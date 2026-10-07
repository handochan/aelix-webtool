"""Static page extraction; no browser, scripts, cookies or third-party reader."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify
from trafilatura import extract

from .errors import WebToolError
from .network import HttpResponse, validate_url


def clean_text(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]", "", text)


def decode(response: HttpResponse) -> str:
    try:
        return clean_text(response.body.decode(response.charset, errors="replace"))
    except LookupError:
        return clean_text(response.body.decode("utf-8", errors="replace"))


def extract_page(response: HttpResponse) -> tuple[str, str, str]:
    text = decode(response)
    if response.challenged:
        raise WebToolError(
            "blocked_page",
            "The server returned a challenge page instead of the requested document.",
        )
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        return response.url, text.strip(), "text"
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else response.url
    scripts = soup.find_all("script")
    script_text = " ".join(script.get_text() for script in scripts)
    challenge_script = any(
        "/cdn-cgi/challenge-platform/" in str(script.get("src", "")) for script in scripts
    )
    if (
        title.strip().lower() == "just a moment..."
        and "window._cf_chl_opt" in script_text
        and (challenge_script or "/cdn-cgi/challenge-platform/" in script_text)
    ) or soup.select_one('#challenge-form, .anomaly-modal__modal, form[action*="/anomaly.js"]'):
        raise WebToolError(
            "blocked_page",
            "The server requested human verification instead of returning the document.",
        )
    if (
        soup.select_one('form input[type="password"]')
        and len(soup.get_text()) < 1200
        and re.search(r"sign\s*in|log\s*in|login", title, re.I)
    ):
        raise WebToolError(
            "authentication_required",
            "The page requires authentication; no readable public document was returned.",
        )
    root_text = " ".join(
        (soup.body or soup.select_one("#root, #app, #__next") or soup)
        .get_text(" ", strip=True)
        .split()
    )
    if (
        scripts
        and soup.select_one("#root, #app, #__next")
        and (not root_text or re.fullmatch(r"(?:loading|please wait)[.\s…!]*", root_text, re.I))
    ):
        raise WebToolError(
            "requires_javascript",
            "The page is a JavaScript-only shell; static reading cannot retrieve its document.",
        )
    for node in soup.select(
        "script, style, noscript, template, nav, footer, body > header, form, svg, iframe, "
        "[role=navigation], [role=complementary], .sidebar, .sphinxsidebar, .cookie-banner"
    ):
        node.decompose()
    for node in soup.select('[hidden], [aria-hidden="true"]'):
        node.decompose()
    for node in soup.find_all("a"):
        href = node.get("href")
        try:
            if not isinstance(href, str):
                raise WebToolError("invalid_url", "Invalid link.")
            node["href"] = validate_url(urljoin(response.url, href))
        except WebToolError:
            node.unwrap()
    root = (
        soup.find("main")
        or soup.select_one('[role="main"]')
        or soup.find("article")
        or soup.select_one("div.body")
    )
    if root is None:
        # Extraction is local only. Never use Trafilatura's fetch helpers, and
        # disable metadata/date crawling and global deduplication state.
        content = extract(
            str(soup),
            url=response.url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_links=True,
            with_metadata=False,
            deduplicate=False,
        )
        if content:
            return clean_text(title)[:300], clean_text(content).strip(), "markdown"
        root = soup.body or soup
    content = markdownify(str(root), heading_style="ATX", strip=["img"], bullets="-")
    return clean_text(title)[:300], clean_text(content).strip(), "markdown"
