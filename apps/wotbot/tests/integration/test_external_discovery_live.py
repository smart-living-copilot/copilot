from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import text

from wotbot.core.database import get_session_factory
from wotbot.core.settings import Settings
from wotbot.discovery.http import BoundedHttpClient
from wotbot.discovery.service import DiscoveryService
from wotbot.discovery.store import DownloadStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        os.environ.get("RUN_EXTERNAL_DISCOVERY_TESTS") != "1",
        reason="set RUN_EXTERNAL_DISCOVERY_TESTS=1 to run the Luxembourg lifecycle smoke test",
    ),
]


def test_luxembourg_source_registry_lifecycle(jobs_integration_environment) -> None:
    async def smoke() -> None:
        settings = Settings()
        service = DiscoveryService(settings)
        thread_id = "luxembourg-source-smoke"

        registered = await service.register_source_url(
            source="https://data.public.lu/en/",
        )
        assert registered.get("unsupported_source") is not True
        source = registered["source"]
        assert source["provider"] == "udata"
        found = await service.search_sources(query="Luxembourg", limit=10)
        assert any(item["source_id"] == source["source_id"] for item in found["items"])

        discovered: dict[str, Any] | None = None
        for query in ("GTFS", "transport", "mobility", "Luxembourg"):
            response = await service.discover(
                source_id=source["source_id"],
                query=query,
                limit=25,
                thread_id=thread_id,
            )
            if response.get("items"):
                discovered = response
                break
        assert discovered is not None, "Luxembourg source returned no dataset candidates"

        errors: list[str] = []
        for candidate in discovered["items"]:
            try:
                onboarded = await service.onboard(
                    candidate_id=candidate["candidate_id"],
                    thread_id=thread_id,
                )
                resource = onboarded["thing"]
                # The onboarding summary omits the document by design, so the
                # action names come from the affordance summary it does carry.
                # Reading "document" here silently yielded no actions, which is
                # why this loop never ran and the download path went untested.
                actions = resource["affordances"]["actions"]["names"]
                for action_name in actions:
                    capability = await service.invoke_thing_action(
                        thing_id=resource["id"],
                        action=action_name,
                        input_data=None,
                    )
                    handle = str(capability["download_url"]).rsplit("/", 1)[-1]
                    record = await DownloadStore(
                        settings.redis_url,
                        ttl_seconds=settings.discovery_download_ttl_seconds,
                    ).get(handle)
                    session, response = await BoundedHttpClient(max_requests=None).stream(
                        record.endpoint,
                        headers=record.headers,
                    )
                    try:
                        if 200 <= response.status < 300:
                            assert await response.content.read(64)
                            return
                        errors.append(f"{action_name}: HTTP {response.status}")
                    finally:
                        response.release()
                        await session.close()
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(str(exc))
        pytest.fail("No discovered Luxembourg distribution returned bytes: " + "; ".join(errors))

    with get_session_factory()() as session:
        session.execute(
            text(
                "TRUNCATE things, discovery_source_credentials, discovery_sources, "
                "thing_event_outbox CASCADE"
            )
        )
        session.commit()
    asyncio.run(smoke())
