"""Code execution service package.

This package hosts the FastAPI-backed execution service used by copilot for
running user-authored, generated, job, and virtual Thing handler Python in
dedicated session processes. It is the service boundary that
``CodeExecutorClient`` targets for async code evaluation and artifact retrieval.
"""
