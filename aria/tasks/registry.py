"""Tool definitions exposed to the voice model.

Phase 0 has a single tool. The schema follows the OpenAI-Realtime function
format, which the Grok Voice Agent API is compatible with.
"""

from __future__ import annotations

READ_DASHBOARD_TOOL = {
    "type": "function",
    "name": "read_dashboard",
    "description": (
        "Open the user's dashboard in the web browser and read the top of the "
        "page aloud. Call this whenever the user asks to open their dashboard "
        "(or a page) and have its contents read back to them. This runs in the "
        "background and is read-only — it never sends, buys, or deletes anything."
    ),
    # No parameters: the dashboard URL comes from configuration in Phase 0.
    "parameters": {"type": "object", "properties": {}, "required": []},
}

TOOLS = [READ_DASHBOARD_TOOL]
