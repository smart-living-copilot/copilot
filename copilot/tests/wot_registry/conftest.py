import pytest

from copilot.core.config import get_settings
from copilot.core.database import get_engine, get_session_factory
from copilot.search import set_active_search_service
from copilot.things.schema import load_td_schema


class StubSearchService:
    async def search(self, query: str, k: int = 5) -> list[dict[str, object]]:
        return [
            {
                "id": "urn:thing:search-stub",
                "title": f"Stub result for {query}",
                "description": "Stubbed semantic search result",
                "tags": ["stub"],
                "score": 1.0,
                "summary": f"Matched with k={k}",
            }
        ]

    async def get_index_status(
        self,
        thing_id: str,
        document_hash: str,
    ) -> dict[str, object]:
        return {
            "thing_id": thing_id,
            "indexed": True,
            "stale": False,
            "indexed_at": "2026-03-16T00:00:00+00:00",
            "summary_source": "stub",
            "summary_model": "stub-model",
            "prompt_version": "v-test",
            "td_hash_match": bool(document_hash),
            "summary": "Stubbed semantic summary",
            "location_candidates": ["Kitchen"],
            "property_names": ["temperature"],
            "action_names": ["toggle"],
            "event_names": ["overheated"],
        }

    @property
    def vector_store(self):
        return None

    async def close(self) -> None:
        return None


INIT_ADMIN_TOKEN = "test-init-admin-token"


@pytest.fixture(autouse=True)
def clear_backend_state(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "REGISTRY_DATABASE_URL",
        f"sqlite:///{tmp_path / 'backend-test.db'}",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("INIT_ADMIN_TOKEN", INIT_ADMIN_TOKEN)
    monkeypatch.setenv("REGISTRY_PUBLIC_URL", "http://testserver")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("WOT_RUNTIME_REGISTRY_TOKEN", "test-runtime-registry-token")
    monkeypatch.setenv("WOT_RUNTIME_API_TOKEN", "test-runtime-api-token")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    load_td_schema.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    load_td_schema.cache_clear()


@pytest.fixture(autouse=True)
def stub_search_runtime(monkeypatch):
    def fake_start_search_service(app, *, settings):
        service = StubSearchService()
        app.state.search_service = service
        set_active_search_service(service)

    async def fake_stop_search_service(app):
        app.state.search_service = None
        set_active_search_service(None)

    async def fake_start_search_indexer(app, *, settings, vector_store=None):
        app.state.search_indexer_consumer = object()

    async def fake_stop_search_indexer(app):
        app.state.search_indexer_consumer = None

    monkeypatch.setattr(
        "copilot.core.lifecycle.start_search_service", fake_start_search_service
    )
    monkeypatch.setattr(
        "copilot.core.lifecycle.stop_search_service", fake_stop_search_service
    )
    monkeypatch.setattr(
        "copilot.core.lifecycle.start_search_indexer", fake_start_search_indexer
    )
    monkeypatch.setattr(
        "copilot.core.lifecycle.stop_search_indexer", fake_stop_search_indexer
    )
    set_active_search_service(None)
    yield
    set_active_search_service(None)


@pytest.fixture
def authenticated_headers():
    return {"Authorization": f"Bearer {INIT_ADMIN_TOKEN}"}
