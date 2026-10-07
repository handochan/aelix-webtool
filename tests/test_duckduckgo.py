from __future__ import annotations

import json

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import SearchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService

LITE_RESULTS = """<html><title>Search at DuckDuckGo</title><table>
<tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fasyncio.html&amp;rut=tracking">Python asyncio</a></td></tr>
<tr><td class="result-snippet">Concurrent code using <b>async/await</b>.</td></tr>
<tr><td class="link-text">docs.python.org</td></tr>
<tr><td><a class="result-link" href="https://example.com/한국어">한국어 문서</a></td></tr>
<tr><td class="result-snippet">장비 분석 문서.</td></tr>
</table></html>"""


class HtmlHttp:
    def __init__(self, html=LITE_RESULTS, *, status=200, content_type="text/html", error=None):
        self.html = html
        self.status = status
        self.content_type = content_type
        self.error = error
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return HttpResponse(url, self.status, self.content_type, "utf-8", self.html.encode())


def test_zero_configuration_selects_keyless_provider():
    config = Config.from_env({})
    assert config.available() == ["duckduckgo"]
    assert config.select() == "duckduckgo"
    assert config.select("duckduckgo") == "duckduckgo"
    assert "duckduckgo" in WebService(config).status()


def test_keyless_selection_remains_explicit_when_other_providers_are_configured():
    config = Config(keys={"brave": "broken-key", "exa": "unused-key"})
    assert config.select() == "brave"
    assert config.select("duckduckgo") == "duckduckgo"
    assert Config(provider="duckduckgo", keys=config.keys).select() == "duckduckgo"


@pytest.mark.parametrize(
    "time_range,df", [(None, None), ("day", "d"), ("week", "w"), ("month", "m"), ("year", "y")]
)
async def test_keyless_request_and_source_contract(time_range, df):
    http = HtmlHttp()
    request = SearchRequest.from_args(
        {"query": "Python 문서", "provider": "duckduckgo", "time_range": time_range}
    )
    result = await WebService(Config(keys={"brave": "credential-not-for-ddg"}), http).search(
        request
    )
    assert result["provider"] == "duckduckgo"
    assert len(http.calls) == 1
    method, url, kwargs = http.calls[0]
    assert method == "GET" and url == "https://lite.duckduckgo.com/lite/"
    assert kwargs["params"]["q"] == "Python 문서"
    assert kwargs["params"].get("df") == df
    assert kwargs["headers"] == {"Accept": "text/html"}
    assert not kwargs.get("allow_private") and not kwargs.get("fetch")
    assert "credential-not-for-ddg" not in json.dumps(http.calls)
    assert result["results"][0]["url"] == "https://docs.python.org/3/library/asyncio.html"
    assert result["results"][0]["snippet"] == "Concurrent code using async/await."
    assert "duckduckgo.com/l/" not in result["text"]
    assert result["results"][1]["title"] == "한국어 문서"
    assert result["results"][1]["snippet"] == "장비 분석 문서."


async def test_default_search_succeeds_without_keys_or_endpoint():
    http = HtmlHttp()
    result = await WebService(Config.from_env({}), http).search(SearchRequest("Python asyncio"))
    assert result["provider"] == "duckduckgo" and len(result["results"]) == 2
    assert len(http.calls) == 1


async def test_domain_filters_use_query_operators_and_local_enforcement():
    http = HtmlHttp()
    request = SearchRequest.from_args(
        {
            "query": "Python docs",
            "include_domains": ["python.org"],
            "exclude_domains": ["old.python.org"],
        }
    )
    result = await WebService(Config(), http).search(request)
    assert "site:python.org" in http.calls[0][2]["params"]["q"]
    assert "-site:old.python.org" in http.calls[0][2]["params"]["q"]
    assert len(result["results"]) == 1
    assert result["results"][0]["url"].startswith("https://docs.python.org/")


@pytest.mark.parametrize(
    "html,status",
    [
        ('<form id="challenge-form" action="/anomaly.js">Verify you are human</form>', 202),
        ('<div class="anomaly-modal__modal">captcha</div>' + LITE_RESULTS, 200),
        (LITE_RESULTS, 202),
    ],
)
async def test_challenge_is_an_error_even_when_results_are_present(html, status):
    http = HtmlHttp(html, status=status)
    with pytest.raises(WebToolError) as exc:
        await WebService(Config(), http).search(SearchRequest("test"))
    assert exc.value.code == "provider_blocked"
    assert len(http.calls) == 1
    assert exc.value.retryable is False


@pytest.mark.parametrize(
    "html,content_type",
    [
        ("<html>Unexpected landing page</html>", "text/html"),
        ("", "text/html"),
        ('{"results": []}', "application/json"),
    ],
)
async def test_unrecognized_response_is_not_reported_as_empty_search(html, content_type):
    with pytest.raises(WebToolError) as exc:
        await WebService(Config(), HtmlHttp(html, content_type=content_type)).search(
            SearchRequest("test")
        )
    assert exc.value.code == "invalid_response"


async def test_explicit_empty_result_page_is_supported():
    html = '<html><div class="no-results">No results found.</div></html>'
    result = await WebService(Config(), HtmlHttp(html)).search(SearchRequest("test"))
    assert result["results"] == []


async def test_snippets_cannot_be_borrowed_from_the_next_result():
    html = """<table>
    <tr><td><a class="result-link" href="https://example.com/one">One</a></td></tr>
    <tr><td class="link-text">example.com</td></tr>
    <tr><td><a class="result-link" href="https://example.com/two">Two</a></td></tr>
    <tr><td class="result-snippet">Two's evidence.</td></tr></table>"""
    result = await WebService(Config(), HtmlHttp(html)).search(SearchRequest("test"))
    assert result["results"][0]["snippet"] == ""
    assert result["results"][1]["snippet"] == "Two's evidence."


async def test_wrappers_and_advertisement_links_do_not_trigger_fetches():
    html = """<table>
    <tr><td><a class="result-link" href="//duckduckgo.com/y.js?ad_domain=advertiser.example">Ad</a></td></tr>
    <tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fprivate">Private</a></td></tr>
    <tr><td><a class="result-link" href="javascript:alert(1)">Script</a></td></tr>
    <tr><td><a class="result-link" href="https://external.example/path?uddg=https%3A%2F%2Fdocs.python.org">Direct</a></td></tr>
    </table>"""
    http = HtmlHttp(html)
    result = await WebService(Config(), http).search(SearchRequest("test"))
    assert len(result["results"]) == 1
    assert result["results"][0]["url"].startswith("https://external.example/path?")
    assert len(http.calls) == 1


async def test_keyless_error_does_not_retry_or_switch_service():
    http = HtmlHttp(error=WebToolError("authorization", "Refused"))
    with pytest.raises(WebToolError) as exc:
        await WebService(Config(keys={"tavily": "not-for-ddg"}), http).search(
            SearchRequest("test", provider="duckduckgo")
        )
    assert exc.value.code == "provider_blocked"
    assert len(http.calls) == 1


async def test_query_with_filters_is_bounded_before_network():
    http = HtmlHttp()
    request = SearchRequest.from_args(
        {"query": "x" * 400, "include_domains": ["a" * 60 + "." + "b" * 60 + ".example"]}
    )
    with pytest.raises(WebToolError) as exc:
        await WebService(Config(), http).search(request)
    assert exc.value.code == "invalid_arguments"
    assert http.calls == []
