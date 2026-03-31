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

ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT = [
    HumanMessage(
        content=(
            "Show me the energy consumption of household 5 from 20.03.2027 3am "
            "for 3h. Use all NILM services to disaggregate it."
        )
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "things_search",
                "args": {"query": "household 5 main meter energy consumption", "k": 3},
                "id": "fs_b1",
            }
        ],
    ),
    ToolMessage(
        content='[{"id":"urn:uuid:meter-05","title":"Smart Meter House 5"}]',
        tool_call_id="fs_b1",
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
                "id": "fs_b2",
            }
        ],
    ),
    ToolMessage(
        content=(
            '{"output":{"type":"array","items":{"properties":'
            '{"ts":{"type":"integer"},"power":{"type":"number"}}}},'
            '"uriVariables":{"from":{"type":"integer"},"to":{"type":"integer"}}}'
        ),
        tool_call_id="fs_b2",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "things_search",
                "args": {"query": "household 5 NILM disaggregation services", "k": 10},
                "id": "fs_b3",
            }
        ],
    ),
    ToolMessage(
        content=(
            '[{"id":"urn:uuid:nilm-kitchen-05","title":"House 5 NILM Kitchen"},'
            '{"id":"urn:uuid:nilm-laundry-05","title":"House 5 NILM Laundry"}]'
        ),
        tool_call_id="fs_b3",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_get_action",
                "args": {
                    "thing_id": "urn:uuid:nilm-kitchen-05",
                    "action_name": "get_disaggregation_history",
                },
                "id": "fs_b4",
            }
        ],
    ),
    ToolMessage(
        content=(
            '{"output":{"type":"array","items":{"properties":'
            '{"ts":{"type":"integer"},"power":{"type":"number"},'
            '"label":{"type":"string"}}}},'
            '"uriVariables":{"from":{"type":"integer"},"to":{"type":"integer"}}}'
        ),
        tool_call_id="fs_b4",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "wot_get_action",
                "args": {
                    "thing_id": "urn:uuid:nilm-laundry-05",
                    "action_name": "get_disaggregation_history",
                },
                "id": "fs_b5",
            }
        ],
    ),
    ToolMessage(
        content=(
            '{"output":{"type":"array","items":{"properties":'
            '{"ts":{"type":"integer"},"power":{"type":"number"},'
            '"label":{"type":"string"}}}},'
            '"uriVariables":{"from":{"type":"integer"},"to":{"type":"integer"}}}'
        ),
        tool_call_id="fs_b5",
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_code",
                "args": {
                    "code": (
                        "import pandas as pd, plotly.express as px\n"
                        "from_ts = 1805511600000\n"
                        "to_ts = 1805522400000\n"
                        "meter_rows = wot.invoke_action('urn:uuid:meter-05',"
                        "'get_power_history', uri_variables={'from': from_ts, 'to': to_ts})\n"
                        "meter_df = pd.DataFrame(meter_rows)\n"
                        "meter_df['time'] = pd.to_datetime(meter_df['ts'], unit='ms')\n"
                        "services = [\n"
                        "    ('urn:uuid:nilm-kitchen-05', 'Kitchen'),\n"
                        "    ('urn:uuid:nilm-laundry-05', 'Laundry'),\n"
                        "]\n"
                        "frames = []\n"
                        "for thing_id, fallback_label in services:\n"
                        "    rows = wot.invoke_action(\n"
                        "        thing_id,\n"
                        "        'get_disaggregation_history',\n"
                        "        uri_variables={'from': from_ts, 'to': to_ts},\n"
                        "    )\n"
                        "    frame = pd.DataFrame(rows)\n"
                        "    if frame.empty:\n"
                        "        continue\n"
                        "    if 'label' in frame:\n"
                        "        frame['component'] = frame['label'].fillna(fallback_label)\n"
                        "    else:\n"
                        "        frame['component'] = fallback_label\n"
                        "    frame['time'] = pd.to_datetime(frame['ts'], unit='ms')\n"
                        "    frames.append(frame[['time', 'power', 'component']])\n"
                        "disagg_df = (\n"
                        "    pd.concat(frames, ignore_index=True)\n"
                        "    if frames else pd.DataFrame(columns=['time', 'power', 'component'])\n"
                        ")\n"
                        "meter_avg = meter_df['power'].mean() if not meter_df.empty else 0\n"
                        "parts = []\n"
                        "if not disagg_df.empty:\n"
                        "    part_avg = disagg_df.groupby('component')['power'].mean()"
                        ".sort_values(ascending=False)\n"
                        "    parts = [f'{name} {value:.0f} W' for name, value in part_avg.items()]\n"
                        "print(\n"
                        "    'Window 2027-03-20 03:00 to 06:00. '\n"
                        "    f'Average household load {meter_avg:.0f} W. '\n"
                        "    + ('NILM components: ' + ', '.join(parts) if parts else "
                        "'No NILM components returned.')\n"
                        ")\n"
                        "if disagg_df.empty:\n"
                        "    fig = px.line(\n"
                        "        meter_df,\n"
                        "        x=meter_df['time'].astype(str),\n"
                        "        y='power',\n"
                        "        title='Household 5 load (2027-03-20 03:00-06:00)',\n"
                        "    )\n"
                        "else:\n"
                        "    fig = px.area(\n"
                        "        disagg_df,\n"
                        "        x=disagg_df['time'].astype(str),\n"
                        "        y='power',\n"
                        "        color='component',\n"
                        "        title='Household 5 NILM disaggregation (2027-03-20 03:00-06:00)',\n"
                        "    )\n"
                        "fig.show()"
                    )
                },
                "id": "fs_b6",
            }
        ],
    ),
    ToolMessage(
        content=json.dumps(
            {
                "stdout": (
                    "Window 2027-03-20 03:00 to 06:00. Average household load 910 W. "
                    "NILM components: Kitchen 320 W, Laundry 180 W"
                ),
                "artifacts": [
                    {
                        "ref": "chart_1",
                        "kind": "plotly",
                        "filename": "def456.json",
                    }
                ],
            }
        ),
        tool_call_id="fs_b6",
    ),
    AIMessage(
        content=(
            "I pulled the 2027-03-20 03:00 to 06:00 window for Household 5, "
            "queried every discovered NILM service, and combined their "
            "disaggregation output. The average total household load was about "
            "910 W, with Kitchen around 320 W and Laundry around 180 W. "
            "The chart above shows the disaggregated load over the full 3-hour window."
        )
    ),
]

ANALYSIS_FEW_SHOTS = [
    *ANALYSIS_POWER_HISTORY_FEW_SHOT,
    *ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT,
]
