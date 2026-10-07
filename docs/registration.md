# Official extension registration

Source repository: [handochan/aelix-webtool](https://github.com/handochan/aelix-webtool).
The current listing and pinned installation source are recorded in the
[published official catalog](https://handochan.github.io/aelix-marketplace/catalog.json).
Catalog changes go through a reviewed PR and the checks described below.

Registered on 2026-10-08 (Asia/Seoul) through
[marketplace PR #4](https://github.com/handochan/aelix-marketplace/pull/4).
See [registration results](registration-results.md) for the source pin, actual
GitHub CI, deployment and published-catalog installation evidence.

The official catalog is [handochan/aelix-marketplace](https://github.com/handochan/aelix-marketplace).
Its public listing gate requires an actual reachable git/PyPI source, an
`aelix.extensions` entry point and an installed manifest verdict of `BOUND`.
The owner reviews the catalog PR. Listing and first-party maintenance are
distinct: the catalog is advisory, and contains no separate `official` badge
field. We do not invent one or claim that listing is a safety audit.

## Local gates

```bash
uv sync
uv pip install /path/to/aelix-ai/packages/aelix-ai \
  /path/to/aelix-ai/packages/aelix-agent-core \
  /path/to/aelix-ai/packages/aelix-coding-agent
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync pyright
uv build
uv run --no-sync python scripts/verify_host.py --aelix-source /path/to/aelix-ai
```

`verify_host.py` builds a fresh wheel and installs it with the real Aelix host
in a throwaway venv. It runs metadata-only `extension verify`, automatically
loads the installed entry point and dispatches the fetch tool through real host
types. It does not install into or change the user's existing Aelix tool env.

Keyed search adapters also need a live keyed call before their integration is
described as live verified. A model-free public fetch and deterministic local
SearXNG test are separate evidence. A real-model tool call is yet another gate.

## Publish and submit the reviewed source

1. Review the source, limitations and recorded verification. Publish the
   repository as `handochan/aelix-webtool` with its Apache-2.0 license. Preserve
   this implementation's documentation and tests in the published revision.
2. Choose the full 40-hex revision from that reachable repository. Generate a
   candidate using the **latest** marketplace catalog as the base:

   ```bash
   python scripts/catalog_entry.py --revision <published-40-hex-sha> \
     --base /path/to/aelix-marketplace/catalog.json \
     --output /path/to/catalog-candidate.json
   ```

   The script does not mutate the marketplace checkout. Review the candidate
   before replacing its catalog. There are no placeholder package sources and
   no display-only SHA256 field presented as enforced integrity.
3. Create a marketplace branch containing the one new entry and updated date.
   Run its actual `scripts/validate_catalog.py` and
   `scripts/verify_candidates.py` against the base catalog and current host.
   A local wheel check cannot substitute for installing the public git source.
4. Open the catalog PR, include verification evidence and complete its existing
   PR template. Let the owner review and merge it. Re-signing, if enabled, is
   the owner's procedure; the currently unsigned catalog is not represented as
   cryptographically endorsed.
5. After merge, verify the **published** Pages catalog and run discovery in an
   isolated agent directory. Only then describe this extension as registered.

The old [aelix-ai#18](https://github.com/handochan/aelix-ai/issues/18) describes
a built-in fetch extension. A reviewed decision should update that issue to
this separately distributed direction; it should not be closed solely because
this local implementation passes its tests.
