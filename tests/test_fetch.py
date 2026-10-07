from __future__ import annotations

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import FetchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService


class PageHttp:
    def __init__(
        self, html, content_type="text/html", charset="utf-8", final_url="https://example.com/final"
    ):
        self.response = HttpResponse(final_url, 200, content_type, charset, html.encode("utf-8"))
        self.calls = []

    async def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


async def test_extracts_main_content_links_unicode_and_omits_scripts():
    http = PageHttp("""<html><title>장비 가이드</title><body>
    <header>Header noise</header><nav>Navigation noise</nav><main>
    <h1>분석</h1><p>안녕하세요 <a href="/docs">문서</a></p>
    <script>secret script</script><style>css noise</style>
    <p hidden>hidden text</p><a href="javascript:alert(1)">bad link</a>
    <a href="http://127.0.0.1/secret">local link</a></main><footer>footer</footer></body></html>""")
    result = await WebService(Config(), http).fetch(FetchRequest("https://example.com/start"))
    assert result["title"] == "장비 가이드"
    assert "# 분석" in result["content"]
    assert "[문서](https://example.com/docs)" in result["content"]
    assert not any(
        word in result["content"]
        for word in (
            "secret script",
            "css noise",
            "hidden text",
            "noise",
            "127.0.0.1",
            "javascript:",
        )
    )
    assert result["url"] == "https://example.com/final"
    assert result["requested_url"] == "https://example.com/start"
    assert result["next_offset"] is None


async def test_offsets_hashes_and_more_text_are_explicit():
    service = WebService(Config(), PageHttp("반도체 문서 " * 200, "text/plain"))
    first = await service.fetch(FetchRequest("https://example.com/page", max_chars=100))
    second = await service.fetch(
        FetchRequest("https://example.com/page", max_chars=100, offset=100)
    )
    assert first["next_offset"] == 100
    assert second["offset"] == 100
    assert first["content_hash"] == second["content_hash"]
    assert first["source_id"] == second["source_id"]
    assert "web_read" in first["text"] and second["cached"] is True
    with pytest.raises(WebToolError, match="beyond"):
        await service.fetch(FetchRequest("https://example.com/page", offset=90000))


async def test_empty_static_page_is_an_error():
    service = WebService(Config(), PageHttp("<body><script>render app</script></body>"))
    with pytest.raises(WebToolError) as exc:
        await service.fetch(FetchRequest("https://example.com"))
    assert exc.value.code == "empty_content"


async def test_sphinx_main_role_keeps_navigation_out_of_excerpt():
    http = PageHttp("""<body><div class="related">Navigation noise</div>
    <div class="body" role="main"><h1>asyncio</h1><p>Concurrent Python.</p></div>
    <div class="sphinxsidebar">sidebar noise</div></body>""")
    result = await WebService(Config(), http).fetch(FetchRequest("https://example.com/docs"))
    assert "# asyncio" in result["content"]
    assert "noise" not in result["content"]


async def test_invalid_charset_falls_back_and_control_sequences_are_removed():
    result = await WebService(Config(), PageHttp("한국어\u001b[0m", "text/plain", "made-up")).fetch(
        FetchRequest("https://example.com")
    )
    assert "한국어" in result["content"] and "\u001b" not in result["content"]
