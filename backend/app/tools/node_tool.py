"""Node registry tools — lookup, probe, update, delete, SSH, verify."""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

_SAFE_USERNAME = re.compile(r"^[a-zA-Z0-9_.\-]{1,64}$")
_SAFE_HOST = re.compile(r"^[a-zA-Z0-9_.\-]{1,253}$")

# Windows Terminal path — shutil.which("wt") fails when the backend process PATH
# does not include %LOCALAPPDATA%\Microsoft\WindowsApps (common when launched by
# a service or IDE). Fall back to the well-known installation path.
def _find_wt() -> Optional[str]:
    via_which = shutil.which("wt")
    if via_which:
        return via_which
    candidate = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe")
    return candidate if os.path.isfile(candidate) else None


def _make_result(ok: bool, tool: str, node: str | None, summary: str, data, error: str | None) -> dict:
    return {"ok": ok, "tool": tool, "node": node, "summary": summary, "data": data, "error": error}


def _is_ip(s: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", s))


def _find_node(name: str):
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    nodes = ns.list_nodes()
    needle = name.lower().strip()
    for node in nodes:
        if node.name.lower() == needle:
            return node
    for node in nodes:
        if any(a.lower() == needle for a in node.aliases):
            return node
    for node in nodes:
        if needle in node.name.lower():
            return node
    for node in nodes:
        if node.tailscale_name and needle in node.tailscale_name.lower():
            return node
    for node in nodes:
        if node.hostname and needle in node.hostname.lower():
            return node
    return None


def _ip_source(node) -> tuple[Optional[str], str]:
    if node.tailscale_ip:
        return node.tailscale_ip, "tailscale"
    if node.resolved_ip:
        return node.resolved_ip, "dns"
    if node.hostname and _is_ip(node.hostname):
        return node.hostname, "registry"
    return None, "unknown"


def resolve_node_ip(name: str) -> dict:
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "resolve_node_ip", name,
            f"Node '{name}' not found in registry. Use 'list nodes' to see what's registered.",
            None,
            f"No node named '{name}' in registry.",
        )
    ip, source = _ip_source(node)
    verified = node.last_probe_at or node.last_seen
    if not ip:
        return _make_result(
            False, "resolve_node_ip", node.name,
            f"No IP on record for {node.name}. Hostname: {node.hostname or 'not set'}. Run a probe to resolve.",
            {"ip": None, "source": "unknown", "last_verified": verified, "hostname": node.hostname},
            f"No IP address found for '{node.name}'.",
        )
    return _make_result(
        True, "resolve_node_ip", node.name,
        f"{node.name} -> {ip} (source: {source}, last verified: {verified or 'never'})",
        {"ip": ip, "source": source, "last_verified": verified, "hostname": node.hostname},
        None,
    )


def probe_node_by_name(name: str) -> dict:
    from backend.app.services.node_service import NodeService
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "ping_node", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'.",
        )
    ns = NodeService()
    result = ns.probe_node(node.id)
    latency_str = f" | {result.latency_ms:.0f}ms" if result.latency_ms else ""
    error_str = f" | Error: {result.probe_error}" if result.probe_error else ""
    return _make_result(
        result.status == "online",
        "ping_node",
        result.name,
        f"{result.name}: {result.status}{latency_str}{error_str}",
        {
            "status": result.status,
            "latency_ms": result.latency_ms,
            "resolved_ip": result.resolved_ip,
            "probe_error": result.probe_error,
            "last_probe_at": result.last_probe_at,
        },
        result.probe_error,
    )


def list_nodes_status() -> dict:
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    nodes = ns.list_nodes()
    online = [n for n in nodes if n.status == "online"]
    offline = [n for n in nodes if n.status == "offline"]
    unknown = [n for n in nodes if n.status not in ("online", "offline")]
    node_list = [
        {
            "name": n.name,
            "status": n.status,
            "ip": n.tailscale_ip or n.resolved_ip or (n.hostname if _is_ip(n.hostname or "") else None),
            "ip_source": _ip_source(n)[1],
            "latency_ms": n.latency_ms,
            "last_probe_at": n.last_probe_at,
        }
        for n in nodes
    ]
    return _make_result(
        True, "list_nodes", None,
        f"{len(online)} online, {len(offline)} offline, {len(unknown)} unknown — {len(nodes)} total registered",
        {"nodes": node_list, "online_count": len(online), "offline_count": len(offline), "unknown_count": len(unknown)},
        None,
    )


def get_node_info(name: str) -> dict:
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "get_node_info", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'.",
        )
    ip, source = _ip_source(node)
    return _make_result(
        True, "get_node_info", node.name,
        f"{node.name} | {node.status} | IP: {ip or 'unknown'} ({source}) | Last probe: {node.last_probe_at or 'never'}",
        {
            "name": node.name, "type": node.type, "status": node.status,
            "hostname": node.hostname, "ip": ip, "ip_source": source,
            "tailscale_ip": node.tailscale_ip, "tailscale_name": node.tailscale_name,
            "cpu": node.cpu, "ram": node.ram, "disk": node.disk,
            "latency_ms": node.latency_ms, "last_probe_at": node.last_probe_at,
            "probe_error": node.probe_error, "tags": node.tags,
        },
        None,
    )


def update_node_ip(name: str, ip: str) -> dict:
    from backend.app.services.node_service import NodeService
    from backend.app.models.nodes import NodeUpdate
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "update_node_ip", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'.",
        )
    # Clear all IP fields and set the authoritative one so priority is unambiguous
    from backend.app.services.node_service import _conn
    is_tailscale = ip.startswith("100.")
    field, source = ("tailscale_ip", "tailscale") if is_tailscale else ("hostname", "registry")
    conn = _conn()
    try:
        if is_tailscale:
            conn.execute(
                "UPDATE nodes SET tailscale_ip=?, hostname='', resolved_ip=NULL, probe_error=NULL, last_probe_at=NULL WHERE id=?",
                (ip, node.id),
            )
        else:
            conn.execute(
                "UPDATE nodes SET hostname=?, tailscale_ip=NULL, resolved_ip=NULL, probe_error=NULL, last_probe_at=NULL WHERE id=?",
                (ip, node.id),
            )
        conn.commit()
    finally:
        conn.close()
    updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _make_result(
        True, "update_node_ip", node.name,
        f"Updated {node.name} {field} -> {ip} (source: {source}) at {updated_at}",
        {"field": field, "value": ip, "source": source, "updated_at": updated_at},
        None,
    )


def create_node_entry(name: str, hostname: str = "", tailscale_ip: str = "") -> dict:
    if not name:
        return _make_result(
            False, "add_node", None,
            "Node name is required.",
            None,
            "Provide a name: 'add [name] at [hostname/IP]'",
        )
    existing = _find_node(name)
    if existing:
        return _make_result(
            False, "add_node", name,
            f"Node '{existing.name}' already exists in the registry (status: {existing.status}).",
            None,
            f"'{name}' is already registered. Use 'update {name} IP to ...' to change its address.",
        )
    # Duplicate check: same IP/hostname already registered under a different name?
    addr = tailscale_ip or hostname
    if addr and addr not in ("", "local"):
        from backend.app.services.node_service import NodeService as _NS
        _all = _NS().list_nodes()
        for _n in _all:
            if (_n.tailscale_ip and _n.tailscale_ip == addr) or \
               (_n.hostname and _n.hostname == addr):
                return _make_result(
                    False, "add_node", name,
                    f"Address {addr} is already registered as '{_n.name}'. "
                    f"Say 'merge {name} into {_n.name}' to add it as an alias instead.",
                    {"existing_node": _n.name, "existing_id": _n.id},
                    f"Address {addr} already belongs to '{_n.name}'.",
                )
    from backend.app.services.node_service import NodeService
    from backend.app.models.nodes import NodeCreate
    ns = NodeService()
    node = ns.create_node(NodeCreate(
        name=name,
        hostname=hostname,
        tailscale_ip=tailscale_ip or None,
    ))
    addr = tailscale_ip or hostname or "no address set"
    return _make_result(
        True, "add_node", node.name,
        f"Registered '{node.name}' ({addr}) — status: {node.status}.",
        {"id": node.id, "name": node.name, "hostname": hostname, "tailscale_ip": tailscale_ip or None, "status": node.status},
        None,
    )


def open_ssh_session(name: str, username: str, key_path: Optional[str] = None) -> dict:
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "ssh_node", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'. Use 'list nodes' to see registered nodes.",
        )

    # Use stored profile values when caller doesn't supply them
    if not username and node.ssh_username:
        username = node.ssh_username
    if not key_path and node.ssh_key_path:
        key_path = node.ssh_key_path

    ip, source = _ip_source(node)
    host = ip or node.hostname or ""
    if not host or host == "local":
        return _make_result(
            False, "ssh_node", node.name,
            f"No reachable address on record for {node.name}.",
            None,
            f"No IP or hostname configured for '{node.name}'. Add one first.",
        )
    if not username:
        return _make_result(
            False, "ssh_node", node.name,
            f"No SSH username configured for {node.name}.",
            None,
            f"No SSH username set for '{node.name}'. Run: set ssh username for {node.name} to <username>",
        )

    if not _SAFE_USERNAME.match(username):
        return _make_result(
            False, "ssh_node", node.name,
            f"Invalid username '{username}'.",
            None,
            "Username must be alphanumeric (letters, numbers, _ . -) and under 64 chars.",
        )
    if not _SAFE_HOST.match(host):
        return _make_result(
            False, "ssh_node", node.name,
            f"Invalid host address '{host}'.",
            None,
            "Host address contains unsafe characters.",
        )

    # Resolve key path — "default" maps to the user's default ed25519 key
    resolved_key = _resolve_key_path(key_path)
    if resolved_key and not os.path.isfile(resolved_key):
        return _make_result(
            False, "ssh_node", node.name,
            f"SSH key not found: {resolved_key}",
            None,
            f"Key file '{resolved_key}' does not exist. Check the path or set a different key.",
        )

    # Build SSH args list (avoids shell injection; args are passed directly to exec)
    ssh_args = ["ssh"]
    if resolved_key:
        ssh_args += ["-i", resolved_key]
    ssh_args.append(f"{username}@{host}")
    ssh_cmd_display = " ".join(ssh_args)
    title = f"SSH — {node.name}"

    try:
        wt = _find_wt()
        if wt:
            # Use cmd.exe /c start so the window opens in the foreground.
            # start "title" "program" args — the first quoted arg is the window title.
            subprocess.Popen(
                ["cmd.exe", "/c", "start", title, wt,
                 "new-tab", "--title", title, "--"] + ssh_args,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            # Fallback: plain cmd.exe console window
            subprocess.Popen(
                ["cmd.exe", "/k"] + ssh_args,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
    except Exception as exc:
        return _make_result(
            False, "ssh_node", node.name,
            f"Failed to open terminal: {exc}",
            None,
            str(exc),
        )

    key_note = f", key: {resolved_key}" if resolved_key else ""
    return _make_result(
        True, "ssh_node", node.name,
        f"Opened SSH terminal -> {node.name} ({username}@{host}, source: {source}{key_note})",
        {"host": host, "username": username, "source": source, "command": ssh_cmd_display,
         "key_path": resolved_key, "wt_available": bool(wt)},
        None,
    )


def _resolve_key_path(key_path: Optional[str]) -> Optional[str]:
    """Expand 'default' to ~/.ssh/id_ed25519 (or id_rsa as fallback). Returns None if no key."""
    if not key_path:
        return None
    if key_path.lower() in ("default", "~/.ssh/id_ed25519"):
        ed = os.path.expanduser("~/.ssh/id_ed25519")
        rsa = os.path.expanduser("~/.ssh/id_rsa")
        return ed if os.path.isfile(ed) else (rsa if os.path.isfile(rsa) else ed)
    return os.path.expanduser(key_path)


def update_ssh_profile(node_name: str, username: Optional[str], key_path: Optional[str]) -> dict:
    node = _find_node(node_name)
    if not node:
        return _make_result(
            False, "update_ssh_profile", node_name,
            f"Node '{node_name}' not found.",
            None,
            f"No node named '{node_name}'.",
        )
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    resolved_key = _resolve_key_path(key_path) if key_path else node.ssh_key_path
    updated = ns.update_ssh_profile(node.id, username or node.ssh_username, resolved_key)
    if not updated:
        return _make_result(False, "update_ssh_profile", node_name, "Update failed.", None, "DB update returned None.")
    parts = []
    if username:
        parts.append(f"username → {username}")
    if key_path:
        parts.append(f"key → {resolved_key or key_path}")
    summary = f"SSH profile for {node.name} updated: {', '.join(parts)}." if parts else f"SSH profile for {node.name} unchanged."
    return _make_result(
        True, "update_ssh_profile", node.name, summary,
        {"node": node.name, "ssh_username": updated.ssh_username, "ssh_key_path": updated.ssh_key_path},
        None,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ping_sync(host: str) -> dict:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1200", host],
            capture_output=True, text=True, timeout=4, check=False,
        )
        latency = round((time.perf_counter() - started) * 1000, 1)
        return {
            "reachable": result.returncode == 0,
            "latency_ms": latency if result.returncode == 0 else None,
        }
    except Exception:
        return {"reachable": False, "latency_ms": None}


def _node_metrics_dict(node) -> dict:
    return {
        "name": node.name,
        "type": node.type,
        "status": node.status,
        "cpu": node.cpu,
        "ram": node.ram,
        "disk": node.disk,
        "temperature": node.temperature,
        "uptime": node.uptime,
        "last_seen": node.last_seen,
        "last_probe_at": node.last_probe_at,
        "agent_url": node.agent_url,
        "source": "silvia-agent" if node.agent_url else "node-probe",
        # Robotics fields
        "battery_pct": node.battery_pct,
        "position_lat": node.position_lat,
        "position_lon": node.position_lon,
        "altitude": node.altitude,
        "heading": node.heading,
        "mission_state": node.mission_state,
        "imu_data": node.imu_data,
    }


def get_node_telemetry(name: str) -> dict:
    """Return cached telemetry from the node registry for one node or all nodes."""
    from backend.app.services.node_service import NodeService
    ns = NodeService()

    key = (name or "").lower().strip()
    if not key or key in ("all", "all nodes", "every", "nodes", "infrastructure"):
        nodes = ns.list_nodes()
        data = [_node_metrics_dict(n) for n in nodes]
        has_metrics = sum(
            1 for n in nodes
            if any(v is not None for v in [n.cpu, n.ram, n.disk, n.temperature])
        )
        return _make_result(
            True, "get_node_telemetry", None,
            f"{len(nodes)} nodes — {has_metrics} with telemetry data",
            {"nodes": data, "total": len(nodes), "with_metrics": has_metrics},
            None,
        )

    node = _find_node(name)
    if not node:
        return _make_result(
            False, "get_node_telemetry", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}' in registry. Use 'list nodes' to see what's registered.",
        )

    parts = [f"{node.name} | {node.status}"]
    if node.cpu is not None:
        parts.append(f"CPU {node.cpu:.0f}%")
    if node.ram is not None:
        parts.append(f"RAM {node.ram:.0f}%")
    if node.disk is not None:
        parts.append(f"Disk {node.disk:.0f}%")
    if node.temperature is not None:
        parts.append(f"{node.temperature:.0f}°C")

    return _make_result(
        True, "get_node_telemetry", node.name,
        " | ".join(parts),
        _node_metrics_dict(node),
        None,
    )


async def send_bulk_command(node_type: str, command: str, payload: dict | None = None) -> dict:
    """Send a command to all nodes of a given type concurrently."""
    import asyncio as _asyncio
    from backend.app.services.node_service import NodeService

    command = command.strip().lower()
    if command not in _SAFE_COMMANDS:
        return _make_result(
            False, "send_bulk_command", None,
            f"Unknown command '{command}'.",
            None,
            f"Command '{command}' is not in the allowed set: {sorted(_SAFE_COMMANDS)}",
        )

    ns = NodeService()
    nodes = ns.list_nodes_by_type(node_type)
    if not nodes:
        return _make_result(
            True, "send_bulk_command", None,
            f"No {node_type} nodes registered.",
            {"type": node_type, "nodes": [], "succeeded": 0, "failed": 0},
            None,
        )

    agent_nodes = [n for n in nodes if n.agent_url]
    no_agent = [n for n in nodes if not n.agent_url]

    async def _run_one(node):
        return await send_node_command(node.name, command, payload)

    results = await _asyncio.gather(*[_run_one(n) for n in agent_nodes], return_exceptions=True)

    per_node = []
    succeeded = 0
    failed = 0
    for node, res in zip(agent_nodes, results):
        if isinstance(res, Exception):
            per_node.append({"node": node.name, "ok": False, "message": str(res)})
            failed += 1
        else:
            per_node.append({"node": node.name, "ok": res["ok"], "message": res["summary"]})
            if res["ok"]:
                succeeded += 1
            else:
                failed += 1

    for node in no_agent:
        per_node.append({"node": node.name, "ok": False, "message": "No silvia-agent configured"})
        failed += 1

    summary = f"Bulk '{command}' on {len(nodes)} {node_type}(s): {succeeded} succeeded, {failed} failed"
    return _make_result(
        succeeded > 0 or not nodes,
        "send_bulk_command",
        None,
        summary,
        {"type": node_type, "command": command, "nodes": per_node,
         "succeeded": succeeded, "failed": failed},
        None if failed == 0 else f"{failed} node(s) failed",
    )


async def verify_node_by_name(name: str) -> dict:
    """
    Run the full verification chain for a named node:
    local → silvia-agent → tailscale → DNS/ping
    Updates last_verified + verification_source in the registry.
    """
    import asyncio
    import httpx
    from backend.app.services.node_service import NodeService
    from backend.app.models.nodes import NodeMetricsUpdate

    node = _find_node(name)
    if not node:
        return _make_result(
            False, "verify_node", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'. Use 'list nodes' to see registered nodes.",
        )

    ns = NodeService()
    loop = asyncio.get_event_loop()

    # 1. Local workstation — always verified
    if node.type == "workstation" or node.hostname == "local":
        now = _utc_now()
        ns.update_metrics(node.id, NodeMetricsUpdate(
            status="online", last_verified=now, verification_source="local",
        ))
        return _make_result(
            True, "verify_node", node.name,
            f"{node.name} verified — local machine",
            {"name": node.name, "status": "online", "verification_source": "local",
             "last_verified": now, "latency_ms": 0},
            None,
        )

    # 2. Silvia-Agent /status
    if node.agent_url:
        url = node.agent_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"{url}/status")
                if resp.status_code == 200:
                    now = _utc_now()
                    ns.update_metrics(node.id, NodeMetricsUpdate(
                        status="online", last_verified=now, verification_source="silvia-agent",
                    ))
                    return _make_result(
                        True, "verify_node", node.name,
                        f"{node.name} verified via Silvia-Agent",
                        {"name": node.name, "status": "online",
                         "verification_source": "silvia-agent", "last_verified": now, "latency_ms": None},
                        None,
                    )
        except Exception:
            pass

    # 3. Tailscale IP
    if node.tailscale_ip:
        result = await loop.run_in_executor(None, _ping_sync, node.tailscale_ip)
        if result["reachable"]:
            now = _utc_now()
            ns.update_metrics(node.id, NodeMetricsUpdate(
                status="online", last_verified=now, verification_source="tailscale",
                latency_ms=result["latency_ms"],
            ))
            lat = f" ({result['latency_ms']:.0f}ms)" if result["latency_ms"] else ""
            return _make_result(
                True, "verify_node", node.name,
                f"{node.name} verified via Tailscale{lat}",
                {"name": node.name, "status": "online", "verification_source": "tailscale",
                 "last_verified": now, "latency_ms": result["latency_ms"]},
                None,
            )

    # 4. DNS + hostname ping
    if node.hostname and node.hostname not in ("", "local"):
        resolved_ip = None
        try:
            resolved_ip = socket.gethostbyname(node.hostname)
        except OSError:
            pass
        target = resolved_ip or node.hostname
        result = await loop.run_in_executor(None, _ping_sync, target)
        if result["reachable"]:
            now = _utc_now()
            source = "dns" if resolved_ip else "ping"
            ns.update_metrics(node.id, NodeMetricsUpdate(
                status="online", last_verified=now, verification_source=source,
                latency_ms=result["latency_ms"],
            ))
            lat = f" ({result['latency_ms']:.0f}ms)" if result["latency_ms"] else ""
            return _make_result(
                True, "verify_node", node.name,
                f"{node.name} verified via {source.upper()}{lat}",
                {"name": node.name, "status": "online", "verification_source": source,
                 "last_verified": now, "latency_ms": result["latency_ms"]},
                None,
            )

    # All methods failed
    ns.update_metrics(node.id, NodeMetricsUpdate(status="offline"))
    tried = []
    if node.agent_url:
        tried.append("Silvia-Agent")
    if node.tailscale_ip:
        tried.append("Tailscale")
    if node.hostname:
        tried.append("DNS/Ping")
    reason = (
        f"Tried: {', '.join(tried)}. All unreachable."
        if tried
        else "No connectivity options configured (no hostname, Tailscale IP, or agent URL)."
    )
    return _make_result(
        False, "verify_node", node.name,
        f"{node.name} — unreachable",
        {"name": node.name, "status": "offline", "verification_source": None,
         "last_verified": None, "error": reason},
        reason,
    )


async def verify_all_nodes() -> dict:
    """Verify every registered node sequentially and return a summary."""
    from backend.app.services.node_service import NodeService

    ns = NodeService()
    nodes = ns.list_nodes()
    results = []
    for node in nodes:
        r = await verify_node_by_name(node.name)
        results.append(r)

    verified = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    return _make_result(
        True, "refresh_nodes", None,
        f"Verified {len(verified)}/{len(nodes)} — {len(failed)} unreachable",
        {
            "results": [r["data"] for r in results if r.get("data")],
            "verified_count": len(verified),
            "failed_count": len(failed),
            "total": len(nodes),
        },
        None,
    )


def get_watch_alerts() -> dict:
    """Return all active (non-dismissed) Watch Officer alerts."""
    from backend.app.services.watch_service import WatchService
    ws = WatchService()
    alerts = ws.list_alerts(include_dismissed=False)
    return _make_result(
        True, "get_watch_alerts", None,
        f"{len(alerts)} active alert{'s' if len(alerts) != 1 else ''}",
        {"alerts": [a.model_dump() for a in alerts], "count": len(alerts)},
        None,
    )


def delete_node_by_name(name: str) -> dict:
    from backend.app.services.node_service import NodeService
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "delete_node", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'.",
        )
    if node.id == "workstation":
        return _make_result(
            False, "delete_node", node.name,
            "Cannot delete the workstation — it is the primary SILVIA host node.",
            None,
            "Workstation node is protected.",
        )
    ns = NodeService()
    ok = ns.delete_node(node.id)
    deleted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _make_result(
        ok, "delete_node", node.name,
        f"Deleted node '{node.name}' from registry at {deleted_at}." if ok else f"Failed to delete '{node.name}'.",
        {"node_id": node.id, "node_name": node.name, "deleted_at": deleted_at} if ok else None,
        None if ok else "Delete failed.",
    )


def merge_nodes(source_name: str, target_name: str) -> dict:
    """Merge source node into target: source's identity becomes an alias, source is deleted."""
    source = _find_node(source_name)
    target = _find_node(target_name)
    if not source:
        return _make_result(False, "merge_nodes", source_name,
            f"Source node '{source_name}' not found. Use 'list nodes' to see the registry.",
            None, f"'{source_name}' not found.")
    if not target:
        return _make_result(False, "merge_nodes", target_name,
            f"Target node '{target_name}' not found. Use 'list nodes' to see the registry.",
            None, f"'{target_name}' not found.")
    if source.id == "workstation":
        return _make_result(False, "merge_nodes", source_name,
            "Cannot merge the workstation node — it is the primary SILVIA host.",
            None, "Workstation is protected.")
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    ok, msg = ns.merge_nodes(source.id, target.id)
    return _make_result(
        ok, "merge_nodes", target.name,
        msg,
        {"merged_from": source.name, "merged_into": target.name,
         "source_id": source.id, "target_id": target.id} if ok else None,
        None if ok else msg,
    )


def find_duplicate_nodes() -> dict:
    """Scan the node registry for duplicate entries sharing the same IP or hostname."""
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    dupes = ns.find_duplicate_nodes()
    if not dupes:
        return _make_result(
            True, "find_duplicate_nodes", None,
            "No duplicates found — node registry is clean.",
            {"duplicates": [], "count": 0}, None,
        )
    lines = [f"  - '{d['source']}' and '{d['target']}' (shared IP: {d['shared_ip'] or d['shared_hostname']})" for d in dupes]
    summary = f"Found {len(dupes)} duplicate pair{'s' if len(dupes) != 1 else ''}:\n" + "\n".join(lines)
    return _make_result(
        True, "find_duplicate_nodes", None,
        summary,
        {"duplicates": dupes, "count": len(dupes)},
        None,
    )


# ── Robotics tools ────────────────────────────────────────────────────────────

_ROBOTICS_TYPES = {"drone", "robot", "esp32", "sensor-network"}

_SAFE_COMMANDS = {
    "reboot", "restart_service", "emergency_stop",
    "arm", "disarm", "land", "home",
}
_DESTRUCTIVE_COMMANDS = {"arm", "disarm", "emergency_stop", "reboot", "land"}


def list_nodes_by_type(node_type: str) -> dict:
    """List nodes of a specific type (drone, robot, esp32, sensor-network, etc.)."""
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    nodes = ns.list_nodes_by_type(node_type)
    if not nodes:
        return _make_result(
            True, "list_nodes_by_type", None,
            f"No {node_type} nodes registered.",
            {"type": node_type, "nodes": [], "count": 0},
            None,
        )
    data = [_node_metrics_dict(n) for n in nodes]
    return _make_result(
        True, "list_nodes_by_type", None,
        f"{len(nodes)} {node_type} node{'s' if len(nodes) != 1 else ''} registered",
        {"type": node_type, "nodes": data, "count": len(nodes)},
        None,
    )


async def send_node_command(node_name: str, command: str, payload: dict | None = None) -> dict:
    """
    Send a command to a node via its silvia-agent.
    Returns result dict. Raises no exceptions — all errors captured.
    """
    import httpx

    command = command.strip().lower()
    if command not in _SAFE_COMMANDS:
        return _make_result(
            False, "send_node_command", node_name,
            f"Unknown command '{command}'.",
            None,
            f"Command '{command}' is not in the allowed set: {sorted(_SAFE_COMMANDS)}",
        )

    node = _find_node(node_name)
    if not node:
        return _make_result(
            False, "send_node_command", node_name,
            f"Node '{node_name}' not found in registry.",
            None,
            f"No node named '{node_name}'.",
        )

    if not node.agent_url:
        return _make_result(
            False, "send_node_command", node.name,
            f"{node.name} has no silvia-agent configured — cannot send commands.",
            None,
            "No agent_url on this node.",
        )

    url = node.agent_url.rstrip("/") + "/command"
    body = {"command": command, "payload": payload or {}}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
        result_data = resp.json()
        ok = result_data.get("ok", False)
        message = result_data.get("message") or result_data.get("error") or ""
        return _make_result(
            ok, "send_node_command", node.name,
            f"{node.name}: {message}" if message else f"Command '{command}' sent to {node.name}.",
            result_data,
            None if ok else result_data.get("error", "Command failed"),
        )
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        return _make_result(
            False, "send_node_command", node.name,
            f"Command rejected: {detail or exc.response.status_code}",
            None,
            detail or str(exc),
        )
    except Exception as exc:
        return _make_result(
            False, "send_node_command", node.name,
            f"Could not reach {node.name}: {type(exc).__name__}",
            None,
            str(exc),
        )
