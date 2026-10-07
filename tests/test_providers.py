from __future__ import annotations

import json
from datetime import datetime

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import SearchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import SEARCH_OUTPUT_LIMIT, WebService


class RecordingHttp:
    def __init__(self, payload=None, error=None):
        self.payload = {"results": []} if payload is None else payload
        self.error = error
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return HttpResponse(
            url, 200, "application/json", "utf-8", json.dumps(self.payload).encode()
        )


def config(provider="auto"):
    return Config(
        provider=provider, keys={"brave": "key-brave", "tavily": "key-tavily", "exa": "key-exa"}
    )


@pytest.mark.parametrize("provider", ["brave", "tavily", "exa"])
async def test_provider_wire_contracts_and_recency(provider):
    http = RecordingHttp(
        {"type": "search", "web": {"results": []}} if provider == "brave" else None
    )
    request = SearchRequest.from_args(
        {
            "query": "Python 문서",
            "provider": provider,
            "max_results": 8,
            "time_range": "week",
            "include_domains": ["docs.python.org"],
            "exclude_domains": ["old.docs.python.org"],
        }
    )
    result = await WebService(config(), http).search(request)
    assert result["provider"] == provider
    assert len(http.calls) == 1
    method, url, kwargs = http.calls[0]
    assert url.startswith("https://")
    assert "key-" not in url
    if provider == "brave":
        assert method == "GET"
        assert kwargs["headers"] == {"X-Subscription-Token": "key-brave"}
        assert kwargs["params"]["count"] == 8
        assert kwargs["params"]["freshness"] == "pw"
        assert "site:docs.python.org" in kwargs["params"]["q"]
        assert "-site:old.docs.python.org" in kwargs["params"]["q"]
    elif provider == "tavily":
        assert method == "POST"
        body = kwargs["json_body"]
        assert body["query"] == "Python 문서" and body["max_results"] == 8
        assert body["time_range"] == "week"
        assert body["include_answer"] is False and body["include_raw_content"] is False
        assert body["auto_parameters"] is False
        assert body["include_domains"] == ["docs.python.org"]
    else:
        assert method == "POST"
        body = kwargs["json_body"]
        assert body["contents"] == {"highlights": True}
        assert body["numResults"] == 8 and body["type"] == "auto"
        assert body["includeDomains"] == ["docs.python.org"]
        assert datetime.fromisoformat(body["startPublishedDate"]).tzinfo is not None


async def test_searxng_is_operator_configured_and_week_fails_before_request():
    http = RecordingHttp()
    service = WebService(Config(searxng_url="http://127.0.0.1:8080/team"), http)
    result = await service.search(SearchRequest("test", time_range="day"))
    assert result["provider"] == "searxng"
    method, url, kwargs = http.calls[0]
    assert method == "GET" and url == "http://127.0.0.1:8080/team/search"
    assert kwargs["params"]["format"] == "json"
    assert kwargs["params"]["time_range"] == "day"
    assert kwargs["allow_private"] is True
    with pytest.raises(WebToolError) as exc:
        await service.search(SearchRequest("test", time_range="week"))
    assert exc.value.code == "unsupported_filter"
    assert len(http.calls) == 1


async def test_failure_never_sends_query_to_other_configured_provider():
    http = RecordingHttp(error=WebToolError("rate_limit", "Rate limit", retryable=True))
    with pytest.raises(WebToolError):
        await WebService(config(), http).search(SearchRequest("private query"))
    assert len(http.calls) == 1
    assert "brave" in http.calls[0][1]


async def test_result_normalization_deduplication_domain_policy_and_redaction():
    http = RecordingHttp(
        {
            "results": [
                {
                    "title": "<b>반도체 문서</b>",
                    "url": "https://docs.example.com/guide#one",
                    "content": "key-exa <b>내용</b>\u001b",
                    "published_date": "2026-10-08",
                },
                {"title": "duplicate", "url": "https://docs.example.com/guide#two"},
                {"url": "https://notexample.com/lookalike"},
                {"url": "https://blocked.example.com/page"},
                {"url": "http://127.0.0.1/secret"},
                {"url": "file:///etc/passwd"},
                {"url": 12},
                {
                    "title": "Two",
                    "url": "https://example.com/two",
                    "highlights": ["new", None, "documentation"],
                },
            ]
        }
    )
    request = SearchRequest.from_args(
        {
            "query": "문서",
            "include_domains": ["example.com"],
            "exclude_domains": ["blocked.example.com"],
        }
    )
    result = await WebService(config("exa"), http).search(request)
    assert len(result["results"]) == 2
    first = result["results"][0]
    assert first["title"] == "반도체 문서"
    assert first["url"] == "https://docs.example.com/guide"
    assert first["published_at"] == "2026-10-08"
    assert "key-exa" not in json.dumps(result)
    assert "[REDACTED]" in first["snippet"]
    assert "\u001b" not in result["text"]
    assert result["results"][1]["snippet"] == "new documentation"
    assert result["filtered_results"] == 5
    again = await WebService(config("exa"), http).search(request)
    assert first["source_id"] == again["results"][0]["source_id"]


@pytest.mark.parametrize(
    "payload", [{"answer": "looks useful"}, {"results": None}, {"results": "bad"}, {"results": {}}]
)
async def test_malformed_success_cannot_be_misreported_as_no_results(payload):
    with pytest.raises(WebToolError) as exc:
        await WebService(config("exa"), RecordingHttp(payload)).search(SearchRequest("test"))
    assert exc.value.code == "invalid_response"


async def test_brave_empty_results_shape_is_supported():
    result = await WebService(
        config("brave"), RecordingHttp({"type": "search", "query": {"original": "x"}})
    ).search(SearchRequest("x"))
    assert result["results"] == []
    assert "does not establish" in result["text"]


async def test_long_results_are_bounded_and_truncation_is_visible():
    rows = [
        {
            "url": "https://example.com/" + str(i) + "x" * 1800,
            "title": "t" * 800,
            "content": "c" * 9000,
        }
        for i in range(30)
    ]
    result = await WebService(config("exa"), RecordingHttp({"results": rows})).search(
        SearchRequest("test", max_results=20)
    )
    assert len(result["text"]) <= SEARCH_OUTPUT_LIMIT
    assert result["truncated"] is True
    assert "omitted" in result["text"]
    assert len(result["results"]) < 20
