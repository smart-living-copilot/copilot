"""API entrypoint boundary for the code execution service.

This package exposes the application object lazily as ``app`` so importing the
package does not eagerly construct the FastAPI application before runtime
configuration is ready. It keeps public imports explicit through ``__all__``.
"""


def __getattr__(name: str):
    if name == "app":
        from code_executor.api.app import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app"]
