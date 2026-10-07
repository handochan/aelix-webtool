"""Static page extraction; no browser, scripts, cookies or third-party reader."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify

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
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        return response.url, text.strip(), "text"
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else response.url
    for node in soup.select(
        "script, style, noscript, template, nav, footer, header, form, svg, iframe"
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
        or soup.body
        or soup
    )
    content = markdownify(str(root), heading_style="ATX", strip=["img"], bullets="-")
    return clean_text(title)[:300], clean_text(content).strip(), "markdown"
