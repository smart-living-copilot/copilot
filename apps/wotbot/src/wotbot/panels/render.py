"""Shared document wrapper for generated WoT mini-interfaces.

Both ephemeral panels (the ``create_web_interface`` tool) and pinned panels
(the ``panels`` resource render route) wrap the agent's raw body markup into a
standalone document here. The ``window.wot`` bridge is inlined rather than loaded
via ``<script src>`` because the panel runs in an opaque (sandboxed) origin where
CSP ``'self'`` does not match, and inlining keeps pinned panels self-contained.
"""

from __future__ import annotations

import html as html_lib
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def _bridge_source() -> str:
    return resources.files("wotbot.panels").joinpath("wot_bridge.js").read_text(encoding="utf-8")


def wrap_panel_document(body_html: str, title: str = "") -> str:
    """Wrap agent-authored body markup into a full panel document.

    The injected bridge exposes ``window.wot`` for device interaction; the panel
    talks only to the parent via postMessage (see wot_bridge.js).
    """
    safe_title = html_lib.escape(title or "Interface")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<script>{_bridge_source()}</script>\n"
        "</head>\n"
        f"<body>\n{body_html}\n</body>\n"
        "</html>\n"
    )
