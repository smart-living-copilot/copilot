"""Internal service clients.

This package exports async clients for copilot dependencies, including the code
executor service and the WoT runtime gateway. These clients are used by agent
nodes and worker paths to isolate transport concerns.
"""

from copilot.clients.code_executor import CodeExecutorClient
from copilot.clients.wot_runtime import WotRuntimeClient

__all__ = ["CodeExecutorClient", "WotRuntimeClient"]
