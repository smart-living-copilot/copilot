"""Internal service clients used by the copilot backend."""

from copilot.clients.code_executor import CodeExecutorClient
from copilot.clients.wot_runtime import WotRuntimeClient

__all__ = ["CodeExecutorClient", "WotRuntimeClient"]
