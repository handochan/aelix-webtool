from __future__ import annotations

import json

import pytest

from aelix_webtool import setup
from aelix_webtool.errors import WebToolError
from aelix_webtool.network import HttpResponse

pytest.importorskip("aelix_coding_agent")

from aelix_ai.tools import ToolExecutionContext, validate_tool_arguments
from aelix_coding_agent.extensions.loader import load_extensions
from aelix_coding_agent.tools._abort import AbortSignal


async def test_actual_host_loader_registers_tools_and_command_without_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("loading the extension performed network I/O")

    monkeypatch.setattr("aelix_webtool.network.HttpClient.request", forbidden)
    result = await load_extensions([setup])
    assert not result.errors
    extension = result.extensions[0]
    assert set(extension.tools) == {"web_search", "web_fetch", "web_read", "web_find"}
    assert set(extension.commands) == {"web"}
    assert "Aelix Web Tools" in extension.commands["web"].handler("status", None)


async def test_host_dispatch_receives_success_and_structured_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fixture-key")
    monkeypatch.setenv("AELIX_WEB_PROVIDER", "tavily")
    monkeypatch.delenv("AELIX_WEB_OFFLINE", raising=False)

    async def request(_self, method, url, **kwargs):
        body = {
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com/guide",
                    "content": "Actual schema dispatched.",
                }
            ]
        }
        return HttpResponse(url, 200, "application/json", "utf-8", json.dumps(body).encode())

    monkeypatch.setattr("aelix_webtool.network.HttpClient.request", request)
    loaded = await load_extensions([setup])
    tool = loaded.extensions[0].tools["web_search"]
    args = await validate_tool_arguments(tool, {"query": "aelix", "max_results": "5"})
    result = await tool.execute(args, ToolExecutionContext(tool_call_id="host-test"))
    assert not result.is_error
    assert result.details["provider"] == "tavily"
    assert "https://example.com/guide" in result.content[0].text

    async def failure(*args, **kwargs):
        raise WebToolError("rate_limit", "Rate limit", retryable=True)

    monkeypatch.setattr("aelix_webtool.network.HttpClient.request", failure)
    error = await tool.execute(args, ToolExecutionContext())
    assert error.is_error and error.details["error"]["code"] == "rate_limit"


async def test_real_host_abort_signal_is_preserved():
    loaded = await load_extensions([setup])
    signal = AbortSignal()
    signal.abort()
    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await (
            loaded.extensions[0]
            .tools["web_fetch"]
            .execute({"url": "https://example.com"}, ToolExecutionContext(signal=signal))
        )


async def test_host_fetch_read_find_share_one_store_and_session_start_clears_it(monkeypatch):
    calls = []

    async def response(_self, *args, **kwargs):
        calls.append(args)
        return HttpResponse(
            "https://example.com/guide",
            200,
            "text/plain",
            "utf-8",
            "첫 줄\nTimeout = 10\nSource evidence.".encode(),
        )

    monkeypatch.setattr("aelix_webtool.network.HttpClient.request", response)
    extension = (await load_extensions([setup])).extensions[0]
    context = ToolExecutionContext()
    fetched = await extension.tools["web_fetch"].execute(
        {"url": "https://example.com/guide"}, context
    )
    key = fetched.details["snapshot_id"]
    read = await extension.tools["web_read"].execute({"snapshot_id": key}, context)
    found = await extension.tools["web_find"].execute(
        {"snapshot_id": key, "query": "timeout"}, context
    )
    assert not read.is_error and found.details["total_matches"] == 1
    assert found.details["matches"][0]["line_start"] == 2 and len(calls) == 1
    extension.handlers["session_start"][0]({}, None)
    missing = await extension.tools["web_read"].execute({"snapshot_id": key}, context)
    assert missing.is_error and missing.details["error"]["code"] == "snapshot_not_found"
