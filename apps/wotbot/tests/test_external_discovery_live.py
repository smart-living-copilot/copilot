import asyncio
import os

import pytest

from wotbot.discovery.providers import resolve_public_source


@pytest.mark.external
@pytest.mark.skipif(
    os.environ.get("RUN_EXTERNAL_DISCOVERY_TESTS") != "1",
    reason="set RUN_EXTERNAL_DISCOVERY_TESTS=1 to probe the public portal",
)
def test_data_public_lu_is_discovered_without_catalog_side_effects() -> None:
    source, evidence, supported = asyncio.run(resolve_public_source("https://data.public.lu/en/"))

    assert supported
    assert source is not None
    assert source.provider == "udata"
    assert source.external_id == "https://data.public.lu"
    assert evidence
