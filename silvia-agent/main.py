"""
silvia-agent — lightweight node protocol for the SILVIA ecosystem.

Deploy on any node: Raspberry Pi, VPS, workstation, cyberdeck.
Exposes identity, telemetry, services, and capabilities over HTTP.

Usage:
    pip install -r requirements.txt
    AGENT_NODE_NAME=pi5 AGENT_NODE_TYPE=raspberry-pi python main.py

Endpoints:
    GET  /status        identity + summary health
    GET  /telemetry     cpu, ram, disk, temperature, uptime
    GET  /services      detected running services
    GET  /capabilities  what this node supports
    POST /command       501 Not Implemented (reserved for future)
"""
import socket

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

import capabilities as caps_module
import config
import services as svc_module
import telemetry as tel_module

app = FastAPI(
    title="silvia-agent",
    description="SILVIA node protocol — telemetry and capability reporting.",
    version=config.AGENT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


@app.get("/status")
async def status():
    tel = tel_module.collect()
    return {
        "node": config.NODE_NAME,
        "type": config.NODE_TYPE,
        "role": config.NODE_ROLE or None,
        "hostname": _hostname(),
        "version": config.AGENT_VERSION,
        "status": "online",
        "telemetry": {
            "cpu": tel["cpu"],
            "ram": tel["ram"],
            "disk": tel["disk"],
            "temperature": tel["temperature"],
            "uptime": tel["uptime"],
        },
        "capabilities": caps_module.detect(),
    }


@app.get("/telemetry")
async def telemetry():
    return tel_module.collect()


@app.get("/services")
async def services():
    return {"services": svc_module.detect()}


@app.get("/capabilities")
async def capabilities():
    return {"capabilities": caps_module.detect()}


@app.post("/command")
async def command(response: Response):
    response.status_code = 501
    return {
        "ok": False,
        "error": "Command execution not implemented in this version.",
        "reserved": True,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.AGENT_HOST,
        port=config.AGENT_PORT,
        log_level="info",
    )
