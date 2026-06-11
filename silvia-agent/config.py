"""Configuration — all values overridable via environment variables."""
import os

NODE_NAME: str = os.getenv("AGENT_NODE_NAME", "unknown-node")
NODE_TYPE: str = os.getenv("AGENT_NODE_TYPE", "custom")
NODE_ROLE: str = os.getenv("AGENT_NODE_ROLE", "")
AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8765"))
AGENT_HOST: str = os.getenv("AGENT_HOST", "0.0.0.0")
AGENT_VERSION: str = "1.0.0"
