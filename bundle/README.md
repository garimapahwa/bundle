**For founders, CISOs, and product teams: see what your web app gives away to every visitor, how you compare with your industry, and the five fixes that matter most. One audit, about 3 minutes.**

## What does Bundle do?

Bundle is an **AI agent that audits your public web app for business exposure** and
**benchmarks you against industry peers**. It opens your site like a visitor would (public pages
only, no login, no probing) and checks:

- **Unused API fields.** For every API response your pages load, Bundle compares the JSON fields
  with what the page actually shows. A field the UI never shows was sent for no reason. If it
  looks like **personal data** (PAN, Aadhaar, phone, email, date of birth, account numbers,
  internal IDs, risk scores), it is **high severity**.
- **Secrets and keys** in your JavaScript. Keys that are public by design (storefront,
  error-tracking, and browser map keys) are labelled as such, not as leaks. Values are always masked.
- **Internal hostnames and endpoints** in production code, and **public source maps**.
- **Unreleased feature flags** visible in your live flag config.

Then it runs **the same scan on 3 to 5 peers** (it finds them on Google, or you name them) and
gives you an **exposure score**, your **rank in your industry**, and the **top 5 fixes**, with
why each matters, including the **DPDP Act, 2023** where personal data is involved.

The agent chooses its own tools, and every step shows in the run log:

```
[agent] calling fetchSite on example.in (up to 3 pages)
[agent] loaded example.in with chromium
[agent] calling auditExposure on example.in (6 API responses, 36 JS files)
[agent] calling findPeers on example.in ("beauty and personal care brands in India" via apify/google-search-scraper)
[agent] calling benchmarkPeers on example.in (3 peers, 2 pages each)
```

## Why use Bundle?

- **Finds what testing misses.** Over-sent fields are invisible on screen, so nobody notices
  them, until someone opens DevTools. Bundle lists them with the exact field paths to fix.
- **A number your board understands.** An exposure score from 0 to 100 and your rank in your
  industry, not a 200-line scanner dump.
- **Fixes in priority order,** each tied to real findings and explained in plain business terms.
- **Honest by design.** The agent can only cite findings the code actually made. Public-by-design
  keys are not called secrets. Personal-data law is only mentioned when personal data was found.
- **Private by design.** Field values are never stored, logged, or sent to the AI model:
  findings hold field paths and the kind of data only. Peers appear by name with counts and
  scores only, never their individual findings (or tick **Anonymize peers**).

## How to use Bundle

1. Click **Try for free**.
2. Enter **your website** and **your industry** in plain words.
3. Leave **Peer websites** empty to let the agent find competitors, or list 3 to 5 yourself.
4. Click **Start**. An audit takes 2 to 8 minutes, depending on how many peers are scanned fresh.
5. Open **Output**: **Report (web page)** for the summary, **Findings** for the table.

## Example input

```json
{
    "targetUrl": "https://www.example.in",
    "industry": "online beauty and personal care brand",
    "peerUrls": [],
    "maxPages": 3
}
```

`llmApiKey` is optional: add your own OpenRouter key, or leave it empty to use the Apify
OpenRouter proxy, billed to your Apify account.

## Example output

The **Findings** table has one row per finding, grouped so it stays short. You can download the
dataset in various formats such as JSON, HTML, CSV, or Excel. These rows come from real runs on
Indian consumer sites (names removed):

| Severity | Finding | Field or key | Fix |
| --- | --- | --- | --- |
| medium | Internal hostname in JavaScript | `search-aggregator.<region>-<co>.internal` | Remove internal hostnames from production code. |
| medium | Public source map (your source code) | `https://<site>/cdn/shop/t/148/assets/global.js.map` | Stop serving .map files in production. |
| low | 517 unused fields in data/json API | `inventory_id, inventory_name, personalization, +108 more` | Send only the fields the page shows. |
| low | Public client key in JavaScript | `008b******** (32 chars, masked)` | Meant to be public. Check its permissions; no rotation needed. |
| low | Unreleased feature flag | `inr_wallet_re_arch_enabled, us-stocks-v2-enabled, +23 more` | Evaluate flags on the server; send only the result. |

Each row also has `category`, `evidence_url` (where it was found), and `peer_benchmark`, for
example *"You 139 vs industry 2.7 unused fields per page"*.

The **report** (`report.html`, `report.md`, and `REPORT` as JSON) has the exposure score, the
rank against named peers, the industry average, a "How we checked" diagram, a fix checklist,
findings you can filter by severity, a benchmark chart, and caveats. From a headline the agent wrote for a large beauty retailer (abridged, name removed):

> "…ships 418 API fields the UI never renders (139.3 per page, versus a peer average of 2.7) …
> and an internal hostname, ranking 2nd least exposed of 4 peers on overall score."

## Severity and score

| Severity | What | Weight |
| --- | --- | ---: |
| High | Personal data sent but not shown. High-risk keys (AWS, `sk_live`, private keys). | 15 |
| Medium | Other secrets, internal hosts and endpoints, public source maps | 5 |
| Low | Unused fields, public client keys, unreleased flags (low points capped at 20) | 1 |

The exposure score is the weighted sum, capped at 100. Lower is better. Every peer is scored the
same way.

## How much does a Bundle audit cost?

Bundle uses **pay per event**: **$1.99 per completed audit**. A run that cannot load your site
is not charged.

On top of that you pay the small usage of two tools the agent calls with your Apify account:
the AI model through the Apify OpenRouter proxy (under $0.01 per audit) and one Google search
(under $0.01). There is no other cost.

## Tips

- **Use saved captures** re-runs an audit in about a minute without loading the sites again.
- Give **Peer websites** yourself to compare against the exact competitors you care about.
- Run it on a monthly [schedule](https://docs.apify.com/platform/schedules) to track your score
  against your industry over time.
- Point **Your website** at a data-heavy public page (a product, pricing, or search page) for a
  deeper audit than a marketing homepage gives.

## Ethics and limits

- **Audit sites you own or are allowed to assess.** Peers are scanned only on public pages, with
  no login, no form submission, and no probing, and appear only as counts and scores.
- **No bypassing protections.** Bundle loads sites with a normal full browser. If a site still
  refuses, Bundle stops, says so in the report, and does not charge. It never solves CAPTCHAs.
- **Values are never stored.** Not in the dataset, the report, the log, or the AI prompt.
  Secret-like strings are masked and never tested.
- **Public pages only.** Logged-in areas are where most personal data lives, and Bundle does not
  see them. A clean result is not a clean bill of health.
- **Not legal advice.** DPDP notes explain why a finding may matter; ask your counsel what it
  means for you.

Found a bug or a false alarm? Open an issue in the **Issues** tab.
