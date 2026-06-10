from pathlib import Path


def test_compose_defines_rdf_service_with_persistent_store_and_shared_event_stream():
    compose = Path("deploy/compose.yaml").read_text()

    assert "rdf-service:" in compose
    assert 'command: ["copilot", "rdf-service"]' in compose
    assert "rdf-data:/data/rdf" in compose
    assert 'RDF_STORE_PATH: "/data/rdf"' in compose
    assert "RDF_FEDERATION_PROXY_BASE_URL" in compose
    assert "RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS" in compose
    assert "redis://valkey:6379" in compose
    assert "rdf-data:" in compose


def test_env_template_defines_rdf_settings():
    env_template = Path(".env.example").read_text()

    assert "THING_EVENTS_STREAM=thing_events" in env_template
    assert "RDF_SERVICE_URL=http://rdf-service:8124" in env_template
    assert "RDF_STORE_PATH=/data/rdf" in env_template
    assert "RDF_EVENTS_GROUP=thing_rdf_indexer" in env_template
    assert "RDF_FEDERATION_PROXY_BASE_URL=http://localhost:8124" in env_template
    assert "RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS=false" in env_template
