import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api import actions, assistant, decision, devices, events, maps, memory, missions, mode, nodes, personal, system, voice, watch, web, world
from backend.app.models.nodes import NodeMetricsUpdate
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.services.node_service import NodeService
from backend.config import CORS_ALLOW_ORIGINS
from backend.utils import get_logger, setup_logging


logger = get_logger(__name__)


async def _agent_poll_loop(router: AssistantPlatformRouter) -> None:
    """Poll silvia-agent on every node that has agent_url set. Runs every 30s."""
    await asyncio.sleep(8)
    node_svc = NodeService()
    while True:
        nodes_list = node_svc.list_nodes()
        agent_nodes = [n for n in nodes_list if n.agent_url]
        async with httpx.AsyncClient(timeout=5.0) as client:
            for node in agent_nodes:
                url = node.agent_url.rstrip("/")
                try:
                    resp = await client.get(f"{url}/telemetry")
                    resp.raise_for_status()
                    tel = resp.json()

                    # Fetch services in parallel
                    svc_resp = await client.get(f"{url}/services")
                    svc_data = svc_resp.json() if svc_resp.status_code == 200 else {}

                    cap_resp = await client.get(f"{url}/capabilities")
                    cap_data = cap_resp.json() if cap_resp.status_code == 200 else {}

                    metrics = NodeMetricsUpdate(
                        status="online",
                        cpu=tel.get("cpu"),
                        ram=tel.get("ram"),
                        disk=tel.get("disk"),
                        temperature=tel.get("temperature"),
                        uptime=tel.get("uptime"),
                        services=svc_data.get("services"),
                        capabilities=cap_data.get("capabilities"),
                        last_verified=datetime.now(timezone.utc).isoformat(),
                        verification_source="silvia-agent",
                        # Robotics / edge telemetry
                        battery_pct=tel.get("battery_pct"),
                        position_lat=tel.get("position_lat"),
                        position_lon=tel.get("position_lon"),
                        altitude=tel.get("altitude"),
                        heading=tel.get("heading"),
                        mission_state=tel.get("mission_state"),
                        imu_data=tel.get("imu_data"),
                    )
                    node_svc.update_metrics(node.id, metrics)

                    detail = "Agent online"
                    if tel.get("cpu") is not None:
                        detail += f" · CPU {tel['cpu']:.0f}% RAM {tel['ram']:.0f}%"
                    if tel.get("temperature") is not None:
                        detail += f" · {tel['temperature']:.0f}°C"
                    if tel.get("battery_pct") is not None:
                        detail += f" · Bat {tel['battery_pct']:.0f}%"
                    if tel.get("mission_state"):
                        detail += f" · {tel['mission_state']}"
                    await router.event_service.emit(f"Agent: {node.name}", detail, "info")
                    await router.event_service.emit_ws_only({
                        "type": "node_telemetry",
                        "node_id": node.id,
                        "node_name": node.name,
                        "cpu": tel.get("cpu"),
                        "ram": tel.get("ram"),
                        "disk": tel.get("disk"),
                        "temperature": tel.get("temperature"),
                        "uptime": tel.get("uptime"),
                        "battery_pct": tel.get("battery_pct"),
                        "position_lat": tel.get("position_lat"),
                        "position_lon": tel.get("position_lon"),
                        "altitude": tel.get("altitude"),
                        "heading": tel.get("heading"),
                        "mission_state": tel.get("mission_state"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                except Exception as exc:
                    # Mark offline only if previously online via agent
                    if node.status == "online":
                        node_svc.update_metrics(node.id, NodeMetricsUpdate(status="offline"))
                    logger.debug("Agent poll failed for %s (%s): %s", node.name, url, exc)
                    await router.event_service.emit(
                        f"Agent: {node.name}", f"Unreachable — {type(exc).__name__}", "warning"
                    )

        await asyncio.sleep(30)


_OFFLINE_ALERT_MINUTES = 30   # raise offline alert after this many minutes of downtime
_offline_since: dict[str, datetime] = {}  # node_id → first time noticed offline

_CPU_WARN = 85.0
_CPU_CRIT = 95.0
_RAM_WARN = 85.0
_RAM_CRIT = 95.0
_DISK_WARN = 88.0
_DISK_CRIT = 95.0
_TEMP_WARN = 75.0
_TEMP_CRIT = 85.0
_STALE_MINUTES = 5


def _is_fresh(last_seen: str | None) -> bool:
    from datetime import timedelta
    if not last_seen:
        return False
    try:
        ts = datetime.fromisoformat(last_seen)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < timedelta(minutes=_STALE_MINUTES)
    except Exception:
        return False


async def _watch_officer_loop(router: AssistantPlatformRouter) -> None:
    """Evaluate node telemetry against thresholds, raise/resolve Watch Officer alerts."""
    await asyncio.sleep(20)  # Start after agent poll has run at least once
    from backend.app.services.watch_service import WatchService
    node_svc = NodeService()
    watch_svc = WatchService()

    while True:
        try:
            nodes_list = node_svc.list_nodes()

            for node in nodes_list:
                prefix = f"node:{node.id}"

                # ── Offline check (skip workstation — always local) ──────────
                if node.id != "workstation":
                    if node.status == "offline" and node.last_seen:
                        _offline_since.setdefault(node.id, datetime.now(timezone.utc))
                        offline_dur = datetime.now(timezone.utc) - _offline_since[node.id]
                        if offline_dur.total_seconds() >= _OFFLINE_ALERT_MINUTES * 60:
                            alert = watch_svc.raise_alert(
                                rule_key=f"{prefix}:offline",
                                message=f"{node.name} offline for {_OFFLINE_ALERT_MINUTES}+ min",
                                category="infra",
                                severity="critical",
                            )
                            if alert:
                                await router.event_service.emit_ws_only({
                                    "type": "watch_alert",
                                    "alert": alert.model_dump(),
                                })
                                await router.event_service.emit(
                                    f"[OPS] {node.name}", f"offline {_OFFLINE_ALERT_MINUTES}+ min", "error"
                                )
                    elif node.status == "online":
                        _offline_since.pop(node.id, None)
                        if watch_svc.resolve_alert(f"{prefix}:offline"):
                            await router.event_service.emit_ws_only({
                                "type": "watch_resolve",
                                "rule_key": f"{prefix}:offline",
                            })

                # ── Metric threshold checks ──────────────────────────────────
                # Only evaluate if telemetry is fresh (within last 5 minutes)
                if not _is_fresh(node.last_seen):
                    continue

                checks = [
                    ("cpu",         node.cpu,         _CPU_WARN,  _CPU_CRIT,  "CPU",  "%"),
                    ("ram",         node.ram,         _RAM_WARN,  _RAM_CRIT,  "RAM",  "%"),
                    ("disk",        node.disk,        _DISK_WARN, _DISK_CRIT, "Disk", "%"),
                    ("temperature", node.temperature, _TEMP_WARN, _TEMP_CRIT, "Temp", "°C"),
                ]
                for metric, value, warn, crit, label, unit in checks:
                    rule_key = f"{prefix}:{metric}_high"
                    if value is None:
                        continue

                    if value >= crit:
                        alert = watch_svc.raise_alert(
                            rule_key=rule_key,
                            message=f"{node.name} {label} {value:.0f}{unit}",
                            category="infra",
                            severity="critical",
                        )
                        if alert:
                            await router.event_service.emit_ws_only({
                                "type": "watch_alert",
                                "alert": alert.model_dump(),
                            })
                            await router.event_service.emit(
                                f"[OPS] {node.name}", f"{label} {value:.0f}{unit}", "error"
                            )
                    elif value >= warn:
                        alert = watch_svc.raise_alert(
                            rule_key=rule_key,
                            message=f"{node.name} {label} {value:.0f}{unit}",
                            category="infra",
                            severity="warning",
                        )
                        if alert:
                            await router.event_service.emit_ws_only({
                                "type": "watch_alert",
                                "alert": alert.model_dump(),
                            })
                            await router.event_service.emit(
                                f"[OPS] {node.name}", f"{label} {value:.0f}{unit}", "warning"
                            )
                    else:
                        if watch_svc.resolve_alert(rule_key):
                            await router.event_service.emit_ws_only({
                                "type": "watch_resolve",
                                "rule_key": rule_key,
                            })

        except Exception as exc:
            logger.warning("Watch officer loop error: %s", exc)

        await asyncio.sleep(30)


async def _node_probe_loop(router: AssistantPlatformRouter) -> None:
    await asyncio.sleep(4)
    node_svc = NodeService()
    loop = asyncio.get_running_loop()
    while True:
        try:
            probed = await loop.run_in_executor(None, node_svc.probe_all_nodes)
            for node in probed:
                level = "info" if node.status == "online" else "warning"
                detail = f"Status: {node.status}"
                if node.latency_ms is not None and node.latency_ms > 0.2:
                    detail += f" | {node.latency_ms:.0f}ms"
                if node.cpu is not None:
                    detail += f" | CPU {node.cpu:.0f}% RAM {node.ram:.0f}%"
                if node.probe_error:
                    detail += f" | {node.probe_error}"
                    level = "error"
                await router.event_service.emit(f"Node: {node.name}", detail, level)
        except Exception as exc:
            logger.warning("Node probe loop error: %s", exc)
        await asyncio.sleep(60)


async def _reminder_loop(router: AssistantPlatformRouter) -> None:
    """Check for due reminders every 60s and fire them via Watch Officer + WebSocket."""
    await asyncio.sleep(15)
    from backend.app.services.reminder_service import ReminderService
    from backend.app.services.watch_service import WatchService

    reminder_svc = ReminderService()
    watch_svc = WatchService()

    while True:
        try:
            due = reminder_svc.get_due_reminders()
            for reminder in due:
                alert = watch_svc.raise_alert(
                    rule_key=f"reminder:{reminder.id}",
                    message=f"Reminder: {reminder.message}",
                    category="system",
                    severity="info",
                )
                if alert:
                    await router.event_service.emit_ws_only({
                        "type": "watch_alert",
                        "alert": alert.model_dump(),
                    })
                    await router.event_service.emit("[REM]", reminder.message, "info")

                if reminder.recurrence == "once":
                    reminder_svc.complete_reminder(reminder.id)
                else:
                    reminder_svc.advance_recurrence(reminder.id)
                    # Auto-resolve so the same alert can fire again next cycle
                    watch_svc.resolve_alert(f"reminder:{reminder.id}")
        except Exception as exc:
            logger.warning("Reminder loop error: %s", exc)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    router = AssistantPlatformRouter()
    app.state.router = router
    logger.info("Assistant platform initialized")

    # Pre-warm wake word detector in a thread so model downloads and ONNX
    # session creation happen at startup, not on the first WS connection.
    loop = asyncio.get_event_loop()
    try:
        from backend.voice.wakeword.detector import get_detector
        await loop.run_in_executor(None, get_detector)
        logger.info("Wake word detector pre-warmed")
    except Exception as exc:
        logger.warning("Wake word detector pre-warm failed (non-fatal): %s", exc)

    # Retroactively index existing messages into semantic memory (non-blocking)
    async def _index_existing_messages():
        try:
            n = await router.semantic_memory_service.index_existing(limit=200)
            logger.info("Semantic memory: indexed %d existing turns", n)
        except Exception as exc:
            logger.debug("Semantic memory retroactive index failed (non-fatal): %s", exc)

    asyncio.create_task(_index_existing_messages())

    probe_task = asyncio.create_task(_node_probe_loop(router))
    agent_task = asyncio.create_task(_agent_poll_loop(router))
    watch_task = asyncio.create_task(_watch_officer_loop(router))
    reminder_task = asyncio.create_task(_reminder_loop(router))

    yield

    probe_task.cancel()
    agent_task.cancel()
    watch_task.cancel()
    reminder_task.cancel()
    logger.info("Assistant platform shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SILVIA — AI Operating System",
        description="Strategic Intelligence, Logistics, Voice & Integrated Assistant. Local-first. Ollama-powered. Multi-agent.",
        version="4.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "silvia", "version": "4.0.0"}

    app.include_router(assistant.router, prefix="/api")
    app.include_router(decision.router, prefix="/api")
    app.include_router(mode.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(devices.router, prefix="/api")
    app.include_router(world.router, prefix="/api")
    app.include_router(maps.router, prefix="/api")
    app.include_router(voice.router, prefix="/api")
    app.include_router(web.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(missions.router, prefix="/api")
    app.include_router(nodes.router, prefix="/api")
    app.include_router(watch.router, prefix="/api")
    app.include_router(personal.router, prefix="/api")
    return app
