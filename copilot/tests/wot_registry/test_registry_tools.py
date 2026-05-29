from copilot.graph.tools.registry import REGISTRY_TOOLS, _registry_base_url, things_validate
from copilot.settings import Settings


def sample_thing(thing_id: str = "urn:thing:tool-test") -> dict[str, object]:
    return {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": thing_id,
        "title": "Tool Test Thing",
        "securityDefinitions": {
            "nosec_sc": {
                "scheme": "nosec",
            }
        },
        "security": "nosec_sc",
        "properties": {
            "temperature": {
                "type": "number",
                "forms": [{"href": "https://example.com/temperature"}],
            }
        },
    }


def test_registry_tools_include_catalog_and_runtime_tools():
    tool_names = {tool.name for tool in REGISTRY_TOOLS}

    assert "things_search" in tool_names
    assert "registry_health" in tool_names
    assert "wot_read_property" in tool_names
    assert "wot_subscribe_event" in tool_names


def test_registry_base_url_accepts_old_mcp_url_for_compatibility():
    settings = Settings(wot_registry_url="http://registry.example/mcp")

    assert _registry_base_url(settings) == "http://registry.example"


def test_things_validate_tool_returns_summary_counts():
    response = things_validate.invoke({"document": sample_thing()})

    assert response["id"] == "urn:thing:tool-test"
    assert response["property_count"] == 1
    assert response["action_count"] == 0
