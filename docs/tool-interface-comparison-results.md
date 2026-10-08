# Web tool interface comparison: retain four public tools

Date: 2026-10-08 (Asia/Seoul)
Decision: retain the published v0.2 four-tool interface. The evaluated three-tool
prototype is viable, but this comparison does not justify replacing that API.
The earlier three-tool preference was a design hypothesis, not measured evidence.

Method: [comparison protocol](tool-interface-comparison-protocol.md).
Data: [per-trial metrics, definitions and source fingerprints](evaluations/tool-interface-comparison-2026-10-08.json).

## What ran

The real Aelix host dispatched tools from the actual installed v0.2 wheel.
`openai-codex/gpt-5.6-luna` ran eight tasks three times per arm (24 pairs), and
`gpt-5.6-sol` ran the same tasks once per arm (8 pairs), both with low thinking.
There were 64 main trial executions: 32 for each interface. Four pilot executions
and a four-execution common-working-directory control are excluded from the main
cohorts. These are agent trials with multiple model requests, not 64 single API
requests.

Prompts named goals rather than tools; both arms had identical documents, task
prompts, engine/store/result behavior and limits. The three-tool adapter combined
reading/finding under `web_read(find_text=...)` and forwarded to the existing
executors. Only the public registration, schema and corresponding descriptions
differed. Case and arm order were seeded; model sampling was not seeded.

HTTP was a fixed fixture, so search ranking, availability and page changes could
not contaminate this interface comparison. The refresh case deliberately advanced
its document on a new download. This is real-model/real-host evidence with mocked
HTTP, not new live DuckDuckGo or keyed-provider evidence.

## Main results

| Metric | Four tools | Three tools |
| --- | ---: | ---: |
| Correct values, cited URLs and retrieved evidence | 32 / 32 | 32 / 32 |
| Invalid-argument tool results, recovered by the agent | 1 | 3 |
| Tool calls, total | 106 | 102 |
| Tool calls, median per trial | 3 | 3 |
| Actual fixture page downloads | 40 | 40 |
| Serialized tool definitions | 3,770 bytes | 3,747 bytes |
| First-request logical input difference per identical pair | reference | +16 tokens in all 32 pairs |
| Reported tokens, total | 330,239 | 309,258 |
| Reported tokens, median per trial | 8,596 | 8,562 |
| Wall time, median per trial | 8.730 seconds | 8.250 seconds |

These pooled totals describe this workload and its weighting. The model cohorts
and repeated task types are not independent samples from all web workloads.

| Cohort | Functional successes four / three | Invalid arguments four / three | Median paired token difference, three minus four | Median paired wall-time difference |
| --- | --- | --- | ---: | ---: |
| Luna, 24 pairs | 24 / 24; 24 / 24 | 1 / 3 | +48 tokens | -0.080 seconds |
| Sol, 8 pairs | 8 / 8; 8 / 8 | 0 / 0 | +78.5 tokens | -0.027 seconds |

The first-request measure includes cached input once. All assistant responses
reported usage, and all reported totals matched uncached input + cached input +
output; reasoning was already included in output. No dollar-cost estimate is
inferred from OAuth/subscription access. The common-working-directory control
repeated +16 first-request input tokens for both tasks, so the main per-arm
directory names did not explain that result.

## Why keep four

1. A 25% reduction in the number of names produced only a 0.61% reduction in
   serialized definition bytes. The actual first model request used 16 more
   input tokens with the three-tool schema. Conditional argument rules and
   additional descriptions offset the removed definition.
2. Functional success tied in this sample. The three-tool candidate did not
   improve success or median call count. All four observed argument errors were
   overlarge `context_chars` requests in the long-section case: four tools had
   one such error, three tools had three. They were rejected before execution
   and recovered; none were mixed-mode or private-access failures. This small
   observation does not establish a universal error-rate difference.
3. Three tools did save 6.35% of aggregate reported tokens and four calls in this
   workload. That benefit was concentrated in refresh/history: 25 versus 19 calls
   and 84,050 versus 52,637 tokens. In the long-section case, three tools instead
   used 15 versus 13 calls and 59,466 versus 50,913 tokens. Outside refresh/history,
   the three-tool arm used 4.24% more aggregate tokens. Neither cohort's median
   paired token difference showed a reduction.
4. An interface replacement would remove the existing model-visible `web_find`
   API and add mode-dependent rules to `web_read`. Keeping the simple separate
   contracts avoids that migration while preserving the same functionality.

The decision is to preserve four tools for now, rather than claim that four is
always superior. If history-heavy usage becomes dominant, the three-tool shape
deserves another evaluation. Improving redundant follow-up reading through tool
guidance is also possible without replacing an API; it was not mixed into these
frozen trials.

## Scoring audit

The original scorer required `{"answers": {...}, "sources": [...]}`. Several
otherwise correct responses returned the requested keys at the JSON root or
used equivalent URL maps/strings. Their initial failures reflected formatting,
not incorrect evidence retrieval. Original scores and all raw events were kept.

A separate, explicitly post-hoc functional assessment accepted those equivalent
structures while retaining the same named values, exact URLs, observed source
text, absence/count proof and historical-snapshot requirements. It did not accept
guessed values without tool evidence or rerun/selectively discard any trial.
Shape compliance remains separate: Luna 9/24 versus 10/24 and Sol 4/8 versus 4/8.
Tests prove that the supplemental scorer still rejects guesses and wrong values.

## Validation and scope

- Python 3.11.15, 3.12.13 and 3.13.13: each 211 tests passed, with zero skips,
  failures or errors and `ResourceWarning` treated as an error.
- Ruff lint/format and source Pyright passed with the actual host interpreter.
- `scripts/verify_host.py` built and installed an actual wheel beside host
  `cd6f7a5c31adf34e5a43c254026aa81d96d60339`: `BOUND`, automatic discovery of
  the existing four tools, `/web` and real private-fetch rejection passed.
- Prototype tests cover the real host schema, no injected read defaults in find
  mode, mixed/unknown inputs, immutable source/hash sharing, reset, cancellation
  and private-fetch rejection. Production network policy is unchanged.
- No source package, public manifest, README tool contract or official catalog
  pin was changed. Model transcripts, HTTP journals and test environments stay
  under ignored `.devstate`; temporary auth copies were removed. Credentials
  and the user's global installation were not written by this harness.

Both models belong to one provider/model family. Eight synthetic task types,
limited repeats and fixed HTTP cannot establish performance for other models,
real ranking, authenticated pages or production task distributions. Latency is
descriptive; passing local checks does not mean comparative model trials ran in
GitHub CI. Public registration still refers to the existing v0.2 runtime.

## Reproduce with an installed host and v0.2 wheel

```bash
python scripts/compare_tool_interfaces.py --aelix /path/to/test-env/bin/aelix \
  --model gpt-5.6-luna --repeats 3 --output .devstate/new-luna-run
python scripts/compare_tool_interfaces.py --aelix /path/to/test-env/bin/aelix \
  --model gpt-5.6-sol --repeats 1 --output .devstate/new-sol-run
python scripts/rescore_tool_interfaces.py .devstate/new-luna-run .devstate/new-sol-run
python scripts/check_tool_interface_context.py --aelix /path/to/test-env/bin/aelix \
  --output .devstate/new-cwd-control
```

These commands intentionally use existing configured model auth and start real
model requests. Supply a new output directory to retain previous evidence.
