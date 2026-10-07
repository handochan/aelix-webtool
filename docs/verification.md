# First implementation verification

Date: 2026-10-08 (Asia/Seoul)
Status: Local implementation and validation complete; public publication and
catalog registration pending. This record does not claim search quality or
actual GitHub CI success.

## Environment

- macOS, Apple Silicon.
- Python 3.12.13 (primary) and Python 3.11.15 (minimum-version check).
- uv 0.11.19; locked extension dependencies: aiohttp 3.14.4,
  beautifulsoup4 4.15.0, markdownify 1.2.3, yarl 1.25.1.
- Host: Aelix `0.1.0b2`, source revision
  `402a801325dcc335e2b7e1a7e829e9b5ebed93ca`. Its tracked main matched GitHub
  when checked. Existing untracked material in that checkout was preserved.
- This extension does not modify Aelix core or the user's global installation.

## Executed checks

| Scope | Command / check | Observed result |
| --- | --- | --- |
| Deterministic contracts and actual HTTP boundaries, Python 3.12 | `uv run --no-sync pytest -q -W error::ResourceWarning` | 108 passed; no host module skipped. |
| Minimum Python version with independently installed extension/host | Python 3.11.15, actual host packages installed; `python -m pytest -q -W error::ResourceWarning` | 108 passed. |
| Lint, formatting, types | `ruff check .`, `ruff format --check .`, `pyright` | Passed; zero type errors. |
| Source/wheel packaging | `uv build` | Built sdist, then wheel from that sdist. |
| Fresh installed wheel / real host | `python scripts/verify_host.py --aelix-source <host checkout>` | `BOUND aelix-webtool`, exactly one installed entry point; automatic discovery exposes `web_search`, `web_fetch`, `/web`; actual host-type dispatch rejects a private fetch before I/O. |
| Model-free public fetch | CLI fetch of `https://example.com` and `https://docs.python.org/3/library/asyncio.html` | Real HTTPS, DNS/TLS, extraction, source URL and truncation metadata observed. |
| Real-model tool flow, installed wheel | `python scripts/model_e2e.py --provider openai-codex --model gpt-5.6-luna` | Exit 0; one fixture search request, both successful tool-end events, real public-document fetch, final answer contains the fixture marker and documentation URL. |

The real-model check uses a private temporary copy of existing host auth, a
temporary agent directory and `--no-session`, with only these two tools active.
Temporary credentials are removed when it exits. The installed-wheel run
reported no editable-manifest degradation warning. An earlier exploratory run
used the editable install and did warn; the final run superseded it with an
actual non-editable wheel.

Its search source is a deterministic HTTP server implementing SearXNG's JSON
shape. This verifies agent routing, API shape, tool-result ingestion and public
fetch behavior. It does **not** verify a real SearXNG engine deployment or an
external search provider's ranking.

## Review and repaired findings

- A live documentation fetch initially included Sphinx navigation in the text.
  Extraction now recognizes `[role="main"]` and the documentation body; a
  regression checks that the excerpt retains the article and omits navigation.
- The URL validator initially accepted legacy numeric host forms such as
  `2130706433`, `127.1` and octal/hex variants. Five new regression cases failed
  before the repair. These forms are now rejected before any connector shortcut
  can bypass DNS policy, including on older supported aiohttp versions.
- The isolated-host script initially guessed a non-executable CLI module path.
  It now invokes the actual console entry function under isolated Python mode;
  the installation and discovery gate was rerun successfully.
- Network tests exercise real HTTP redirects, chunked overflow, content-length
  overflow, total deadlines, cancellation, compressed-response refusal and
  credential-bearing API redirect refusal. Resolver tests include mixed DNS
  answers and a real connector refusing a DNS name that resolves to loopback
  before the local server receives a request.

HTTP fixture tests deliberately route a synthetic hostname to a local test
socket; that test-only resolver substitution is separate from the strict
production resolver tests. No production private-fetch exception was added.

## Unrun or pending gates

- **Brave, Tavily and Exa live keyed searches:** no search keys were present.
  Request mappings, normalization and errors are tested with fixtures, not live
  provider responses. No provider quality, price or reliability ranking is claimed.
- **Real self-hosted SearXNG engines:** local HTTP/API-shape coverage only.
- **GitHub Actions:** a pinned-host CI matrix for Python 3.11/3.12/3.13 is
  committed as configuration; no remote workflow has run for this repository.
  Python 3.13 and Linux are not included in the executed local evidence above.
- **Interactive TUI:** no custom renderer or widget was added. Slash-command
  registration and handler behavior were checked through the actual host API,
  without an interactive TUI session.
- **Public listing:** no source repository or marketplace PR has been published
  by this implementation session. The generator creates a SHA-pinned candidate,
  not a listing. The marketplace's install-from-public-source submission gate
  and post-merge published-catalog discovery remain necessary.

Raw local model evidence is under `.devstate/model-e2e-wheel/` (gitignored).
This committed record is the portable summary; credentials and local transcripts
are not release artifacts. See [registration](registration.md) for the remaining
publication gates.
