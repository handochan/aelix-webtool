# ADR-0002: Keyless DuckDuckGo Lite search

Status: Accepted
Amended by: [ADR-0003](0003-core-web-investigation.md) when retries/fallback are explicitly configured; challenge bypass remains prohibited.
Date: 2026-10-08 (Asia/Seoul)
Amends: ADR-0001 search-provider selection and its no-default-keyless-endpoint decision.

## Context

The owner asked for a working search option when no configured provider can be
used and no API key is available. The first version needed a dedicated search
key or an operator-run SearXNG endpoint; it could not perform ordinary search
with zero configuration.

DuckDuckGo documents public HTML and Lite non-JavaScript search pages. A small
live probe in this environment found that HTML returned a human-verification
page (HTTP 202), while Lite returned normal search results (HTTP 200). Lite was
selected as the one fixed endpoint; this is not a runtime endpoint retry chain.

## Decision

- Add `duckduckgo` using `https://lite.duckduckgo.com/lite/` through the existing
  bounded HTTP client. No key, account, cookies, browser, proxy, installed
  metasearch library or user-supplied endpoint is needed.
- `auto` selects SearXNG, Brave, Tavily, Exa in the existing order when configured,
  then DuckDuckGo. With no configuration, DuckDuckGo is selected before any I/O.
  Existing configured providers still take priority; a configured provider
  failing does not silently send its query elsewhere. An explicit
  `provider="duckduckgo"` or `AELIX_WEB_PROVIDER=duckduckgo` works even when keys
  for other, unavailable providers are present.
- Make exactly one first-page GET per search. Return up to the requested result
  limit from that page; fewer results can be returned. Do not paginate, retry,
  switch engines/endpoints, solve challenges, borrow tokens, rotate identities
  or fetch result redirect wrappers.
- Parse normal Lite result links and the associated snippet rows. Decode `uddg`
  destinations only on DuckDuckGo's known `/l/` wrapper, then validate the actual
  destination. Omit advertising endpoints and unsafe URLs. Do not assign the
  next result's snippet to a source missing its own snippet.
- Send domain filters as search operators and enforce them locally. Map the
  requested time range to `df=d/w/m/y`; this is a provider hint, not proof of
  publication time or completeness. Enforce a 499-character limit including
  generated filter operators before sending the request.
- An HTTP 202, recognized challenge, or 401/403 becomes `provider_blocked`.
  Existing timeout, rate-limit and size errors remain explicit. An unfamiliar
  response shape becomes `invalid_response`; only a recognized no-results page
  counts as an empty search. Never turn a CAPTCHA into a successful empty result.
- Keep the existing DNS, TLS, private-network, one-MB search input, output limit,
  credential redaction, cancellation and offline boundaries.
- `available()`/`/web` describe providers that can be selected, not a successful
  reachability probe. Loading still performs no I/O.

## Verification and limits

Test zero-configuration selection, explicit selection over unavailable keyed
providers, request/filter mapping, wrapper decoding, Unicode, snippet ownership,
advertisement/unsafe-link omission, empty/malformed/challenge responses and
strict one-request behavior. Recheck Python 3.11/3.12/3.13, installed-wheel
binding, a real keyless search and the model's actual search/fetch flow.

This integrates a public search page, not a versioned search API with a service
guarantee. Its markup or availability can change, and the service can rate-limit
or block requests. On a blocked request the user sees that error and can choose
another configured provider. General web search still requires internet access.

References: [DuckDuckGo non-JavaScript search](https://duckduckgo.com/duckduckgo-help-pages/features/non-javascript),
[terms](https://duckduckgo.com/terms), [acceptable use](https://duckduckgo.com/acceptable-use),
[SearXNG DuckDuckGo engine](https://docs.searxng.org/dev/engines/online/duckduckgo.html),
[pi-web-access adapter](https://github.com/nicobailon/pi-web-access/blob/main/duckduckgo.ts).
The adapter was written for this extension; no external implementation was copied.
