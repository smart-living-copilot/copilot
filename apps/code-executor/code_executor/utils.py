"""Utility functions for the code executor service."""

import json


def plotly_json_to_html(fig_json: dict) -> str:
    """Convert a Plotly figure JSON dict to a standalone HTML string."""
    fig_str = json.dumps(fig_json)
    return (
        "<!DOCTYPE html>"
        '<html><head><meta charset="utf-8"/>'
        '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
        "<style>*{margin:0;padding:0}html,body{width:100%;height:100%;overflow:hidden}</style>"
        "</head><body>"
        '<div id="plot" style="width:100%;height:100%;"></div>'
        "<script>"
        f"var fig = {fig_str};"
        "var layout = Object.assign({}, fig.layout || {});"
        "delete layout.width; delete layout.height;"
        "layout.autosize = true;"
        'Plotly.newPlot("plot", fig.data, layout, {responsive: true});'
        "</script></body></html>"
    )
