"""Code execution service package.

This package hosts the FastAPI-backed execution service used by copilot for
running user-authored or generated Python safely in a dedicated process.
It is the service boundary that `CodeExecutorClient` targets for async code
evaluation and artifact retrieval.
"""
