import pytest
from fastapi import FastAPI

from copilot.core.config import get_settings
from copilot.core.database import get_connection_pool
from copilot.core.lifecycle import start_backend_runtime


def test_postgresql_psycopg_url_is_normalized(monkeypatch):
    monkeypatch.setenv(
        "REGISTRY_DATABASE_URL",
        "postgresql+psycopg://copilot:copilot@postgres:5432/copilot",
    )

    get_settings.cache_clear()

    assert (
        get_settings().DATABASE_URL
        == "postgresql://copilot:copilot@postgres:5432/copilot"
    )


@pytest.mark.anyio
async def test_backend_startup_requires_runtime_security_tokens(monkeypatch):
    monkeypatch.setenv(
        "REGISTRY_DATABASE_URL",
        "postgresql://copilot:copilot@localhost:5432/copilot",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.delenv("WOT_RUNTIME_REGISTRY_TOKEN", raising=False)
    monkeypatch.delenv("WOT_RUNTIME_API_TOKEN", raising=False)

    get_settings.cache_clear()
    get_connection_pool.cache_clear()

    settings = get_settings()
    app = FastAPI()

    with pytest.raises(
        RuntimeError,
        match="WOT_RUNTIME_REGISTRY_TOKEN, WOT_RUNTIME_API_TOKEN",
    ):
        await start_backend_runtime(
            app,
            settings=settings,
            connection_pool=object(),  # type: ignore[arg-type]
        )
