from __future__ import annotations

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.extract import extract_page
from aelix_webtool.models import FetchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService


def response(html):
    return HttpResponse("https://example.com/docs", 200, "text/html", "utf-8", html.encode())


@pytest.mark.parametrize(
    "html,code",
    [
        (
            '<title>Just a moment...</title><p>Checking browser.</p><script>window._cf_chl_opt = {};</script><script src="/cdn-cgi/challenge-platform/check.js"></script>',
            "blocked_page",
        ),
        (
            '<title>Verify</title><form id="challenge-form" action="/anomaly.js">Verify you are human</form>',
            "blocked_page",
        ),
        (
            '<title>Sign in</title><form action="/login"><input type="password">Sign in to view this page</form>',
            "authentication_required",
        ),
        (
            '<title>App</title><div id="root">Loading...</div><script src="app.js"></script>',
            "requires_javascript",
        ),
    ],
)
async def test_non_document_pages_are_not_successful_evidence(html, code):
    class Http:
        async def request(self, *args, **kwargs):
            return response(html)

    with pytest.raises(WebToolError) as exc:
        await WebService(Config(), Http()).fetch(FetchRequest("https://example.com/docs"))
    assert exc.value.code == code


def test_document_header_code_tables_and_safe_links_are_preserved():
    html = """<body><header>Site noise</header><nav>Menu noise</nav><main>
    <article><header><h1>장비 설정</h1></header><p>설정 문서.</p>
    <pre><code class="language-python">timeout = 10\nprint(timeout)</code></pre>
    <table><tr><th>Parameter</th><th>Value</th></tr><tr><td>timeout</td><td>10</td></tr></table>
    <a href="/reference">Reference</a><aside>Useful note.</aside></article>
    <aside class="sidebar">Sidebar noise</aside></main></body>"""
    _, content, _ = extract_page(response(html))
    assert "장비 설정" in content and "timeout = 10\nprint(timeout)" in content
    assert "Parameter" in content and "| timeout | 10 |" in content
    assert "[Reference](https://example.com/reference)" in content
    assert "Useful note." in content and "noise" not in content


def test_article_without_semantic_wrapper_omits_link_heavy_boilerplate():
    paragraph = (
        "The equipment guide explains sensor collection, calibration and repeatable operation. "
        * 12
    )
    html = (
        '<body><div class="sidebar">'
        + "".join(f'<a href="/menu/{i}">Unrelated menu item {i}</a>' for i in range(80))
        + '</div><div class="post"><h1>Equipment guide</h1><p>'
        + paragraph
        + "</p><p>"
        + paragraph.replace("sensor", "signal")
        + "</p></div></body>"
    )
    _, content, _ = extract_page(response(html))
    assert "sensor collection" in content and "signal collection" in content
    assert "Unrelated menu" not in content


def test_generic_title_and_quoted_challenge_markers_are_not_a_block():
    html = "<title>Just a moment...</title><article><h1>Browser challenge tutorial</h1><pre>window._cf_chl_opt and /cdn-cgi/challenge-platform/ are examples.</pre><p>Normal reference content.</p></article>"
    _, content, _ = extract_page(response(html))
    assert "Normal reference content." in content


def test_challenge_header_is_authoritative_for_plain_text():
    result = HttpResponse(
        "https://example.com/docs", 200, "text/plain", "utf-8", b"verification", challenged=True
    )
    with pytest.raises(WebToolError) as exc:
        extract_page(result)
    assert exc.value.code == "blocked_page"
