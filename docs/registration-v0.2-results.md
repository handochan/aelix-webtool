# v0.2 official catalog publication results

Date: 2026-10-08 (Asia/Seoul)
Status: Source and catalog merged, deployed, installed and upgraded through the
published official catalog.

## Published revisions

- Package: `aelix-webtool 0.2.0`.
- Source [PR #8](https://github.com/handochan/aelix-webtool/pull/8) merged at
  `2026-10-07T23:38:07Z` as `5fcb5878cf67f97b459c1f40897d2534c2e1ca7d`.
- Catalog [PR #6](https://github.com/handochan/aelix-marketplace/pull/6) merged at
  `2026-10-07T23:43:08Z` as `fa2c7df351b2d8754a7c9c2e78721e9ef3190fe6`.
- Exact installation source:
  `git+https://github.com/handochan/aelix-webtool.git@5fcb5878cf67f97b459c1f40897d2534c2e1ca7d`.
- The actual HTTP 200 response from the
  [official catalog](https://handochan.github.io/aelix-marketplace/catalog.json)
  contains this source and version. All other entries, including the latest
  memory update already on the catalog base, were preserved.
- Parent #1 and children #2–#7 are closed after the implementation merge.

The catalog pins the reviewed runtime commit, rather than following `main`.
Subsequent documentation commits record publication and upgrade instructions
without changing that runtime.

## Executed checks

| Check | Result and evidence |
| --- | --- |
| Source PR CI | Python 3.11/3.12/3.13 each passed 190 tests, lint/types, builds and installed-wheel binding/discovery/dispatch. [Run 37668901204](https://github.com/handochan/aelix-webtool/actions/runs/37668901204). |
| Merged-source main CI | All three version jobs passed on the exact pinned merge commit. [Run 37703382326](https://github.com/handochan/aelix-webtool/actions/runs/37703382326). |
| Current-host public-source tests | Host `cd6f7a5c31adf34e5a43c254026aa81d96d60339`, Python 3.13.13: installed the public git source via Aelix CLI, verified the recorded pin in a strict repeat, then ran 190 installed-source tests with zero failures/errors/skips and ResourceWarning treated as an error. |
| Actual built-wheel host check | `scripts/verify_host.py` built and installed a new wheel with that current host; manifest `BOUND`, automatic entry-point discovery, all four tools, `/web` and private-fetch rejection passed. |
| Submission gate | Local `scripts/verify_candidates.py` installed the changed source into a fresh environment and returned `BOUND`; [GitHub run 37703677749](https://github.com/handochan/aelix-marketplace/actions/runs/37703677749) repeated it successfully. |
| Catalog parsing | Caps/schema and the actual runtime parser retained both entries locally and in [PR CI](https://github.com/handochan/aelix-marketplace/actions/runs/37703677825). [Merged-main validation](https://github.com/handochan/aelix-marketplace/actions/runs/37703837644) passed. |
| Pages deployment | [Run 37703837792](https://github.com/handochan/aelix-marketplace/actions/runs/37703837792) passed on the catalog merge commit; the default public URL served the expected bytes afterward. |
| Published-catalog installation | An isolated agent directory with no catalog override refreshed the actual default URL and discovered v0.2.0. Catalog installation recorded the source pin; a `--strict` repeat succeeded. Installed metadata matched the exact commit, `verify` reported `BOUND`, and real host loading found `web_search`, `web_fetch`, `web_read`, `web_find` and `/web`. |
| Existing v0.1 upgrade | A separate environment installed and pinned the public v0.1 commit first. Installing the new catalog entry without accepting its new pin correctly exited 2 before pip started and kept v0.1 installed. Repeating with `--strict --repin` installed exactly v0.2.0; metadata, `BOUND`, all four tools and real private-fetch rejection passed. |

The upgrade's `--repin` explicitly accepts the published new commit. It does not
disable verification; no `--no-verify` was used. Fresh installations used normal
first-acquisition pinning followed by strict verification, without `--repin`.

All checks used private test environments. The user's global installation,
credentials and prior implementation/registration evidence were preserved.
Raw local logs, metadata, JUnit and install results are excluded from artifacts
and commits under `.devstate/v02-publication-*/`. Public PRs and CI links provide
the durable publication record.

## Install or upgrade

For a new installation:

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool
aelix extension verify aelix-webtool
```

For an existing v0.1 git installation, review the new source displayed by the
installer and explicitly accept the new pin:

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool --repin
aelix extension verify aelix-webtool
```

Restart Aelix or run `/reload` afterward. `/web` displays provider availability;
the default with no provider settings uses keyless DuckDuckGo Lite.

## Validation limits

Pre-merge real DuckDuckGo and real-model search/fetch/find/read evidence is
recorded separately in [v0.2 verification](verification-v0.2.md). Publication
checks here are model-free and do not imply new live keyed-provider coverage.
Brave/Tavily/Exa live keyed calls, deployed SearXNG and interactive TUI rendering
remain unrun. Static reading excludes PDF/OCR, JavaScript rendering and media.
The advisory catalog remains unsigned; no PyPI release or new signing scheme
was introduced.
