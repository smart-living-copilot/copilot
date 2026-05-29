import pytest
from fastapi import FastAPI

from copilot.config import get_settings
from copilot.database import get_engine, get_session_factory
from copilot.lifecycle import start_backend_runtime


@pytest.mark.anyio
async def test_backend_startup_requires_openai_search_settings(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "REGISTRY_DATABASE_URL",
        f"sqlite:///{tmp_path / 'backend-test.db'}",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    settings = get_settings()
    app = FastAPI()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY, OPENAI_MODEL"):
        await start_backend_runtime(
            app,
            settings=settings,
            session_factory=get_session_factory(),
        )


@pytest.mark.anyio
async def test_backend_startup_requires_runtime_security_tokens(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "REGISTRY_DATABASE_URL",
        f"sqlite:///{tmp_path / 'backend-test.db'}",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.delenv("WOT_RUNTIME_REGISTRY_TOKEN", raising=False)
    monkeypatch.delenv("WOT_RUNTIME_API_TOKEN", raising=False)

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    settings = get_settings()
    app = FastAPI()

    with pytest.raises(
        RuntimeError,
        match="WOT_RUNTIME_REGISTRY_TOKEN, WOT_RUNTIME_API_TOKEN",
    ):
        await start_backend_runtime(
            app,
            settings=settings,
            session_factory=get_session_factory(),
        )
