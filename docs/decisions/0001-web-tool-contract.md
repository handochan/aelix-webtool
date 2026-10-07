# ADR-0001: Explicit search routing and bounded public-page reading

Status: Accepted for the first implementation
Date: 2026-10-08 (Asia/Seoul)
Amended by: [ADR-0002](0002-keyless-duckduckgo-search.md) for keyless search and `auto` selection.

## Context

The workspace started empty. Aelix main at
`402a801325dcc335e2b7e1a7e829e9b5ebed93ca` has an installed-extension contract
(`setup`, `aelix.extensions`, manifest API level 1), but no built-in web tools.
Issue [aelix-ai#18](https://github.com/handochan/aelix-ai/issues/18) remains open
and describes a built-in fetch MVP. This separately distributed extension is
the owner's newly requested direction; it does not silently close or implement
the old built-in proposal in the core repository.

The official marketplace currently has no entries. Listing requires a
reachable published source, an installed entry point and a manifest verdict of
`BOUND`. A working source checkout alone is not a registration.

Pi references include a broad host-independent search/fetch core in
`pi-web-access`, and current-model native search in `pi-web-search`. We adopt
explicit source metadata, provider isolation and cancellation. We do not copy
their implementation or introduce subscription credential reuse, browser
cookies, model-generated summaries, hosted reader fallback or repository clones.

## Decision

- Ship `aelix-webtool` / `aelix_webtool`, Apache-2.0, Python 3.11+, as a separate
  hatchling wheel. The factory and manifest share the same package directory.
- Keep requests, adapters and extraction host-independent. A thin Aelix adapter
  supplies two `AgentTool`s and `/web`; a CLI provides model-free verification.
- Search uses Brave, Tavily, Exa, or an operator-configured SearXNG endpoint.
  `auto` selects the first configured provider in the documented order
  SearXNG, Brave, Tavily, Exa. There is exactly one provider request per call.
  No implicit provider failover, retry, credential borrowing or query rewrite.
- Return source IDs derived from URLs, URLs, bounded snippets, provider name and
  retrieval time. Dates are provider-reported; an age filter is not evidence
  that a statement is current. Post-filter domain constraints locally as well.
- Fetch public HTTP(S) pages on ports 80/443. Use the connector's own checked
  DNS resolver, validate literals and each redirect, reject mixed DNS answers,
  verify TLS, ignore ambient proxies, and discard cookies. No separate DNS
  check followed by an unchecked second lookup.
- Only the operator-configured SearXNG search endpoint may reach a private
  network, and it cannot redirect. That exception never applies to `web_fetch`.
- Bound total requests to 25 seconds including redirects, search responses to
  1 MB, page responses to 2 MB, redirects to five, and displayed text to a
  bounded excerpt. Request identity encoding and reject compressed responses
  rather than decompressing attacker-controlled bodies without an input cap.
- Honor task cancellation and the host's awaitable abort signal; close each
  call's network resources before returning. Load performs no network activity.
- Extract static text or Markdown. No browser/JS, PDF, login, local-file access,
  remote reader service or persistent content cache. Offset paging re-fetches;
  return a content hash so callers can detect changes.
- Use environment settings only. Do not accept keys, headers or API endpoints
  as model arguments. Do not load credentials from project-controlled files.
  Expose classified errors without upstream bodies or client exception strings.
- Declare `net = true` honestly. Aelix's manifest net gate concerns declarative
  MCP servers; it does not sandbox arbitrary in-process Python sockets. Retain
  the host's normal extension-tool permission behavior.

## Acceptance criteria

1. Provider request mapping, Unicode queries, domain filters, empty/malformed
   results and classified failures have deterministic automated coverage.
2. Literal/private/mixed DNS, redirect, response-size, total-deadline and
   cancellation boundaries are exercised. Network resources are released.
3. Build and install an actual wheel in an isolated Aelix environment; the
   current host reports `BOUND`, discovers both tools and dispatches them.
4. Run a public-page live fetch. Paid-provider live search is a separate gate
   requiring an available key; mock success does not satisfy it.
5. Before public listing, publish a reviewed source commit, pin that 40-hex SHA
   in the marketplace entry, execute its actual submission gate and review the
   catalog PR. Local registration fixtures are not claimed as public listing.

## Consequences and follow-up

Search quality is provider-dependent and not ranked by this investigation.
No live cross-provider quality benchmark was run. Provider-native search may
later reduce configuration for supported Aelix models, but needs a separate
credential/endpoint/cost contract and real host E2E. Batching, source-content
storage, PDFs and JS pages are future decisions, not first-version promises.
