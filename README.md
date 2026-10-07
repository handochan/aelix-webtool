# Aelix Web Tools

An Aelix extension providing `web_search`, `web_fetch` and `/web`.
Source: [handochan/aelix-webtool](https://github.com/handochan/aelix-webtool).
The [official catalog](https://handochan.github.io/aelix-marketplace/catalog.json)
is the authority for the published installation source; see
[registration results](docs/registration-results.md) and
[registration](docs/registration.md) for the published record and procedure.

## Install into Aelix

With Aelix already installed, install from the official catalog:

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool
aelix extension verify aelix-webtool
```

Restart Aelix (or `/reload`) after installing. `/web` shows which search
providers can be selected without exposing credentials. With no provider
settings, search uses keyless DuckDuckGo Lite.

To build and install a wheel from a source checkout:

```bash
uv build --wheel
aelix extension install /absolute/path/to/aelix_webtool-0.1.0-py3-none-any.whl
aelix extension verify aelix-webtool
```

Aelix supplies the host
APIs; this wheel deliberately does not depend on beta placeholder PyPI packages.
Compatibility was checked against Aelix source at the revision recorded in
[verification](docs/verification.md), rather than inferred from the version name.

## Configure search

With no keys or provider settings, `web_search` uses **DuckDuckGo Lite**.
It needs internet access, but no account, API key or self-hosted server.
To select it explicitly when other configured providers are unavailable:

```bash
export AELIX_WEB_PROVIDER=duckduckgo
aelix
```

This uses the public Lite search page, whose format and availability can change.
CAPTCHA/block responses are reported as errors; the extension does not solve
challenges, rotate identities or retry through other services.

These are search-service API keys issued by Brave, Tavily or Exa. Configure
the key for the provider you use. They are separate from Aelix's conversational
model credentials; this extension does not reuse model API keys or OAuth logins
for these search endpoints. Self-hosted SearXNG needs its endpoint URL instead,
and public-page `web_fetch` needs no search API key.

Export a provider key in the shell that starts Aelix:

```bash
export BRAVE_API_KEY='your-key'
export AELIX_WEB_PROVIDER=brave
aelix
```

| Provider | Configuration | Recency behavior |
| --- | --- | --- |
| DuckDuckGo | None; optionally `AELIX_WEB_PROVIDER=duckduckgo` | day/week/month/year hints on the public Lite page; best-effort. |
| Brave | `BRAVE_API_KEY` | Page-age filter: day/week/month/year. |
| Tavily | `TAVILY_API_KEY` | Provider time-range filter: day/week/month/year. |
| Exa | `EXA_API_KEY` | Published-date lower bound: 1/7/30/365 days. |
| SearXNG | `AELIX_WEB_SEARXNG_URL` | day/month/year; week returns an explicit unsupported-filter error. Instance engines may handle filters differently. |

`AELIX_WEB_PROVIDER=auto` (the default) selects the first configured provider in
this order: SearXNG, Brave, Tavily, Exa, then keyless DuckDuckGo. It sends one
request to that provider. If a configured provider is unavailable, select
`duckduckgo` explicitly to search without using its key.
Failures do not automatically cause retries or calls to other services. Choose
an explicit provider to make routing independent of other exported keys.
No search configuration is needed for `web_fetch`.

For a self-hosted search service:

```bash
export AELIX_WEB_SEARXNG_URL='http://127.0.0.1:8080'
export AELIX_WEB_PROVIDER=searxng
```

The SearXNG instance must enable JSON output. Its exact configured endpoint can
be private; search API redirects remain refused. This does not grant the fetch
tool access to private networks. The default when nothing is configured is the
public DuckDuckGo Lite endpoint. `.env` files are **not** automatically read.

`AELIX_WEB_OFFLINE=1` disables both tools. Aelix's general `--offline` controls
its own maintenance/catalog traffic; it does not sandbox extensions or their
HTTP calls. Use this extension's setting to disable its network tools.

## Tool contracts

```python
web_search(
    {
        "query": "Python asyncio documentation",
        "max_results": 5,
        "time_range": "month",
        "include_domains": ["docs.python.org"],
    }
)

web_fetch({"url": "https://docs.python.org/3/library/asyncio.html", "max_chars": 8000})
```

Search returns source IDs, actual source URLs, provider, retrieval time and
bounded snippets. Provider-reported publication dates are labelled as such.
Domain constraints also run locally after the API response. Empty results do
not establish that a fact is absent. Search does not generate a second model's
answer; the conversational model reads the sources and cites their URLs.

Fetch returns the final URL, extracted text/Markdown, content hash, retrieval
time and truncation metadata. Follow `next_offset` to read another excerpt;
the page is fetched again and can change, so compare content hashes. Web content
is untrusted evidence and must never become instructions to the agent.

## Limits and behavior

- Search: 1–20 results, query up to 400 characters/75 words, up to 10 included
  and 10 excluded domains; snippets up to 600 characters; text output up to
  16,000 characters. Upstream response limit: 1 MB.
- Fetch: public HTTP(S) on ports 80/443, static HTML, text, Markdown or JSON.
  2 MB input limit, 8,000-character default excerpt (12,000 max), five redirects
  and a 25-second total HTTP deadline. Compressed responses that ignore
  `Accept-Encoding: identity` are explicitly refused.
- TLS verification stays enabled. The actual connector validates DNS addresses;
  local/private/special-use and mixed answers are blocked. Fetch never accepts
  model-provided credentials, headers or private-network exceptions.
- No JavaScript browser, PDF parser, login cookies, proxy environment variables,
  hosted reader fallback, disk content cache or subscription-token reuse.
- Loading the extension makes no network call. Cancellation drains tasks and
  closes request resources. Classified errors omit upstream bodies and client
  exception strings; configured provider keys are also redacted from output.
- Aelix's regular extension-tool approvals apply, including plan-mode blocking.
  `net = true` declares network intent; an in-process Python extension is not
  sandboxed by its manifest.

## Develop and verify

```bash
uv sync
# For host integration tests/type checks, install the actual host source:
uv pip install /path/to/aelix-ai/packages/aelix-ai \
  /path/to/aelix-ai/packages/aelix-agent-core \
  /path/to/aelix-ai/packages/aelix-coding-agent
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync pyright
uv run --no-sync python scripts/verify_host.py --aelix-source /path/to/aelix-ai
```

The CLI works independently of a running model:

```bash
uv run --no-sync aelix-webtool status
uv run --no-sync aelix-webtool search 'Python asyncio official documentation' --provider duckduckgo
uv run --no-sync aelix-webtool search 'Aelix extension documentation' --provider brave
uv run --no-sync aelix-webtool fetch https://docs.python.org/3/library/asyncio.html
```

Without the host packages the host integration test module is skipped. CI
installs the pinned real host and additionally verifies a fresh wheel in an
isolated environment. Mocked provider responses, actual HTTP fixtures,
public-page live fetches and real-model E2E are recorded separately in
[verification](docs/verification.md).

See [design](docs/decisions/0001-web-tool-contract.md), [keyless search decision](docs/decisions/0002-keyless-duckduckgo-search.md), [investigated references](docs/references.md)
and [official registration procedure](docs/registration.md).
