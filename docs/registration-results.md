# Initial v0.1 catalog registration results

Date: 2026-10-08 (Asia/Seoul)
Status: v0.1 registration completed. The current published v0.2 entry and upgrade
evidence are recorded in [v0.2 registration results](registration-v0.2-results.md).

## Published source and catalog

- Source: [handochan/aelix-webtool](https://github.com/handochan/aelix-webtool), public.
- Catalog entry: `aelix-webtool`, version `0.1.0`.
- Exact installation source:
  `git+https://github.com/handochan/aelix-webtool.git@880e4bf2ec21d7029de3e4af61015c43d8c1b921`.
- Registration: [aelix-marketplace PR #4](https://github.com/handochan/aelix-marketplace/pull/4),
  merged at `2026-10-07T16:39:36Z` as
  `026fcf76be77181193d64acf9719c848d46c04c1`.
- Published document: [official catalog](https://handochan.github.io/aelix-marketplace/catalog.json).
  Its actual HTTP response contains the entry and exactly the source pin above.
- The existing `aelix-memory` entry was preserved without changes.

The catalog pins the reviewed source revision rather than following moving
`main`. Later documentation-only commits record this publication and install
instructions; they do not change the installed runtime code.

## Executed publication checks

| Check | Result and durable evidence |
| --- | --- |
| Source GitHub CI, Linux Python 3.11/3.12/3.13 | All three jobs passed; each ran 128 tests, lint/types, builds and installed-wheel binding/discovery/dispatch. [Run 37652714953](https://github.com/handochan/aelix-webtool/actions/runs/37652714953), source revision `880e4bf2ec21d7029de3e4af61015c43d8c1b921`, host revision `402a801325dcc335e2b7e1a7e829e9b5ebed93ca`. |
| Actual marketplace submission gate | Locally installed the exact public git source in a throwaway environment with current Aelix and returned `BOUND`. GitHub repeated the source-install gate successfully. [Run 37653496025](https://github.com/handochan/aelix-marketplace/actions/runs/37653496025). |
| Catalog schema and authoritative runtime parser | Both entries retained; local validation and [PR CI](https://github.com/handochan/aelix-marketplace/actions/runs/37653496050) passed. |
| Main catalog after merge | [Run 37653784992](https://github.com/handochan/aelix-marketplace/actions/runs/37653784992) passed on the merge commit. |
| GitHub Pages | [Deploy run 37653785050](https://github.com/handochan/aelix-marketplace/actions/runs/37653785050) completed successfully on the merge commit. |
| Real current-host CLI installation | Aelix revision `61f03b6718211c5e3ec81617374ff736881dd999`, Python 3.13.13: installed from the public pinned git source, recorded the expected commit pin, then passed a `--strict` repeat and `extension verify` (`BOUND`). Installed entry-point discovery, actual tool dispatch and all 128 extension tests also passed. |
| Published-catalog discovery and installation | The default official URL was refreshed into an isolated agent directory; `discover aelix-webtool` returned one match. `discover install aelix-webtool --yes --strict` resolved exactly the listed source, verified the previously recorded pin and installed successfully; subsequent verification reported `BOUND`. |

On the first installation attempt, `--strict` correctly refused the absence of
an out-of-band provisioned pin before pip ran. The normal first-acquisition
flow then recorded the reviewed commit, and strict verification succeeded
against that record. No `--no-verify` or `--repin` bypass was used.

The CLI/install/discovery checks ran in private test environments. The user's
global Aelix installation, credentials and existing checkouts were preserved.
Raw local evidence is under the gitignored `.devstate/official-registration-*/`
directory; the public CI and merged PR are the durable registration record.

## Install

```bash
aelix extension discover --refresh
aelix extension discover install aelix-webtool
aelix extension verify aelix-webtool
```

Restart Aelix or run `/reload`. `/web` reports selectable providers. With no
provider settings, `web_search` uses DuckDuckGo Lite without a search API key.

## Scope of the result

This is an entry in Aelix's official advisory catalog, with owner-maintained
public source. It is not a safety audit or a signature endorsement. No PyPI
publication or new catalog signing scheme was introduced.

Keyless live search and real-model search/fetch were verified before publication;
see [local verification](verification.md). Brave/Tavily/Exa live keyed calls,
a deployed SearXNG engine and interactive TUI operation remain outside that
executed evidence. The old built-in-fetch proposal `aelix-ai#18` remains a
separate scope and was not closed by this catalog registration.
