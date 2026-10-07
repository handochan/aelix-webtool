# ADR-0003: Reliable reading and bounded session investigation

Status: Accepted for the owner-requested core improvements
Date: 2026-10-08 (Asia/Seoul)
Amends: ADR-0001 extraction, repeated fetching and single-item APIs; ADR-0002 request policy only when explicitly configured.

## Scope

Implement the six core improvements from the current-source comparison with
pi-web-access. Keep provider/extraction logic independent of Aelix, import-free
host discovery, keyless default search and the existing network trust boundary.
PDF, browser rendering, hosted readers, provider-native login, MCP serving and
multimedia are separate future work.

## HTTP and extraction

Reject recognized HTTP-200 challenge pages, login-only pages and JavaScript-only
shells before they can become successful source evidence. Match strong challenge
markers, not a generic article title alone. Preserve only the response header
needed for challenge classification, never cookies or request credentials.

Support gzip and zlib/raw deflate with manual streaming decompression. Bound both
wire and decoded bytes to the existing 1 MB search / 2 MB fetch limits. Truncated,
malformed or concatenated streams fail explicitly. Brotli remains unsupported
rather than using an unbounded decoder. DNS validation, TLS, redirects, cookie/
proxy isolation, total deadlines and resource cleanup stay enforced.

Use explicit document structure for technical docs so headings, code and tables
remain intact. For unstructured articles, use Trafilatura's local extraction;
never its network fetch helpers. Preserve safe resolved links and Unicode.

## Snapshots and passages

Each running service/extension owns an in-memory snapshot store: immutable full
text, opaque ID, actual URL, content hash, retrieval time and line positions.
Default limits: 32 snapshots, 16 MB accounted text/index/metadata, 2 MB text per snapshot and 30-minute
TTL. Evict least-recently-used entries. No disk cache or import-time I/O.

`web_fetch` reuses its current URL snapshot unless `refresh=true`. A refresh
creates a new ID and leaves the previous immutable snapshot readable until
expiry/eviction. `web_read` and `web_find` require a snapshot ID and perform no
network I/O; they return bounded original-character ranges, line positions and
source/hash metadata. Search is literal, case-sensitive or insensitive, not a
model-controlled regular expression. Missing/expired IDs are explicit errors.

Session start/shutdown clears snapshots and advances a generation. In-flight work
from an old generation may not publish into the new store. Concurrent fetches
of one URL share a lock and reuse the committed snapshot; cancellation must not
leave background publishers or permit cross-session retrieval.

## Batch and resilience

Existing single-item arguments remain valid. Search and fetch also accept up to
five queries/URLs, with three concurrent operations, input order preserved,
per-item errors and bounded combined text. All malformed arguments are validated
before I/O. Policy rejection affects that item; cancellation drains the batch.

Default routing stays one provider with zero automatic retries/failover.
`AELIX_WEB_RETRIES=0|1` permits bounded transient retries, respecting Retry-After
within a 25-second total search deadline. `AELIX_WEB_FALLBACK_PROVIDERS` explicitly
enumerates at most two additional configured providers for an `auto` call.
An explicit tool `provider` never switches providers. There is exactly one
selected provider per attempt; credentials bind to its fixed endpoint.

Only retryable network/timeout/HTTP-5xx/rate-limit and explicit usage-limit errors
may move along an operator-declared route. Auth, configuration, bad arguments,
unsupported filters, network policy, invalid responses and challenges fail
closed. DuckDuckGo challenges are never retried or bypassed. Record provider
attempts and classified errors without credentials or upstream bodies.

## Verification

Each of the six tracked children needs its own failing regression and acceptance
evidence. Verify all Python 3.11/3.12/3.13 gates, actual installed-wheel manifest
and host dispatch, session isolation, and a real-model search/fetch/read/find
flow. Describe mock, local HTTP, live provider and model evidence separately.
The official v0.1 source pin is updated only through a reviewed catalog change.
