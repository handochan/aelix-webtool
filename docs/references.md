# Web-tool references

Checked 2026-10-08 (Asia/Seoul). Facts below concern inspected documentation
and source; they are not a live search-quality benchmark or a price comparison.

| Reference | Useful behavior | First-version choice |
| --- | --- | --- |
| [Pi package catalog](https://pi.dev/packages) | Both `pi-web-access` and `pi-web-search` are discoverable examples. Catalog presence does not establish official Pi support. | Inspect package source and contracts, not just download counts. |
| [pi-web-access](https://github.com/nicobailon/pi-web-access/tree/f0c0a96a8f19198e767cbec2e447f38779ccca50) | Host-independent core, search/fetch separation, source metadata, response IDs, filters, abort and SSRF handling. Broad integrations and optional fallbacks create a large configuration surface. | Adopt a small core, explicit providers, source metadata, bounded results and cancellation. Defer cache IDs, browser cookies, cloning, video and hosted fallback. |
| [pi-web-search](https://github.com/ttttmr/pi-web-search/tree/8017f377178bbac28974d6da83fa9ea8b374f644) | Native search uses current provider/model; unsupported models do not silently cause a model switch. Dedicated search models are explicit. | Preserve strict selection. Native model search remains a later adapter after Aelix auth/endpoint behavior is validated. |
| [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get) | Ranked web results, freshness ranges, snippets, explicit API token and search operators. | GET with header credential; bounded results; no generated answer. |
| [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search) | Search-depth choices, domain/date filters, content snippets and optional answer/raw content. | Basic search, disable automatic parameters, answers, images and raw pages. |
| [Exa Search API](https://exa.ai/docs/reference/search) | Search plus highlights, domain inclusion/exclusion and published-date filtering. | Direct keyed REST search, highlights only. No implicit keyless hosted MCP endpoint. |
| [SearXNG Search API](https://docs.searxng.org/dev/search_api.html) | Self-hostable JSON search; instances must enable JSON output. Time ranges are day/month/year. | Operator-owned endpoint only; reject unsupported week filter. Engine handling of dates and site operators can vary. |
| [aiohttp advanced clients](https://docs.aiohttp.org/en/stable/client_advanced.html) | Custom connector/resolver, resource ownership, TLS, redirect and proxy configuration. | Validate actual connection DNS answers, close resources per call, disable ambient proxies and cookies. |
| [Aelix extension guide](https://github.com/handochan/aelix-ai/blob/402a801325dcc335e2b7e1a7e829e9b5ebed93ca/docs/guides/extension-authoring.md) | Python factory, AgentTool, entry points, manifests, command dispatch and permission posture. | Use the Python extension contract directly. No core changes. |
| [Official marketplace contribution contract](https://github.com/handochan/aelix-marketplace/blob/main/CONTRIBUTING.md) | Owner review, git/PyPI sources, actual installation and `BOUND` manifest gate. | Prepare a SHA-pinned entry from the reviewed source; validate at the actual submission boundary. |

Provider-native integrations in third-party packages were inspected as design
examples only. Their claims about subscription endpoints or supported models
were not adopted as Aelix support claims. No code was copied from those packages.
