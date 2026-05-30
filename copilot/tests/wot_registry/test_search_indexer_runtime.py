from types import SimpleNamespace

from copilot.thing_indexer.runtime import SearchIndexerStreamConfig


def test_search_indexer_stream_config_reads_settings_values():
    settings = SimpleNamespace(
        THING_EVENTS_STREAM="thing_events",
        SEARCH_INDEXER_EVENTS_GROUP="search_group",
        SEARCH_INDEXER_EVENTS_CONSUMER="consumer_a",
        SEARCH_INDEXER_BATCH_SIZE=25,
        SEARCH_INDEXER_POLL_BLOCK_MS=3000,
        SEARCH_INDEXER_CLAIM_IDLE_MS=45000,
        SEARCH_INDEXER_RETRY_SECONDS=7,
    )

    config = SearchIndexerStreamConfig.from_settings(settings)

    assert config == SearchIndexerStreamConfig(
        stream="thing_events",
        group="search_group",
        consumer="consumer_a",
        batch_size=25,
        poll_block_ms=3000,
        claim_idle_ms=45000,
        retry_seconds=7,
    )
