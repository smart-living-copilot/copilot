"""Few-shot examples for the analysis branch."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

ANALYSIS_POWER_HISTORY_FEW_SHOT = [
    HumanMessage(content="Show me the last 24h of power consumption for house 5."),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "things_search",
                "args": {"query": "power consumption house 5", "k": 3},
                "id": "fs_a1",
            }
        ],
    ),
    ToolMessage(
        content='[{"id":"urn:uuid:meter-05","title":"Smart Meter House 5"}]',
        tool_call_id="fs_a1",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_get_action",
                "args": {
                    "thing_id": "urn:uuid:meter-05",
                    "action_name": "get_power_history",
                },
                "id": "fs_a2",
            }
        ],
    ),
    ToolMessage(
        content=(
            '{"output":{"type":"array","items":{"properties":'
            '{"ts":{"type":"integer"},"power":{"type":"number"}}}},'
            '"uriVariables":{"from":{"type":"integer"},"to":{"type":"integer"}}}'
        ),
        tool_call_id="fs_a2",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_code",
                "args": {
                    "code": (
                        "import pandas as pd, plotly.express as px\n"
                        "now_ts_ms = 1774710000000\n"
                        "from_ts = now_ts_ms - 24*60*60*1000\n"
                        "data = wot.invoke_action('urn:uuid:meter-05','get_power_history',\n"
                        "    uri_variables={'from': from_ts, 'to': now_ts_ms})\n"
                        "df = pd.DataFrame(data)\n"
                        "df['time'] = pd.to_datetime(df['ts'], unit='ms')\n"
                        "print(f'{len(df)} points, avg {df.power.mean():.0f} W')\n"
                        "fig = px.line(df, x=df['time'].astype(str), y='power',\n"
                        "    title='House 5 – Power (24h)')\n"
                        "fig.show()"
                    )
                },
                "id": "fs_a3",
            }
        ],
    ),
    ToolMessage(
        content=json.dumps(
            {
                "stdout": "1440 points, avg 720 W",
                "artifacts": [
                    {
                        "ref": "chart_1",
                        "kind": "plotly",
                        "filename": "abc123.json",
                    }
                ],
            }
        ),
        tool_call_id="fs_a3",
    ),
    AIMessage(
        content=(
            "Here's the last 24 hours of power consumption for House 5. "
            "The average was about 720 W across 1,440 data points, and the "
            "chart above shows the full hourly trend."
        )
    ),
]

ANALYSIS_FEW_SHOTS = [*ANALYSIS_POWER_HISTORY_FEW_SHOT]
