"""Persistent generative WoT panels (pinned mini-interfaces).

Exposes the shared document wrapper used by both ephemeral panels (the
``create_web_interface`` tool) and pinned panels (the ``panels`` resource).
"""

from wotbot.panels.render import wrap_panel_document

__all__ = ["wrap_panel_document"]
