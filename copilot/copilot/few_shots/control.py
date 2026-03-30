"""Few-shot examples for the control branch."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

CONTROL_TURN_ON_LIGHT_FEW_SHOT = [
    HumanMessage(content="Turn on the desk lamp in the office."),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "things_search",
                "args": {"query": "desk lamp office", "k": 3},
                "id": "fs_c1",
            }
        ],
    ),
    ToolMessage(
        content='[{"id":"urn:uuid:office-lamp","title":"Office Desk Lamp"}]',
        tool_call_id="fs_c1",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_get_action",
                "args": {
                    "thing_id": "urn:uuid:office-lamp",
                    "action_name": "set_power",
                },
                "id": "fs_c2",
            }
        ],
    ),
    ToolMessage(
        content=(
            '{"input":{"type":"object","properties":{"state":{"type":"string",'
            '"enum":["on","off"]}}},"uriVariables":{}}'
        ),
        tool_call_id="fs_c2",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_invoke_action",
                "args": {
                    "thing_id": "urn:uuid:office-lamp",
                    "action_name": "set_power",
                    "input": {"state": "on"},
                    "uri_variables": {},
                },
                "id": "fs_c3",
            }
        ],
    ),
    ToolMessage(content='{"status":"ok"}', tool_call_id="fs_c3"),
    AIMessage(content="The office desk lamp is now on."),
]

CONTROL_UNLOCK_CONFIRMATION_FEW_SHOT = [
    HumanMessage(content="Unlock the front door."),
    AIMessage(
        content=(
            "Unlocking the front door affects home security. "
            "Please confirm that you want me to unlock it."
        )
    ),
    HumanMessage(content="Yes, unlock it."),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "things_search",
                "args": {"query": "front door lock", "k": 3},
                "id": "fs_c4",
            }
        ],
    ),
    ToolMessage(
        content='[{"id":"urn:uuid:front-door-lock","title":"Front Door Lock"}]',
        tool_call_id="fs_c4",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_get_action",
                "args": {
                    "thing_id": "urn:uuid:front-door-lock",
                    "action_name": "unlock",
                },
                "id": "fs_c5",
            }
        ],
    ),
    ToolMessage(
        content='{"input":{"type":"null"},"uriVariables":{}}',
        tool_call_id="fs_c5",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_invoke_action",
                "args": {
                    "thing_id": "urn:uuid:front-door-lock",
                    "action_name": "unlock",
                    "uri_variables": {},
                },
                "id": "fs_c6",
            }
        ],
    ),
    ToolMessage(content='{"status":"ok"}', tool_call_id="fs_c6"),
    AIMessage(content="The front door is now unlocked."),
]

CONTROL_FEW_SHOTS = [
    *CONTROL_TURN_ON_LIGHT_FEW_SHOT,
    *CONTROL_UNLOCK_CONFIRMATION_FEW_SHOT,
]
