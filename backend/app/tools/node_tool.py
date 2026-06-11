"""Node registry tools — lookup, probe, update, delete, SSH."""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Optional

_SAFE_USERNAME = re.compile(r"^[a-zA-Z0-9_.\-]{1,64}$")
_SAFE_HOST = re.compile(r"^[a-zA-Z0-9_.\-]{1,253}$")


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


def open_ssh_session(name: str, username: str) -> dict:
    node = _find_node(name)
    if not node:
        return _make_result(
            False, "ssh_node", name,
            f"Node '{name}' not found in registry.",
            None,
            f"No node named '{name}'. Use 'list nodes' to see registered nodes.",
        )

    ip, source = _ip_source(node)
    host = ip or node.hostname or ""
    if not host or host == "local":
        return _make_result(
            False, "ssh_node", node.name,
            f"No reachable address on record for {node.name}.",
            None,
            f"No IP or hostname configured for '{node.name}'. Add one first.",
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

    ssh_cmd = f"ssh {username}@{host}"
    title = f"SSH: {node.name}"

    try:
        if shutil.which("wt"):
            subprocess.Popen(
                ["wt", "new-tab", "--title", title, "cmd.exe", "/k", ssh_cmd],
                creationflags=subprocess.DETACHED_PROCESS,
            )
        else:
            subprocess.Popen(
                ["cmd.exe", "/k", ssh_cmd],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
    except Exception as exc:
        return _make_result(
            False, "ssh_node", node.name,
            f"Failed to open terminal: {exc}",
            None,
            str(exc),
        )

    return _make_result(
        True, "ssh_node", node.name,
        f"Opened SSH terminal -> {node.name} ({username}@{host}, source: {source})",
        {"host": host, "username": username, "source": source, "command": ssh_cmd},
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
        {"deleted_at": deleted_at} if ok else None,
        None if ok else "Delete failed.",
    )
