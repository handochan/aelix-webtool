"""Run inside an isolated environment containing the real host and built wheel."""

from __future__ import annotations

import asyncio
import json
import tempfile
from importlib.metadata import entry_points
from pathlib import Path

from aelix_ai.tools import ToolExecutionContext, validate_tool_arguments
from aelix_coding_agent.extensions.loader import discover_and_load_extensions


async def main() -> None:
    endpoints = [ep for ep in entry_points(group="aelix.extensions") if ep.name == "aelix-webtool"]
    assert len(endpoints) == 1, "Installed extension entry point is missing or duplicated"
    with tempfile.TemporaryDirectory(prefix="webtool-discovery-") as work:
        root = Path(work)
        loaded = await discover_and_load_extensions(
            [],
            cwd=root,
            agent_dir=root / "agent",
            no_project_local=True,
        )
        assert not loaded.errors, [(e.path, e.error) for e in loaded.errors]
        extensions = [
            ext
            for ext in loaded.extensions
            if set(ext.tools) == {"web_search", "web_fetch", "web_read", "web_find"}
        ]
        assert len(extensions) == 1, "Installed wheel was not automatically loaded"
        ext = extensions[0]
        assert "Aelix Web Tools" in ext.commands["web"].handler("status", None)
        tool = ext.tools["web_fetch"]
        args = await validate_tool_arguments(tool, {"url": "http://127.0.0.1/private"})
        result = await tool.execute(
            args, ToolExecutionContext(tool_call_id="installed-wheel-smoke")
        )
        assert result.is_error and result.details["error"]["code"] == "blocked_url"
        print(
            json.dumps(
                {
                    "entry_point": endpoints[0].value,
                    "tools": sorted(ext.tools),
                    "commands": sorted(ext.commands),
                    "dispatch": "private fetch rejected before I/O",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
