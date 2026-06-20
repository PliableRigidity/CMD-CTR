"""Transport-agnostic capability executor.

Resolves a capability name → matching services → executes via the correct transport.
Returns a standardised result dict identical to node_tool._make_result().
"""
from __future__ import annotations

from typing import Optional

from backend.app.models.services import CapabilityMatch
from backend.app.services.service_registry import ServiceRegistry


def _make_result(ok: bool, tool: str, node: str | None, summary: str, data, error: str | None) -> dict:
    return {"ok": ok, "tool": tool, "node": node, "summary": summary, "data": data, "error": error}


class CapabilityExecutor:
    def __init__(self) -> None:
        self._registry = ServiceRegistry()

    async def execute(
        self,
        capability: str,
        args: dict | None = None,
        service_id: Optional[str] = None,
        node_name: Optional[str] = None,
        _intent: str = "",
    ) -> dict:
        """Find and execute a capability.

        If service_id is given, run on that specific service.
        If node_name is given, restrict search to that node.
        Otherwise runs on the first running service that exposes this capability.

        When ENABLE_CAPABILITY_EXECUTION=false the capability is resolved but not
        dispatched — a simulation result is returned instead.

        Returns a result dict. Never raises.
        """
        import time as _time
        from backend.config import ENABLE_CAPABILITY_EXECUTION
        from backend.app.services.execution_ledger import get_ledger
        _t0   = _time.monotonic()
        args  = args or {}

        # 1. Find matching services
        if service_id:
            matches = self._find_by_service_id(service_id, capability)
        else:
            matches = self._registry.find_capability(capability, node_name=node_name)

        if not matches:
            get_ledger().log_execution(
                intent=_intent, capability=capability, node=node_name,
                tool="execute_capability", status="failure",
                message=f"No service found for '{capability}'",
            )
            return _make_result(
                False, "execute_capability", node_name,
                f"No service found that exposes capability '{capability}'.",
                {"capability": capability, "matches": []},
                f"No registered service has capability '{capability}'. "
                "Register a service with this capability first.",
            )

        # 2. Prefer running, fall back to stopped
        running = [m for m in matches if m.service_status == "running"]
        target = running[0] if running else matches[0]

        # 3. Simulation mode — resolve but don't dispatch
        if not ENABLE_CAPABILITY_EXECUTION:
            transport = target.service_transport
            cmd_hint = ""
            if transport == "ssh":
                svc_name = args.get("service") or target.service_config.get("service_name") or target.service_name
                cmd_hint = f" → `sudo systemctl {capability.split('.')[-1]} {svc_name}`"
            sim_result = _make_result(
                True, "execute_capability", target.node_name,
                f"[SIMULATION] Would execute '{capability}' on {target.node_name} via {transport}{cmd_hint}",
                {
                    "capability": capability,
                    "service": target.service_name,
                    "node": target.node_name,
                    "transport": transport,
                    "simulated": True,
                },
                None,
            )
            get_ledger().log_execution(
                intent=_intent, capability=capability, node=target.node_name,
                service=target.service_name, tool="execute_capability",
                executor=transport, status="simulated",
                duration_ms=int((_time.monotonic() - _t0) * 1000),
                message=sim_result["summary"],
            )
            return sim_result

        if target.service_status != "running":
            get_ledger().log_execution(
                intent=_intent, capability=capability, node=target.node_name,
                service=target.service_name, tool="execute_capability",
                status="failure",
                message=f"Service '{target.service_name}' is {target.service_status}",
            )
            return _make_result(
                False, "execute_capability", target.node_name,
                f"Service '{target.service_name}' on {target.node_name} is {target.service_status}, not running.",
                {"capability": capability, "service": target.service_name,
                 "node": target.node_name, "status": target.service_status},
                f"Service offline. Start it first or check node status.",
            )

        # 4. Dispatch to transport
        dispatch_result = await self._dispatch(target, capability, args)
        get_ledger().log_execution(
            intent=_intent, capability=capability, node=target.node_name,
            service=target.service_name, tool="execute_capability",
            executor=target.service_transport,
            status="success" if dispatch_result["ok"] else "failure",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            message=dispatch_result.get("summary", ""),
            metadata=(dispatch_result.get("data") or {}) if not dispatch_result["ok"] else None,
        )
        return dispatch_result

    async def _dispatch(self, match: CapabilityMatch, capability: str, args: dict) -> dict:
        transport = match.service_transport
        if transport == "http":
            return await self._exec_http(match, capability, args)
        elif transport == "mqtt":
            return await self._exec_mqtt(match, capability, args)
        elif transport == "ssh":
            return await self._exec_ssh(match, capability, args)
        elif transport == "local":
            return await self._exec_local(match, capability, args)
        else:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"Transport '{transport}' is not supported yet.",
                None,
                f"Transport '{transport}' not implemented. Supported: http, mqtt, ssh, local.",
            )

    async def _exec_http(self, match: CapabilityMatch, capability: str, args: dict) -> dict:
        import httpx

        endpoint = match.service_endpoint
        if not endpoint:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"Service '{match.service_name}' has no endpoint configured.",
                None,
                "No endpoint set on this service.",
            )

        url = endpoint.rstrip("/") + "/capability"
        body = {"capability": capability, "args": args}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=body)
                if resp.status_code == 404:
                    # Silvia-agent compatibility: fall back to /command
                    command = capability.split(".")[-1]
                    url2 = endpoint.rstrip("/") + "/command"
                    resp = await client.post(url2, json={"command": command, "payload": args})
                resp.raise_for_status()
            data = resp.json()
            ok = data.get("ok", True)
            return _make_result(
                ok, "execute_capability", match.node_name,
                f"{match.node_name} / {match.service_name} — {capability}: {'ok' if ok else 'failed'}",
                {**data, "capability": capability, "service": match.service_name,
                 "node": match.node_name},
                None if ok else data.get("error"),
            )
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", "")
            except Exception:
                pass
            return _make_result(
                False, "execute_capability", match.node_name,
                f"HTTP {exc.response.status_code} from {match.service_name}: {detail}",
                None,
                detail or str(exc),
            )
        except Exception as exc:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"Could not reach {match.node_name}: {type(exc).__name__}",
                None,
                str(exc),
            )

    async def _exec_mqtt(self, match: CapabilityMatch, capability: str, args: dict) -> dict:
        # MQTT transport is implemented in Phase 10B (aiomqtt integration).
        # Until then, return a clear unsupported error rather than silently failing.
        return _make_result(
            False, "execute_capability", match.node_name,
            f"MQTT transport not yet configured (Phase 10B).",
            {"capability": capability, "service": match.service_name,
             "node": match.node_name, "transport": "mqtt"},
            "MQTT broker not configured. Set MQTT_BROKER_HOST in .env to enable.",
        )

    async def _exec_ssh(self, match: CapabilityMatch, capability: str, args: dict) -> dict:
        """Execute a system capability over SSH (systemctl commands only)."""
        import asyncio
        import shlex

        _SSH_COMMAND_MAP = {
            "system.start":   "sudo systemctl start {service}",
            "system.stop":    "sudo systemctl stop {service}",
            "system.restart": "sudo systemctl restart {service}",
            "system.status":  "systemctl is-active {service}",
            "system.reload":  "sudo systemctl reload {service}",
        }
        template = _SSH_COMMAND_MAP.get(capability)
        if not template:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"SSH transport does not support capability '{capability}'.",
                None,
                f"SSH capabilities are limited to: {', '.join(_SSH_COMMAND_MAP.keys())}",
            )

        service_name = args.get("service") or match.service_config.get("service_name") or match.service_name
        remote_cmd = template.format(service=shlex.quote(service_name))

        endpoint = match.service_endpoint
        if not endpoint:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"No SSH endpoint configured for {match.service_name}.",
                None,
                "Set endpoint to 'user@host' on this service.",
            )

        parts = endpoint.split("@", 1)
        if len(parts) == 2:
            user, host = parts
        else:
            user, host = None, parts[0]

        ssh_cmd = ["ssh"]
        if user:
            ssh_cmd += [f"{user}@{host}"]
        else:
            ssh_cmd += [host]
        ssh_cmd += [remote_cmd]

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            ok = proc.returncode == 0
            output = (stdout or b"").decode().strip() or (stderr or b"").decode().strip()
            return _make_result(
                ok, "execute_capability", match.node_name,
                f"{match.node_name} / {capability}: {'ok' if ok else 'failed'} — {output}",
                {"capability": capability, "service": match.service_name,
                 "node": match.node_name, "output": output, "returncode": proc.returncode},
                None if ok else output,
            )
        except asyncio.TimeoutError:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"SSH command timed out on {match.node_name}.",
                None,
                "SSH command timed out after 15 seconds.",
            )
        except Exception as exc:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"SSH execution failed: {exc}",
                None,
                str(exc),
            )

    async def _exec_local(self, match: CapabilityMatch, capability: str, args: dict) -> dict:
        """Local transport — runs a command on the SILVIA host itself."""
        import asyncio

        cmd = match.service_config.get("command") or args.get("command")
        if not cmd:
            return _make_result(
                False, "execute_capability", match.node_name,
                f"Local service '{match.service_name}' has no command configured.",
                None,
                "Set 'command' in the service config to use local transport.",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            ok = proc.returncode == 0
            output = (stdout or b"").decode().strip()
            return _make_result(
                ok, "execute_capability", "local",
                f"Local / {capability}: {'ok' if ok else 'failed'} — {output[:200]}",
                {"capability": capability, "service": match.service_name,
                 "output": output, "returncode": proc.returncode},
                None if ok else (stderr or b"").decode().strip(),
            )
        except asyncio.TimeoutError:
            return _make_result(
                False, "execute_capability", "local",
                f"Local command timed out.",
                None,
                "Command timed out after 30 seconds.",
            )
        except Exception as exc:
            return _make_result(
                False, "execute_capability", "local",
                f"Local execution failed: {exc}",
                None,
                str(exc),
            )

    def _find_by_service_id(self, service_id: str, capability: str) -> list[CapabilityMatch]:
        """Find capability on a specific service_id."""
        svc = self._registry.get_service(service_id)
        if not svc:
            return []
        for cap in svc.capabilities:
            if cap.name == capability or cap.namespace == capability:
                from backend.app.services.node_service import NodeService
                ns = NodeService()
                node = ns.get_node(svc.node_id)
                return [
                    CapabilityMatch(
                        capability_id=cap.id,
                        capability_name=cap.name,
                        capability_risk=cap.risk_level,
                        capability_confirmation=cap.confirmation_required,
                        service_id=svc.id,
                        service_name=svc.name,
                        service_type=svc.type,
                        service_status=svc.status,
                        service_transport=svc.transport,
                        service_endpoint=svc.endpoint,
                        service_config=svc.config,
                        node_id=svc.node_id,
                        node_name=node.name if node else svc.node_id,
                    )
                ]
        return []

    async def list_node_services(self, node_name: Optional[str] = None) -> dict:
        """List services (and their capabilities) for one node or all nodes."""
        from backend.app.tools.node_tool import _find_node
        if node_name:
            node = _find_node(node_name)
            if not node:
                return _make_result(
                    False, "list_services", node_name,
                    f"Node '{node_name}' not found.",
                    None,
                    f"No node named '{node_name}'.",
                )
            services = self._registry.list_services(node_id=node.id)
            if not services:
                return _make_result(
                    True, "list_services", node_name,
                    f"{node_name} has no registered services.",
                    {"node": node_name, "services": []},
                    None,
                )
            svc_data = [_service_summary(s) for s in services]
            return _make_result(
                True, "list_services", node_name,
                f"{node_name} — {len(services)} service(s)",
                {"node": node_name, "services": svc_data},
                None,
            )
        else:
            services = self._registry.list_services()
            if not services:
                return _make_result(
                    True, "list_services", None,
                    "No services registered yet.",
                    {"services": []},
                    None,
                )
            svc_data = [_service_summary(s) for s in services]
            return _make_result(
                True, "list_services", None,
                f"{len(services)} service(s) registered across all nodes",
                {"services": svc_data},
                None,
            )


def _service_summary(svc: "NodeServiceModel") -> dict:
    return {
        "id": svc.id,
        "node": svc.node_name or svc.node_id,
        "name": svc.name,
        "type": svc.type,
        "status": svc.status,
        "transport": svc.transport,
        "endpoint": svc.endpoint,
        "capabilities": [c.name for c in svc.capabilities if c.enabled],
    }
