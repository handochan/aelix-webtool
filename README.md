# Aelix Web Tools

An Aelix extension providing `web_search`, `web_fetch`, `web_read`, `web_find` and `/web`.
The v0.2 implementation adds stable session snapshots, literal passage lookup,
batch queries/URLs, stronger document extraction and explicitly configured resilience.
The [measured interface comparison](docs/tool-interface-comparison-results.md)
records why the public API retains four tools rather than combining read/find.
Source: [handochan/aelix-webtool](https://github.com/handochan/aelix-webtool).
The [official catalog](https://handochan.github.io/aelix-marketplace/catalog.json)
is the authority for the published installation source; see
[v0.2 registration results](docs/registration-v0.2-results.md) and
[registration](docs/registration.md) for the published record and procedure.

## Install into Aelix

The published catalog pins v0.2.0 to the reviewed merge of
[source PR #8](https://github.com/handochan/aelix-webtool/pull/8), published through
[catalog PR #6](https://github.com/handochan/aelix-marketplace/pull/6).

With Aelix already installed, install from the official catalog:

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool
aelix extension verify aelix-webtool
```

For an existing v0.1 git installation, review the new source shown by the
installer and explicitly accept the new commit pin:

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool --repin
aelix extension verify aelix-webtool
```

Restart Aelix (or `/reload`) after installing. `/web` shows which search
providers can be selected without exposing credentials. With no provider
settings, search uses keyless DuckDuckGo Lite.

To build and install a wheel from a source checkout:

```bash
uv build --wheel
aelix extension install /absolute/path/to/aelix_webtool-0.2.0-py3-none-any.whl
aelix extension verify aelix-webtool
```

Aelix supplies the host
APIs; this wheel deliberately does not depend on beta placeholder PyPI packages.
Compatibility was checked against Aelix source at the revision recorded in
[v0.2 verification](docs/verification-v0.2.md), rather than inferred from the version name.

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
challenges or rotate identities. These errors never trigger retry or fallback.

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
Default settings make no automatic retry or call to another service. Choose
an explicit provider to make routing independent of other exported keys.
No search configuration is needed for `web_fetch`.

To explicitly permit a transient retry or an ordered alternate-provider route:

```bash
export AELIX_WEB_PROVIDER=brave
export AELIX_WEB_RETRIES=1
export AELIX_WEB_FALLBACK_PROVIDERS=tavily,duckduckgo
```

The fallback list permits up to two unique, available providers and excludes the
primary. Each attempt uses only that provider's fixed endpoint and credential.
The full search, queueing and retry wait share a 25-second deadline. Retry-After
is respected; waits over two seconds fail rather than blocking the agent.
Only eligible transient or quota failures use an operator-declared alternate.
Authentication, configuration, arguments, security policy, unknown response
formats, unsupported filters and challenges fail closed. Explicit tool
`provider` arguments never switch providers. No summary/model call is introduced.

For a self-hosted search service:

```bash
export AELIX_WEB_SEARXNG_URL='http://127.0.0.1:8080'
export AELIX_WEB_PROVIDER=searxng
```

The SearXNG instance must enable JSON output. Its exact configured endpoint can
be private; search API redirects remain refused. This does not grant the fetch
tool access to private networks. The default when nothing is configured is the
public DuckDuckGo Lite endpoint. `.env` files are **not** automatically read.

`AELIX_WEB_OFFLINE=1` disables search and fetch. Aelix's general `--offline` controls
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

web_search({"queries": ["asyncio task documentation", "asyncio cancellation documentation"]})
web_fetch(
    {
        "urls": [
            "https://docs.python.org/3/library/asyncio.html",
            "https://docs.python.org/3/library/asyncio-task.html",
        ]
    }
)
web_fetch({"url": "https://docs.python.org/3/library/asyncio.html", "max_chars": 8000})
# Use the snapshot_id returned by web_fetch:
web_find({"snapshot_id": "snap-<returned-id>", "query": "cancellation"})
web_read({"snapshot_id": "snap-<returned-id>", "offset": 8000, "max_chars": 8000})
```

Search returns source IDs, actual source URLs, provider, retrieval time and
bounded snippets. Provider-reported publication dates are labelled as such.
Domain constraints also run locally after the API response. Empty results do
not establish that a fact is absent. Search does not generate a second model's
answer; the conversational model reads the sources and cites their URLs.

Fetch stores the full extracted document and returns a snapshot ID, actual URL,
content hash and retrieval time. Repeated fetches of that URL reuse its snapshot;
`refresh=true` captures a new document and keeps the older snapshot readable
until eviction/expiry. Follow `next_offset` with `web_read` to read the exact same
document without another request. `web_find` returns literal matches, nearby
context and original Unicode-character/one-based-line positions. Hashes and
positions refer to stored, sanitized text, not raw HTML.

Batches accept up to five inputs, run at most three network operations at once
and return per-item results/errors in input order. A partial success is clearly
labelled; an entirely failed batch is a tool/CLI error. Combined displayed text
is bounded, previews can be shorter than structured results, and source URLs
remain intact. Brave and DuckDuckGo searches are serialized per service.

Snapshots belong to one running service/session: 32 entries, 16 MB accounted
payload including text/index/metadata, 2 MB text per document and 30-minute TTL.
Eviction is LRU. They are not written to disk and do not survive new sessions,
fork/rebuild, reload or restart. `/web clear` clears them explicitly. Cached
reads/finds can work with network tools disabled; missing IDs are explicit errors.
The CLI is a new process per invocation; use `fetch --find` or a persistent
Python `WebService` instance for combined investigation.

Web content remains untrusted evidence and must never become instructions.

## Limits and behavior

- Search: 1–20 results, query up to 400 characters/75 words, up to 10 included
  and 10 excluded domains; snippets up to 600 characters; text output up to
  16,000 characters. Upstream response limit: 1 MB.
- Fetch: public HTTP(S) on ports 80/443, static HTML, text, Markdown or JSON.
  2 MB encoded and decoded input limits, 8,000-character default excerpt
  (12,000 max), five redirects and a 25-second deadline including queueing.
  gzip and zlib/raw deflate are streamed with a decoder-side allocation limit;
  truncated/malformed/concatenated streams are rejected. Brotli is unsupported.
- TLS verification stays enabled. The actual connector validates DNS addresses;
  local/private/special-use and mixed answers are blocked. Fetch never accepts
  model-provided credentials, headers or private-network exceptions.
- Challenge headers/strong HTML markers, login-only screens and loading-only
  JavaScript shells are errors. Technical DOM extraction preserves document
  headings/code/tables; unstructured articles use local Trafilatura extraction.
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
uv run --no-sync aelix-webtool fetch https://docs.python.org/3/library/asyncio.html --find cancellation
```

Without the host packages the host integration test module is skipped. CI
installs the pinned real host and additionally verifies a fresh wheel in an
isolated environment. Mocked provider responses, actual HTTP fixtures,
public-page live fetches and real-model E2E are recorded separately in
[verification](docs/verification.md).

The v0.2 implementation and validation are recorded in
[v0.2 verification](docs/verification-v0.2.md).

See [design](docs/decisions/0001-web-tool-contract.md), [keyless search decision](docs/decisions/0002-keyless-duckduckgo-search.md), [v0.2 decision](docs/decisions/0003-core-web-investigation.md), [investigated references](docs/references.md)
and [official registration procedure](docs/registration.md).
