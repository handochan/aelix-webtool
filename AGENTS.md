# Aelix Web Tools

Python 3.11+ installed Aelix extension. The design and scope live in
`docs/decisions/0001-web-tool-contract.md`; current validation lives in
`docs/verification.md`. Keep README, manifest and actual contributions aligned.

Keep provider adapters and extraction independent of Aelix. Import host types
only when loading the factory; importing the package must perform no I/O.
Do not add beta placeholder Aelix PyPI packages as runtime dependencies.

Search routes to exactly one explicitly selected provider. Do not add implicit
failover, API credential reuse, model calls or remote readers without a new
decision. Never expose keys or upstream error bodies. Private access belongs
only to the operator-configured SearXNG endpoint, never model-supplied fetch URLs.

Changes to network policy require boundary tests covering the connector's actual
DNS path, redirects, size/deadline and cancellation. Build/install an actual
wheel and run `scripts/verify_host.py` for packaging/host changes. Record mock,
real HTTP, live provider, model E2E and public registration evidence separately.

Use `uv run --no-sync` after installing the real host packages for development;
`uv sync` can remove dependencies absent from this extension's lock file.
Public catalog entries must pin a reachable reviewed commit. A generated local
catalog is not a registered extension. Keep `.devstate`, `.omc`, `.claude` and
credentials out of artifacts and commits.
