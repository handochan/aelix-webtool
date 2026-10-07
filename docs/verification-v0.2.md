# v0.2 core investigation verification

Date: 2026-10-08 (Asia/Seoul)
Tracking: [parent #1](https://github.com/handochan/aelix-webtool/issues/1),
children [#2](https://github.com/handochan/aelix-webtool/issues/2),
[#3](https://github.com/handochan/aelix-webtool/issues/3),
[#4](https://github.com/handochan/aelix-webtool/issues/4),
[#5](https://github.com/handochan/aelix-webtool/issues/5),
[#6](https://github.com/handochan/aelix-webtool/issues/6),
[#7](https://github.com/handochan/aelix-webtool/issues/7).

## Implemented acceptance criteria

| Child | Implementation and meaningful evidence |
| --- | --- |
| #2 HTTP reliability | gzip/zlib/raw deflate decode; wire and decoder allocation bounds; malformed/truncated/concatenated/bomb failures; challenge header/HTML, login-only and JS-shell classification. Original DNS/redirect/deadline/cancellation gates remain active. |
| #3 Static extraction | Preserve nested document headers, tables, code, Unicode and safe links; strip site navigation/sidebar; use local Trafilatura only for unstructured articles. Six reader regressions failed before repair, including successful challenge-page misclassification and lost document headings. |
| #4 Snapshots | Immutable session-local IDs/hash/text; redirect aliases; concurrent same-URL deduplication; explicit refresh retains old content; TTL/LRU/accounted-byte bounds. A pre-implementation regression observed two downloads for two offsets; it now observes one. Old-session/cancelled publishers do not write snapshots. |
| #5 Passages | `web_read`, `web_find`; literal case-sensitive/insensitive matching; original Unicode character ranges and one-based line positions; complete hash/source metadata; missing/expired/cross-instance IDs and invalid ranges fail explicitly. No network or filesystem reads. |
| #6 Batches | Five inputs, up to three network operations, input-order results, per-item errors and explicit partial/all-failed states; bounded previews retain complete URLs/IDs. Host schema previously rejected `queries`; actual host validation now accepts batch forms and preserves scalar coercion. CLI all-failed batches exit nonzero and suppress upstream bodies. |
| #7 Resilience | Defaults stay zero retry/no fallback. Operator-only retry/route settings; explicit providers remain strict; Retry-After/cooldowns and total deadlines; correct endpoint/credential binding. Auth/config/argument/policy/challenge/unsupported/invalid-response failures remain fail-closed. Failure attempts and redaction are exercised. |

## Executed local validation

- Python 3.12.13: 190 passed, 0 failures/errors/skips; lint, formatter and
  Pyright pass. Tests run with `-W error::ResourceWarning`.
- Python 3.11.15 and 3.13.13: each 190 passed, 0 failures/errors/skips,
  installed-wheel suites in independent environments. JUnit files record
  each version's full suite.
- Built sdist and wheel; installed a fresh wheel beside the actual Aelix host
  in a separate throwaway environment: `BOUND`, one entry point, all four tools,
  `/web`, automatic discovery and real private-fetch rejection passed.
- Current local host source is `61f03b6718211c5e3ec81617374ff736881dd999`,
  version `0.1.0b2`. CI additionally uses the established pinned host revision
  `402a801325dcc335e2b7e1a7e829e9b5ebed93ca`.
- Installed-wheel live E2E using `openai-codex/gpt-5.6-luna` and real DuckDuckGo
  Lite search: `web_search -> web_fetch -> web_find -> web_read -> cited answer`
  completed with exit 0, no search fixture, and empty stderr. Fetch/find/read
  shared one snapshot ID and the exact same SHA-256 content hash; find returned
  54 literal matches and read reported `cached=true`.
- Model-free CLI fetch/find of public Python documentation also completed.

The model E2E uses a private temporary copy of existing model auth. Search keys
are removed from its child environment; auth is not borrowed by search adapters.
No user-global installation or original checkout was modified. Test environments,
logs/JUnit and raw model evidence are excluded from artifacts and commits.

## Review boundaries and limitations

- Snapshot memory is scoped to one service/session, capped at 32 entries and
  16 MB including text, compact line indexes and metadata. Each document's
  extracted text is capped at 2 MB; TTL is 30 minutes. IDs do not survive restart,
  reload or session changes, and no disk cache was introduced.
- Web extraction is static; PDF/OCR, JavaScript browsers, hosted reader fallback,
  provider-native authentication, MCP serving and multimedia are deferred.
- gzip/deflate support is bounded; Brotli and concatenated compressed streams
  fail explicitly.
- Actual Brave/Tavily/Exa keyed requests and a deployed SearXNG engine remain
  unrun without their credentials/service. Their request and resilience behavior
  is covered by deterministic/local-HTTP tests, not a ranking benchmark.
- Source [PR #8](https://github.com/handochan/aelix-webtool/pull/8) and
  [catalog PR #6](https://github.com/handochan/aelix-marketplace/pull/6) are merged.
  The published official catalog pins v0.2.0. Post-merge current-host testing,
  deployment, published-source installation and the v0.1 upgrade are recorded
  in [v0.2 registration results](registration-v0.2-results.md).
- Interactive TUI rendering has not been exercised; no custom renderer/widget
  is added. Actual host registration, lifecycle resets and tool dispatch are
  verified separately from real-model behavior.
