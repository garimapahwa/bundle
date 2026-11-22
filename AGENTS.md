# Guidance for AI coding tools

This repo is **Bundle**: one Apify Actor that audits a web app's public pages for business
exposure and benchmarks it against industry peers. What it does and how to run it is in
[`README.md`](./README.md); the Apify Store page is [`bundle/README.md`](./bundle/README.md).

The Actor lives in [`bundle/`](./bundle). There is one Actor and one `.actor/` folder. Do not
split it into separate tool Actors.

## Defer to the Apify Actor Development skill

For scaffolding, building, debugging, or deploying the Actor, defer to the **Apify Actor
Development Agent Skill** (`apify-actor-development`, in `.claude/skills/`). Do not duplicate its
instructions here.

## How Bundle is built

- **The agent loop** is LangChain `create_agent` in `bundle/my_actor/main.py`, with a system
  prompt, the Pydantic `AuditDraft` as `response_format`, and a recursion limit. The LLM runs
  through the Apify OpenRouter proxy (`https://openrouter.apify.actor/api/v1`, `APIFY_TOKEN` as
  the key), or the user's own OpenRouter key from the `llmApiKey` input.
- **The tools** are plain functions in `bundle/my_actor/tools.py`: `fetchSite`,
  `auditExposure`, `findPeers`, and `benchmarkPeers`. Each logs
  `[agent] calling <tool> on <site>`. Only `findPeers` runs another Actor
  (`apify/google-search-scraper`).
- **Pure modules** hold the logic and have tests: `exposure.py` (API fields vs rendered DOM, PII),
  `extractor.py` (secrets, endpoints, and flags in JavaScript, with a CLI), and `audit.py`
  (findings, severity, score).
- **Numbers come from code, words from the LLM.** The score, rank, and industry average are
  computed in code. The LLM finds peers, picks the order of its tools, and writes the fixes.
  Fixes are checked against real findings before they are saved.
- **Output:** one dataset row per finding (`FindingRow`), plus `REPORT`, `report.md`, and
  `report.html` in the key-value store. Pay per event: one `question-answered` charge per
  completed audit.

## Rules that must not break

- **Never store, log, or send a field value** (to the dataset, the report, the log, or the LLM).
  Findings hold field paths and the kind of data only. Secret-like strings are always masked.
- **Peers: counts and scores only.** Peers are named by site (or Peer A to E when `anonymizePeers`
  is on), but their individual findings and field names never appear in any output.
- **Public pages only**: no login, no form submission, no probing, no bypassing bot checks.
- Tools return short, trimmed results, never whole responses or bundles.

## Workflow

```bash
cd bundle
python -m pytest -q tests     # must pass before every push
apify push                     # the OpenRouter proxy only works on the Apify platform
```

## Writing style (for any docs edits)

- "Actor" is always capitalized when it means an Apify Actor.
- Use "Apify Store", "Apify Console", "Apify Proxy" (no "the"), but "the Apify platform".
- Headings in sentence case. No em dashes; use a spaced hyphen ` - ` instead.
- US English, Oxford comma.
