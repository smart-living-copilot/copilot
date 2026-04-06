"""Graph package exports for the Smart Living Copilot."""

from typing import Any

__all__ = ["build_graph"]


def __getattr__(name: str) -> Any:
    if name == "build_graph":
        from copilot.graph.builder import build_graph

        return build_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
