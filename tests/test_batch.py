from __future__ import annotations

import asyncio
import json

import pytest

from aelix_webtool import setup
from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import fetch_requests, search_requests
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService


class BatchHttp:
    timeout = 25.0

    def __init__(self):
        self.active = self.peak = self.calls = 0
        self.drained = 0

    async def request(self, method, url, **kwargs):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            query = kwargs.get("json_body", {}).get("query")
            if query == "bad" or url.endswith("/bad"):
                raise WebToolError("http_error", "503", retryable=True)
            if query is not None:
                body = json.dumps(
                    {
                        "results": [
                            {
                                "title": query,
                                "url": "https://example.com/" + query,
                                "highlights": ["source " + query],
                            }
                        ]
                    }
                ).encode()
                return HttpResponse(url, 200, "application/json", "utf-8", body)
            return HttpResponse(url, 200, "text/plain", "utf-8", b"document\n" * 1000)
        finally:
            self.active -= 1
            self.drained += 1


async def test_batch_order_partial_errors_and_concurrency_bound():
    http = BatchHttp()
    service = WebService(Config(keys={"exa": "key"}), http)
    result = await service.search_many(
        search_requests({"queries": ["one", "bad", "three", "four", "five"]})
    )
    assert result["succeeded"] == 4 and result["failed"] == 1
    assert result["partial"] is True and result["is_error"] is False
    assert [i["input"] for i in result["items"]] == ["one", "bad", "three", "four", "five"]
    assert result["items"][1]["error"]["code"] == "http_error"
    assert 1 < http.peak <= 3 and http.active == 0
    assert "ERROR" in result["text"] and len(result["text"]) <= 16000


async def test_fetch_batch_returns_snapshots_and_preserves_policy_rejection():
    http = BatchHttp()
    service = WebService(Config(), http)
    result = await service.fetch_many(
        fetch_requests(
            {
                "urls": [
                    "https://example.com/one",
                    "http://127.0.0.1/private",
                    "https://example.com/bad",
                ]
            }
        )
    )
    assert result["succeeded"] == 1 and result["failed"] == 2
    assert result["items"][0]["result"]["snapshot_id"].startswith("snap-")
    assert result["items"][1]["error"]["code"] == "blocked_url"
    assert http.calls == 2 and result["output_truncated"] is True


async def test_all_failed_batch_is_a_tool_error():
    result = await WebService(Config(), BatchHttp()).fetch_many(
        fetch_requests({"urls": ["https://example.com/bad"]})
    )
    assert result["is_error"] is True and result["partial"] is False


@pytest.mark.parametrize(
    "args",
    [
        {"queries": []},
        {"query": "x", "queries": ["y"]},
        {"queries": ["x", 4]},
        {"queries": ["x"] * 6},
        {"queries": ["ok"], "api_key": "secret"},
    ],
)
def test_search_batch_validation_is_atomic(args):
    with pytest.raises(WebToolError):
        search_requests(args)


async def test_abort_drains_batch_children_and_publishes_no_snapshots():
    started = asyncio.Event()
    http = BatchHttp()

    async def slow(method, url, **kwargs):
        http.calls += 1
        http.active += 1
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            http.active -= 1

    http.request = slow
    service = WebService(Config(), http)
    signal = asyncio.Event()
    task = asyncio.create_task(
        service.fetch_many(
            fetch_requests({"urls": ["https://example.com/one", "https://example.com/two"]}), signal
        )
    )
    await started.wait()
    signal.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert http.active == 0 and service.store.size_bytes == 0


async def test_real_host_schema_accepts_batch_and_cached_tools():
    from aelix_ai.tools import validate_tool_arguments
    from aelix_coding_agent.extensions.loader import load_extensions

    loaded = await load_extensions([setup])
    tools = loaded.extensions[0].tools
    args = await validate_tool_arguments(
        tools["web_search"], {"queries": ["one", "two"], "max_results": "5"}
    )
    assert args["max_results"] == 5
    args2 = await validate_tool_arguments(
        tools["web_fetch"], {"urls": ["https://example.com"], "refresh": True}
    )
    assert args2["refresh"] is True
    assert set(tools) == {"web_search", "web_fetch", "web_read", "web_find"}


async def test_long_source_urls_remain_complete_in_bounded_batch_text():
    class LongHttp:
        timeout = 25.0

        async def request(self, method, url, **kwargs):
            target = "https://example.com/" + "x" * 1800 + url[-1]
            return HttpResponse(target, 200, "text/plain", "utf-8", b"content " * 2000)

    result = await WebService(Config(), LongHttp()).fetch_many(
        fetch_requests({"urls": [f"https://example.com/{i}" for i in range(5)]})
    )
    assert len(result["text"]) <= 16000
    for item in result["items"]:
        assert item["result"]["url"] in result["text"]
        assert item["result"]["snapshot_id"] in result["text"]
