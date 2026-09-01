import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api import actions, assistant, brain63, cognitive, decision, desktop, devices, events, fleet, hardware, kosine, maps, memory, memory_providers, missions, mission_control, mode, nodes, observability, personal, planner, presence, productivity, project_intelligence, projects, safety, scheduled_tasks, scheduling, services, system, telegram, voice, watch, web, workflows, workspace, world
from backend.app.core.auth_middleware import AuthMiddleware
from backend.app.models.nodes import NodeMetricsUpdate
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.services.node_service import NodeService
from backend.app.services.service_registry import ServiceRegistry
from backend.config import API_KEY, CORS_ALLOW_ORIGINS
from backend.utils import get_logger, setup_logging


logger = get_logger(__name__)


async def _agent_poll_loop(router: AssistantPlatformRouter) -> None:
    """Poll silvia-agent on every node that has agent_url set. Runs every 30s."""
    await asyncio.sleep(8)
    node_svc = NodeService()
    svc_registry = ServiceRegistry()
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

                    # Fetch legacy flat services/capabilities (backwards compat)
                    svc_resp = await client.get(f"{url}/services")
                    svc_data = svc_resp.json() if svc_resp.status_code == 200 else {}

                    cap_resp = await client.get(f"{url}/capabilities")
                    cap_data = cap_resp.json() if cap_resp.status_code == 200 else {}

                    # Phase 10: fetch structured manifest and ingest if available
                    try:
                        manifest_resp = await client.get(f"{url}/manifest")
                        if manifest_resp.status_code == 200:
                            from backend.app.models.services import ServiceManifest
                            manifest = ServiceManifest.model_validate(manifest_resp.json())
                            svc_registry.ingest_manifest(node.id, manifest)
                    except Exception:
                        pass

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

        # Prune telemetry history older than 7 days (run once per cycle)
        try:
            node_svc.prune_telemetry_history()
        except Exception:
            pass

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
    from backend.app.services.notification_service import send_alert
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
                        offline_mins = int(offline_dur.total_seconds() / 60)
                        offline_hrs = offline_dur.total_seconds() / 3600
                        if offline_dur.total_seconds() >= _OFFLINE_ALERT_MINUTES * 60:
                            # Human-readable duration for synthesized message
                            if offline_hrs >= 1:
                                dur_str = f"{offline_hrs:.1f}h"
                            else:
                                dur_str = f"{offline_mins}min"
                            msg = f"{node.name} offline for {dur_str}"
                            alert = watch_svc.raise_alert(
                                rule_key=f"{prefix}:offline",
                                message=msg,
                                category="infra",
                                severity="critical",
                            )
                            if alert:
                                await router.event_service.emit_ws_only({
                                    "type": "watch_alert",
                                    "alert": alert.model_dump(),
                                })
                                await router.event_service.emit(
                                    f"[OPS] {node.name}", f"offline {dur_str}", "error"
                                )
                                asyncio.create_task(send_alert(alert))
                            else:
                                # Alert already exists — update message with current duration
                                watch_svc.update_alert(f"{prefix}:offline", msg)
                    elif node.status == "online":
                        _offline_since.pop(node.id, None)
                        if watch_svc.resolve_alert(f"{prefix}:offline"):
                            await router.event_service.emit_ws_only({
                                "type": "watch_resolve",
                                "rule_key": f"{prefix}:offline",
                            })

                # ── Metric threshold checks ──────────────────────────────────
                # Only evaluate if node is online AND telemetry is fresh.
                # Skipping offline nodes prevents false alerts from stale metric
                # values that remain in the DB after a node goes unreachable.
                if node.status != "online" or not _is_fresh(node.last_seen):
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
                            asyncio.create_task(send_alert(alert))
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
                            asyncio.create_task(send_alert(alert))
                    else:
                        if watch_svc.resolve_alert(rule_key):
                            await router.event_service.emit_ws_only({
                                "type": "watch_resolve",
                                "rule_key": rule_key,
                            })

            # ── Service health monitoring (Phase 10) ────────────────────────
            # If a registered service is stopped/failed while its node is online,
            # raise a Watch Officer alert.
            try:
                from backend.app.services.service_registry import ServiceRegistry as _SR
                _svc_reg = _SR()
                all_services = _svc_reg.list_services()
                for svc in all_services:
                    rule_key = f"service:{svc.id}:down"
                    node_obj = next((n for n in nodes_list if n.id == svc.node_id), None)
                    if node_obj and node_obj.status == "online" and svc.status in ("stopped", "failed"):
                        alert = watch_svc.raise_alert(
                            rule_key=rule_key,
                            message=f"Service '{svc.name}' on {node_obj.name} is {svc.status}",
                            category="infra",
                            severity="warning" if svc.status == "stopped" else "critical",
                        )
                        if alert:
                            await router.event_service.emit_ws_only({
                                "type": "watch_alert", "alert": alert.model_dump(),
                            })
                    elif svc.status == "running":
                        if watch_svc.resolve_alert(rule_key):
                            await router.event_service.emit_ws_only({
                                "type": "watch_resolve", "rule_key": rule_key,
                            })
            except Exception:
                pass

            # ── Pattern detection: multiple alerts from same node ────────────
            # If a node has 3+ active alerts, surface a synthesis alert.
            for node in nodes_list:
                if node.id == "workstation":
                    continue
                node_alerts = watch_svc.get_active_by_prefix(f"node:{node.id}:")
                # Exclude the cluster alert itself from the count
                issue_alerts = [a for a in node_alerts if not a.rule_key or not a.rule_key.endswith(":cluster")]
                if len(issue_alerts) >= 3:
                    watch_svc.raise_alert(
                        rule_key=f"node:{node.id}:cluster",
                        message=f"{node.name}: {len(issue_alerts)} active issues detected simultaneously",
                        category="infra",
                        severity="critical",
                    )
                elif len(issue_alerts) < 3:
                    watch_svc.resolve_alert(f"node:{node.id}:cluster")

        except Exception as exc:
            logger.warning("Watch officer loop error: %s", exc)

        await asyncio.sleep(30)


async def _reminder_escalation_loop(router: AssistantPlatformRouter) -> None:
    """Escalate Watch Officer alerts for reminders that have been ignored.

    Escalation tiers (measured from the alert's created_at):
      24 h → severity bumped to 'warning', message prefixed with [ESCALATED]
      72 h → severity bumped to 'critical', message prefixed with [ELEVATED]
    """
    await asyncio.sleep(90)  # start well after reminder_loop has had a chance to fire
    from backend.app.services.watch_service import WatchService
    watch_svc = WatchService()

    while True:
        try:
            from backend.config import SILVIA_SAFE_MODE
            if SILVIA_SAFE_MODE:
                await asyncio.sleep(300)
                continue

            now = datetime.now(timezone.utc)
            # All active reminder alerts — those not yet dismissed by the operator
            alerts = watch_svc.get_active_by_prefix("reminder:")
            for alert in alerts:
                # Only escalate original alerts (not already-escalated ones)
                if not alert.rule_key:
                    continue
                parts = alert.rule_key.split(":")
                if len(parts) != 2:
                    continue  # skip escalation sub-keys
                try:
                    created = datetime.fromisoformat(alert.created_at)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                age_hours = (now - created).total_seconds() / 3600
                rid = parts[1]

                if age_hours >= 72:
                    watch_svc.raise_alert(
                        rule_key=f"reminder:{rid}:elevated",
                        message=f"[ELEVATED] {alert.message} — ignored for {int(age_hours)}h",
                        category="system",
                        severity="critical",
                    )
                elif age_hours >= 24:
                    watch_svc.raise_alert(
                        rule_key=f"reminder:{rid}:escalated",
                        message=f"[ESCALATED] {alert.message} — unacknowledged for {int(age_hours)}h",
                        category="system",
                        severity="warning",
                    )
        except Exception as exc:
            logger.warning("Reminder escalation loop error: %s", exc)

        await asyncio.sleep(300)  # check every 5 minutes


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


async def _scheduled_task_loop(router: AssistantPlatformRouter) -> None:
    """Run due scheduled tasks via Hermes every 60 seconds."""
    await asyncio.sleep(30)
    from backend.app.services.scheduled_task_service import ScheduledTaskService
    svc = ScheduledTaskService()

    while True:
        try:
            from backend.config import SILVIA_SAFE_MODE
            if SILVIA_SAFE_MODE:
                await asyncio.sleep(60)
                continue

            due = svc.get_due_tasks()
            for task in due:
                await router.event_service.emit(
                    "[SCHED]", f"Running: {task['name']}", "info"
                )
                result_text = "No result"
                try:
                    if router.conversation_service and router.conversation_service.execution_engine:
                        from backend.app.models.assistant import AssistantRequest
                        fake_req = AssistantRequest(
                            query=task["prompt"],
                            mode="conversation",
                            session_id="scheduled-task",
                            metadata={},
                        )
                        resp = await router.conversation_service.execution_engine.run(
                            task["prompt"], fake_req
                        )
                        if resp:
                            result_text = resp.answer[:500]
                except Exception as task_exc:
                    result_text = f"Error: {task_exc}"
                    logger.warning("Scheduled task '%s' failed: %s", task["name"], task_exc)

                svc.mark_ran(task["id"], result_text)
                await router.event_service.emit(
                    f"[SCHED] {task['name']}", result_text[:120], "info"
                )
        except Exception as exc:
            logger.warning("Scheduled task loop error: %s", exc)

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
            from backend.config import SILVIA_SAFE_MODE
            if SILVIA_SAFE_MODE:
                await asyncio.sleep(60)
                continue

            # Check if reminders are paused via conversation service
            if router.conversation_service and getattr(router.conversation_service, '_reminders_paused', False):
                await asyncio.sleep(60)
                continue

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
                    # Persist proof of delivery before changing the schedule.
                    reminder_svc.record_delivery(reminder.id, delivered=True)
                    if reminder.recurrence != "once":
                        reminder_svc.advance_recurrence(reminder.id)
                        watch_svc.resolve_alert(f"reminder:{reminder.id}")
                elif reminder.delivery_status != "delivered":
                    # A deduplicated Watch alert is not proof that this attempt
                    # delivered. Record a visible failure rather than retrying
                    # every minute or pretending success.
                    reminder_svc.record_delivery(reminder.id, delivered=False,
                                                  error="notification alert was not created")
        except Exception as exc:
            logger.warning("Reminder loop error: %s", exc)
        await asyncio.sleep(60)


async def _print_startup_health() -> None:
    """Print a concise startup health summary to the log."""
    import sqlite3
    from pathlib import Path
    import httpx

    lines = ["", "SILVIA Startup Health", "=" * 40]

    # Database
    db_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")
        tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        lines.append(f"  Database:     OK ({tables} tables)")
    except Exception as e:
        lines.append(f"  Database:     FAILED ({e})")

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get("http://localhost:11434/api/tags")
            r.raise_for_status()
            model_count = len(r.json().get("models", []))
            lines.append(f"  Ollama:       OK ({model_count} models)")
    except Exception:
        lines.append("  Ollama:       FAILED (not reachable)")

    # Gmail
    try:
        from backend.app.services.productivity.auth_service import GoogleAuthService
        auth = GoogleAuthService()
        status = auth.get_status()
        if status.get("authenticated"):
            lines.append(f"  Gmail:        OK ({status.get('email', 'authenticated')})")
        else:
            lines.append("  Gmail:        Not configured")
    except Exception:
        lines.append("  Gmail:        Not configured")

    # Telegram
    from backend.config import TELEGRAM_ENABLED
    from backend.app.services.telegram_bridge import get_bridge
    bridge = get_bridge()
    if not TELEGRAM_ENABLED:
        lines.append("  Telegram:     Disabled")
    elif bridge and bridge.running:
        lines.append("  Telegram:     OK (polling)")
    else:
        lines.append("  Telegram:     Configured but not running")

    # Reminders
    try:
        from backend.app.services.reminder_service import ReminderService
        rs = ReminderService()
        active = rs.list_reminders(include_completed=False)
        due = rs.get_due_reminders()
        stuck = [r for r in due if r.recurrence == "once"]
        if stuck:
            lines.append(f"  Reminders:    WARNING ({len(stuck)} stuck, {len(active)} active)")
        else:
            lines.append(f"  Reminders:    OK ({len(active)} active)")
    except Exception:
        lines.append("  Reminders:    FAILED")

    # SSH
    from backend.config import SSH_REQUIRES_APPROVAL
    lines.append(f"  SSH:          OK (approval={'required' if SSH_REQUIRES_APPROVAL else 'disabled'})")

    # Nodes
    try:
        ns = NodeService()
        nodes = ns.list_nodes()
        online = sum(1 for n in nodes if n.status == "online")
        lines.append(f"  Nodes:        OK ({len(nodes)} registered, {online} online)")
    except Exception:
        lines.append("  Nodes:        FAILED")

    # Voice STT/TTS
    try:
        from backend.app.services.voice_service import _check_speaches, _check_whisper_installed
        from backend.config import SPEACHES_BASE_URL, STT_PROVIDER, TTS_PROVIDER
        speaches_ok, speaches_detail = _check_speaches(SPEACHES_BASE_URL)
        whisper_ok, _ = _check_whisper_installed()
        if STT_PROVIDER == "speaches" and speaches_ok:
            lines.append(f"  Voice STT:    OK (Speaches @ {SPEACHES_BASE_URL})")
        elif STT_PROVIDER == "speaches" and not speaches_ok:
            if whisper_ok:
                lines.append(f"  Voice STT:    WARNING (Speaches unavailable, using local Whisper)")
            else:
                lines.append(f"  Voice STT:    FAILED ({speaches_detail})")
        elif whisper_ok:
            lines.append("  Voice STT:    OK (local Whisper)")
        else:
            lines.append("  Voice STT:    Not configured")
        if TTS_PROVIDER == "speaches" and speaches_ok:
            lines.append(f"  Voice TTS:    OK (Speaches)")
        else:
            lines.append(f"  Voice TTS:    {'OK (Piper)' if TTS_PROVIDER == 'piper' else 'Not configured'}")
    except Exception:
        lines.append("  Voice:        Error during check")

    # Safe mode
    from backend.config import SILVIA_SAFE_MODE
    if SILVIA_SAFE_MODE:
        lines.append("  Safe Mode:    ENABLED — proactive features disabled")

    lines.append("=" * 40)
    lines.append("")

    for line in lines:
        logger.info(line)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    app.state.readiness = {"core": "initializing", "optional": "initializing"}
    router = AssistantPlatformRouter()
    app.state.router = router
    logger.info("Assistant platform initialized")
    # Core persistence is ready as soon as the canonical services can open.
    from backend.app.services.task_service import TaskService
    from backend.app.services.reminder_service import ReminderService
    TaskService(); ReminderService()
    app.state.readiness["core"] = "healthy"

    # Wire the cognitive-event bus to the existing WebSocket fan-out so live
    # cognitive activity streams to the Cognitive Graph. Provider-agnostic.
    try:
        from backend.app.services.cognition.events import get_cognitive_bus
        bus = get_cognitive_bus()
        bus.clear_publishers()
        bus.register_publisher(router.event_service.emit_ws_only)
        logger.info("Cognitive event bus wired to WebSocket fan-out")
    except Exception as e:
        logger.warning("Cognitive bus wiring failed: %s", e)

    # Pre-warm wake word detector in a thread so model downloads and ONNX
    # session creation happen at startup, not on the first WS connection.
    async def _warm_wake_word():
        try:
            from backend.voice.wakeword.detector import get_detector
            await asyncio.get_running_loop().run_in_executor(None, get_detector)
            logger.info("Wake word detector pre-warmed")
        except Exception as exc:
            logger.warning("Wake word detector pre-warm failed (non-fatal): %s", exc)
    asyncio.create_task(_warm_wake_word())

    # Retroactively index existing messages into semantic memory (non-blocking)
    async def _index_existing_messages():
        try:
            n = await router.semantic_memory_service.index_existing(limit=200)
            logger.info("Semantic memory: indexed %d existing turns", n)
        except Exception as exc:
            logger.debug("Semantic memory retroactive index failed (non-fatal): %s", exc)

    asyncio.create_task(_index_existing_messages())

    # Pre-warm the chat + embedding models so the FIRST user query doesn't pay
    # model-load latency. Runs in the background — never blocks startup.
    async def _warm_models():
        import httpx as _httpx
        from backend.config import CONVERSATION_MODEL, OLLAMA_CHAT_URL, KEEP_ALIVE
        try:
            async with _httpx.AsyncClient(timeout=120.0) as client:
                await client.post(OLLAMA_CHAT_URL, json={
                    "model": CONVERSATION_MODEL,
                    "messages": [{"role": "user", "content": "ok"}],
                    "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"num_predict": 1},
                })
            from backend.app.services.embedding_service import get_embedding
            await get_embedding("warmup")
            logger.info("LLM models pre-warmed (chat=%s + nomic-embed-text)", CONVERSATION_MODEL)
        except Exception as exc:
            logger.warning("Model pre-warm failed (non-fatal): %s", exc)

    asyncio.create_task(_warm_models())

    probe_task = asyncio.create_task(_node_probe_loop(router))
    agent_task = asyncio.create_task(_agent_poll_loop(router))
    watch_task = asyncio.create_task(_watch_officer_loop(router))
    reminder_task = asyncio.create_task(_reminder_loop(router))
    escalation_task = asyncio.create_task(_reminder_escalation_loop(router))
    sched_task = asyncio.create_task(_scheduled_task_loop(router))

    # Telegram bridge — starts only when TELEGRAM_ENABLED=true
    from backend.app.services.telegram_bridge import start_bridge, stop_bridge
    telegram_start_task = asyncio.create_task(start_bridge(router))

    # ── Startup health summary ─────────────────────────────────────────────
    async def _optional_readiness():
        try:
            await telegram_start_task
            await _print_startup_health()
            app.state.readiness["optional"] = "healthy"
        except Exception as exc:
            app.state.readiness["optional"] = "degraded"
            logger.warning("Optional startup services degraded: %s", exc)
    asyncio.create_task(_optional_readiness())

    yield

    probe_task.cancel()
    agent_task.cancel()
    watch_task.cancel()
    reminder_task.cancel()
    escalation_task.cancel()
    sched_task.cancel()
    await stop_bridge()
    logger.info("Assistant platform shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SILVIA — AI Operating System",
        description="Strategic Intelligence, Logistics, Voice & Integrated Assistant. Local-first. Ollama-powered. Multi-agent.",
        version="4.0.0",
        lifespan=lifespan,
    )
    if API_KEY:
        app.add_middleware(AuthMiddleware)
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
        readiness = getattr(app.state, "readiness", {"core": "initializing", "optional": "initializing"})
        status = "healthy" if readiness.get("core") == "healthy" and readiness.get("optional") == "healthy" else (
            "degraded" if readiness.get("core") == "healthy" else "initializing"
        )
        return {"status": status, "service": "silvia", "version": "4.0.0", "readiness": readiness}

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
    app.include_router(scheduling.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(missions.router, prefix="/api")
    app.include_router(nodes.router, prefix="/api")
    app.include_router(watch.router, prefix="/api")
    app.include_router(personal.router, prefix="/api")
    app.include_router(scheduled_tasks.router, prefix="/api")
    app.include_router(services.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(mission_control.router, prefix="/api")
    app.include_router(desktop.router, prefix="/api")
    app.include_router(hardware.router, prefix="/api")
    app.include_router(productivity.router, prefix="/api")
    app.include_router(fleet.router, prefix="/api")
    app.include_router(observability.router, prefix="/api")
    app.include_router(project_intelligence.router, prefix="/api")
    app.include_router(project_intelligence.knowledge_router, prefix="/api")
    app.include_router(project_intelligence.memory_router, prefix="/api")
    app.include_router(telegram.router, prefix="/api")
    app.include_router(workspace.router, prefix="/api")
    app.include_router(planner.router, prefix="/api")
    app.include_router(safety.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(memory_providers.router, prefix="/api")
    app.include_router(brain63.router, prefix="/api")
    app.include_router(presence.router, prefix="/api")
    app.include_router(cognitive.router, prefix="/api")
    app.include_router(kosine.router, prefix="/api")
    return app
