"""
silvia-agent — lightweight node protocol for the SILVIA ecosystem.

Deploy on any node: Raspberry Pi, VPS, workstation, cyberdeck, drone, robot.
Exposes identity, telemetry, services, capabilities, and command execution over HTTP.

Usage:
    pip install -r requirements.txt
    AGENT_NODE_NAME=pi5 AGENT_NODE_TYPE=raspberry-pi python main.py

Endpoints:
    GET  /status        identity + summary health
    GET  /telemetry     cpu, ram, disk, temperature, uptime + robotics fields
    GET  /services      detected running services
    GET  /capabilities  what this node supports
    POST /command       execute a command on this node (Phase 7C)
"""
import os
import socket
import subprocess
import sys

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import capabilities as caps_module
import config
import services as svc_module
import telemetry as tel_module

app = FastAPI(
    title="silvia-agent",
    description="SILVIA node protocol — telemetry, capabilities, and command execution.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Commands enabled on this node (controlled via env var AGENT_ALLOWED_COMMANDS)
_ALLOWED_COMMANDS_ENV = os.getenv("AGENT_ALLOWED_COMMANDS", "reboot,restart_service,emergency_stop")
_ALLOWED_COMMANDS = {c.strip() for c in _ALLOWED_COMMANDS_ENV.split(",") if c.strip()}

# Robotics nodes also allow these
_ROBOTICS_TYPES = {"drone", "robot", "esp32", "sensor-network"}
if config.NODE_TYPE in _ROBOTICS_TYPES:
    _ALLOWED_COMMANDS.update({"arm", "disarm", "land", "home", "emergency_stop"})


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


class CommandRequest(BaseModel):
    command: str
    payload: dict = {}


@app.get("/status")
async def status():
    tel = tel_module.collect()
    return {
        "node": config.NODE_NAME,
        "type": config.NODE_TYPE,
        "role": config.NODE_ROLE or None,
        "hostname": _hostname(),
        "version": "2.0.0",
        "status": "online",
        "telemetry": {
            "cpu": tel["cpu"],
            "ram": tel["ram"],
            "disk": tel["disk"],
            "temperature": tel["temperature"],
            "uptime": tel["uptime"],
            "battery_pct": tel.get("battery_pct"),
            "mission_state": tel.get("mission_state"),
        },
        "capabilities": caps_module.detect(),
        "allowed_commands": sorted(_ALLOWED_COMMANDS),
    }


@app.get("/telemetry")
async def telemetry():
    return tel_module.collect()


@app.get("/services")
async def services():
    return {"services": svc_module.detect()}


@app.get("/capabilities")
async def capabilities():
    return {
        "capabilities": caps_module.detect(),
        "allowed_commands": sorted(_ALLOWED_COMMANDS),
        "node_type": config.NODE_TYPE,
    }


@app.post("/command")
async def command(req: CommandRequest):
    cmd = req.command.strip().lower()

    if cmd not in _ALLOWED_COMMANDS:
        raise HTTPException(
            status_code=403,
            detail=f"Command '{cmd}' not allowed on this node. Allowed: {sorted(_ALLOWED_COMMANDS)}",
        )

    handlers = {
        "reboot":          _cmd_reboot,
        "restart_service": _cmd_restart_service,
        "emergency_stop":  _cmd_emergency_stop,
        "arm":             _cmd_arm,
        "disarm":          _cmd_disarm,
        "land":            _cmd_land,
        "home":            _cmd_home,
    }

    handler = handlers.get(cmd)
    if handler:
        return await handler(req.payload)

    return {"ok": False, "error": f"Handler not implemented for '{cmd}'"}


async def _cmd_reboot(payload: dict) -> dict:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
        else:
            subprocess.Popen(["sudo", "reboot"])
        return {"ok": True, "command": "reboot", "message": "Reboot initiated in 5 seconds."}
    except Exception as exc:
        return {"ok": False, "command": "reboot", "error": str(exc)}


async def _cmd_restart_service(payload: dict) -> dict:
    service = payload.get("service", "").strip()
    if not service:
        return {"ok": False, "command": "restart_service", "error": "No service name provided."}
    try:
        if sys.platform == "win32":
            result = subprocess.run(["sc", "stop", service], capture_output=True, text=True, timeout=10)
            subprocess.run(["sc", "start", service], capture_output=True, text=True, timeout=10)
        else:
            result = subprocess.run(["sudo", "systemctl", "restart", service],
                                    capture_output=True, text=True, timeout=10)
        ok = result.returncode == 0
        return {
            "ok": ok,
            "command": "restart_service",
            "service": service,
            "message": f"Service '{service}' restarted." if ok else result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "command": "restart_service", "error": str(exc)}


async def _cmd_emergency_stop(payload: dict) -> dict:
    # Generic emergency stop — sets AGENT_MISSION_STATE=emergency_stop
    os.environ["AGENT_MISSION_STATE"] = "emergency_stop"
    return {"ok": True, "command": "emergency_stop", "message": "Emergency stop engaged."}


async def _cmd_arm(payload: dict) -> dict:
    os.environ["AGENT_MISSION_STATE"] = "armed"
    return {"ok": True, "command": "arm", "message": f"{config.NODE_NAME} armed."}


async def _cmd_disarm(payload: dict) -> dict:
    os.environ["AGENT_MISSION_STATE"] = "idle"
    return {"ok": True, "command": "disarm", "message": f"{config.NODE_NAME} disarmed."}


async def _cmd_land(payload: dict) -> dict:
    os.environ["AGENT_MISSION_STATE"] = "landing"
    return {"ok": True, "command": "land", "message": f"{config.NODE_NAME} initiating landing."}


async def _cmd_home(payload: dict) -> dict:
    os.environ["AGENT_MISSION_STATE"] = "returning_home"
    return {"ok": True, "command": "home", "message": f"{config.NODE_NAME} returning to home position."}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.AGENT_HOST,
        port=config.AGENT_PORT,
        log_level="info",
    )
