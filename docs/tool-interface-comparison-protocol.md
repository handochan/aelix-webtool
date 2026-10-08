# Four versus three web tools: comparison protocol

Status: Experiment only; the published v0.2 API remains four tools.
Date: 2026-10-08 (Asia/Seoul)
Baseline runtime source: `5fcb5878cf67f97b459c1f40897d2534c2e1ca7d`.
Repository baseline: `f71b5cb231458ad60847e173d709a6e74eef2dea` (documentation only after that runtime).
Host: `cd6f7a5c31adf34e5a43c254026aa81d96d60339`.

## Question and candidate

Does combining snapshot reading and literal finding produce a better agent
interface than the published `web_search`, `web_fetch`, `web_read`, `web_find`?
The three-tool candidate keeps search and fetch separate and exposes finding
as `web_read(snapshot_id=..., find_text=...)`. Reading arguments and finding
arguments remain mutually exclusive. Schema defaults must not inject reading
arguments into a finding request.

Both arms use the same actual installed wheel, extraction, service, store,
request parsers, result formatting and Aelix host. The explicit test adapter
only changes registration/schema and translates `find_text` to the existing
finder's `query`. The candidate fetch description refers to its actual available
reader. The prototype has no public manifest or default-registration change.

## Controlled model trials

- Eight tasks: buried fact after search; two far-apart settings; a long section
  requiring several values; cross-page comparison; Unicode; literal match count;
  an absent deprecated key and its replacement; refresh followed by historical
  snapshot lookup.
- Answers are seeded and absent from the initial 8,000-character preview. Search
  snippets contain no answers. The scorer requires correct values, correct URLs
  and source text actually observed in successful tool outputs. Absence/count
  and refresh cases have additional evidence requirements.
- Identical prompts per pair; no prescribed tool names or call sequence. A fixed
  seed randomizes case order and the order of the two arms within each pair.
- Primary cohort: `openai-codex/gpt-5.6-luna`, low thinking, three repeats per
  case (24 pairs / 48 trials). Secondary cohort: `gpt-5.6-sol`, same thinking,
  one repeat per case (8 pairs / 16 trials). Availability/authentication is checked
  with a pilot first; pilots are excluded from these cohorts.
- Each trial has a fresh process and session-local store, with at most 12 tool
  calls and a 150-second deadline. No skills, agents, context files, automatic
  extensions, catalog maintenance or other tools are enabled.
- HTTP is an explicit deterministic fixture in both arms. It performs no live
  web requests and does not verify DNS, redirect, decompression or live provider
  behavior. Existing network-boundary tests and optional live smoke are separate.
- Auth is copied only to a private temporary directory and removed afterward.
  No provider search keys are used. Raw events and credentials are excluded from
  commits/artifacts; only aggregate results and reproducible methodology are public.

## Measurements and decision

Record task success, tool errors, invalid arguments, semantic operations, calls,
actual fixture downloads, provider-reported token usage (including cache fields),
wall time and serialized definition size. Report paired outcomes and median
paired differences; do not mistake lower billed uncached tokens or cache hits
for a smaller logical input. Model usage completeness is checked separately.

Prefer the three-tool candidate only if it preserves success across both tested
cohorts, introduces no additional argument errors or snapshot/network behavior
defect, and shows a concrete simplification or resource benefit. Otherwise keep
four tools. A small equal-success sample cannot prove general noninferiority;
latency and token differences are descriptive, not universal performance claims.
Migration of the existing public finder API also requires justification: an
unchanged call count and negligible definition saving alone are weak reasons
to replace an already validated interface.

Tests and model trials serve different purposes. A passing prototype test suite
does not establish comparative model performance, and a controlled model win
does not validate real web availability or public catalog publication.

## Completed execution notes

[Results and decision](tool-interface-comparison-results.md) retain the original
strict JSON-shape scores and identify a separate post-hoc functional assessment
for equivalent flat/nested answers and URL list/map/string citations. No model
trial, prompt, prototype schema or original evidence was changed for that
assessment. Four additional executions held working directory constant to
check first-request token counts; they are reported separately from the cohorts.
