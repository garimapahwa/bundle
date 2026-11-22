"""Helpers: readable logging of the agent loop, and the Markdown and HTML versions of the report."""

from __future__ import annotations

import json
import re
from html import escape

from apify import Actor
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from .models import AuditReport

CATEGORY_TITLES = {
    'pii_exposure': 'Personal data sent but not shown',
    'overexposed_field': 'Other API fields sent but not shown',
    'secret': 'Secrets and keys in JavaScript',
    'internal_endpoint': 'Internal, admin, and staging endpoints',
    'internal_host': 'Internal and staging hosts',
    'source_map': 'Public source maps',
    'unreleased_flag': 'Unreleased feature flags',
}


def log_new_messages(messages: list[BaseMessage], already_logged: int) -> int:
    """Log every message the agent loop added since the last call, and return the new count.

    This is what you watch in the Log tab: the model deciding to call a tool (reason and act),
    then the tool result coming back (observe), until the model has enough to answer.
    """
    for message in messages[already_logged:]:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                Actor.log.info('AGENT -> %s(%s)', tool_call['name'], json.dumps(tool_call['args'], ensure_ascii=False)[:300])
            if not message.tool_calls and message.content:
                Actor.log.info('AGENT: %s', str(message.content)[:300])
        elif isinstance(message, ToolMessage):
            Actor.log.info('TOOL  <- %s returned %s', message.name, _describe(message.content))
            Actor.log.debug('Full tool result: %s', message.content)
    return len(messages)


def _describe(content: str | list) -> str:
    """Summarize a tool result in a few words for the log."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except ValueError:
        return str(content)[:200]
    if isinstance(data, dict) and 'api_responses' in data:
        return f'{data["api_responses"]} API responses, {data.get("js_files")} JS files ({data.get("source")})'
    if isinstance(data, dict) and 'by_category' in data:
        stats = data.get('stats', {})
        return f'score {stats.get("exposureScore")}, {stats.get("high")} high, {stats.get("medium")} medium, {stats.get("low")} low: {data["by_category"]}'
    if isinstance(data, dict) and 'peers' in data:
        return f'{len(data["peers"])} peers benchmarked, rank {data.get("rank")}'
    if isinstance(data, list):
        return f'{len(data)} search results'
    return str(content)[:200]


def report_to_markdown(report: AuditReport) -> str:
    """Render the report as Markdown."""
    avg = report.industry_average or {}
    lines = [
        f'# Exposure audit: {report.company} ({report.target})',
        '',
        f'**{report.headline}**',
        '',
        report.summary,
        '',
        f'- **Exposure score:** {report.exposure_score}/100 (0 = nothing exposed)',
        f'- **Rank:** {report.rank or "no peers benchmarked"}',
        f'- **Overexposed API fields per page:** {report.you.get("overexposedPerPage")} (industry average {avg.get("overexposedPerPage", "n/a")})',
        '',
        '## Top fixes',
        '',
    ]
    for number, fix in enumerate(report.top_fixes, start=1):
        lines += [f'### {number}. {fix.title}', '', fix.fix, '', f'**Why it matters:** {fix.why_it_matters}', '']
        if fix.related:
            lines += ['Findings: ' + ', '.join(f'`{r}`' for r in fix.related[:8]), '']
    lines += ['## Findings by category', '']
    lines += [f'- {CATEGORY_TITLES.get(k, k)}: {v}' for k, v in report.findings_by_category.items()]
    if report.peers:
        lines += ['', f'## Benchmark: {report.industry}', '', '| Site | Exposure score | Overexposed fields per page | High severity |', '| --- | ---: | ---: | ---: |']
        lines.append(f'| **You** | {report.exposure_score} | {report.you.get("overexposedPerPage")} | {report.you.get("high")} |')
        lines += [f'| {p.label} | {p.exposure_score} | {p.overexposed_per_page} | {p.high_severity} |' for p in report.peers]
        lines.append(f'| Industry average | {avg.get("exposureScore")} | {avg.get("overexposedPerPage")} | |')
    lines += ['', '## Caveats', '', *[f'- {c}' for c in report.caveats], '', 'Every finding is in the dataset. Field values are never stored.']
    return '\n'.join(lines)


# What each kind of finding means, for a reader who is not an engineer
PLAIN_ENGLISH = {
    'pii_exposure': "Your site sends this person's data to the browser, but the page never shows it. Anyone who opens the browser's developer tools can read it.",
    'overexposed_field': 'Your API sends more data than the page needs. Nothing on screen shows it, but anyone can read it in the browser.',
    'secret': 'A key or token is written into the code every visitor downloads. If it is a real secret, anyone can copy and use it.',
    'internal_host': 'The name of an internal server is visible in your public code. It tells outsiders how your systems are set up.',
    'internal_endpoint': 'Your public code points to an internal or admin address. It gives outsiders a place to start probing.',
    'source_map': 'Your original, readable source code can be downloaded by anyone, including comments and internal names.',
    'unreleased_flag': 'The names of features you have not launched yet are visible to anyone who looks, including competitors.',
}
VERDICTS = [
    (20, 'good', 'Looking good', 'Little is exposed. Keep it that way with a monthly check.'),
    (50, 'mid', 'Needs attention', 'Some things are exposed that should not be. The fixes below are quick wins.'),
    (101, 'bad', 'At risk', 'Your site exposes more than it should. Start with the first fix below.'),
]


def report_to_html(report: AuditReport) -> str:
    """Render the report as a self-contained page. Interactive with HTML and CSS only (no scripts)."""
    e = escape
    avg = report.industry_average or {}
    score = report.exposure_score
    _limit, tone, verdict, advice = next(v for v in VERDICTS if score < v[0])
    rank = report.rank.split(' (')[0] if report.rank else 'n/a'
    counts = {s: sum(1 for f in report.findings if f.get('severity') == s) for s in ('high', 'medium', 'low')}

    fixes = ''.join(
        f'<li class="fix"><input type="checkbox" id="fix{i}"><details{" open" if i == 1 else ""}>'
        f'<summary><label for="fix{i}" class="tick" title="Mark as done"></label><span class="n">{i}</span>'
        f'<span class="ft">{e(f.title)}</span></summary>'
        f'<div class="body"><p class="lbl">What to do</p><p>{e(f.fix)}</p>'
        f'<p class="lbl">Why it matters</p><p>{e(f.why_it_matters)}</p>'
        + (f'<p class="lbl">Affected</p><p class="chips">{"".join(f"<code>{e(_short(r))}</code>" for r in f.related[:4])}</p>' if f.related else '')
        + '</div></details></li>'
        for i, f in enumerate(report.top_fixes, start=1)
    )

    items = ''.join(
        f'<details class="item {e(f.get("severity", "low"))}"><summary><span class="dot"></span>'
        f'<span class="it">{e(f.get("finding", ""))}</span><span class="sev">{e(f.get("severity", ""))}</span></summary>'
        f'<div class="body"><p class="lbl">What this means</p><p>{e(PLAIN_ENGLISH.get(f.get("category", ""), ""))}</p>'
        f'<p class="lbl">Field or key</p><p><code>{e(f.get("field_or_key", ""))}</code></p>'
        f'<p class="lbl">How to fix</p><p>{e(f.get("fix", ""))}</p>'
        f'<p class="lbl">Where we saw it</p><p class="where">{e(f.get("evidence_url", ""))}</p>'
        + (f'<p class="lbl">Compared with peers</p><p>{e(f["peer_benchmark"])}</p>' if f.get('peer_benchmark') else '')
        + '</div></details>'
        for f in report.findings
    )

    max_score = max([score, *[p.exposure_score for p in report.peers], avg.get('exposureScore') or 0, 1])
    bars = [('You', score, True)] + [(p.label, p.exposure_score, False) for p in report.peers]
    if avg:
        bars.append(('Industry average', avg.get('exposureScore', 0), False))
    bench = ''.join(
        f'<div class="bar{" you" if you else ""}"><span class="bl">{e(label)}</span>'
        f'<span class="track"><span class="fill" style="width:{max(2, round(100 * float(v) / max_score))}%"></span></span>'
        f'<span class="bv">{e(_num(v))}</span></div>'
        for label, v, you in bars
    )
    if report.peers and avg:
        better = 'less' if score <= (avg.get('exposureScore') or 0) else 'more'
        compare = f'You are <strong>{better} exposed</strong> than the average of {len(report.peers)} similar sites. Lower is better.'
    else:
        compare = ''
    caveats = ''.join(f'<li>{e(c)}</li>' for c in report.caveats)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exposure audit: {e(report.company)}</title>
<style>
:root {{ --bg:#f6f6f3; --card:#fff; --ink:#1c1c1e; --muted:#6b6b70; --line:#e5e5e0; --soft:#efefea;
  --bad:#c62828; --bad-bg:#fdecea; --mid:#a15c00; --mid-bg:#fff3dc; --good:#2e7d32; --good-bg:#e8f5e9; --accent:#1a5fb4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141416; --card:#1e1e21; --ink:#f2f2f2; --muted:#a3a3a8; --line:#2e2e33; --soft:#2a2a2e;
  --bad:#ef6b6b; --bad-bg:#3a1f1f; --mid:#f0b45a; --mid-bg:#3a2e17; --good:#6cc070; --good-bg:#1c3320; --accent:#7aa7ff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:28px 16px 64px; }}
.eyebrow {{ color:var(--muted); font-size:13px; letter-spacing:.04em; text-transform:uppercase; margin:0 0 6px; }}
h1 {{ font-size:28px; line-height:1.2; margin:0 0 18px; }}
h2 {{ font-size:19px; margin:34px 0 6px; }}
.sub {{ color:var(--muted); margin:0 0 14px; font-size:15px; }}
.hero {{ display:flex; gap:22px; align-items:center; background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px; }}
.ring {{ --p:{score}; flex:0 0 112px; height:112px; border-radius:50%; display:grid; place-items:center;
  background:conic-gradient(var(--{tone}) calc(var(--p)*1%), var(--soft) 0); }}
.ring span {{ width:86px; height:86px; border-radius:50%; background:var(--card); display:grid; place-items:center; font-size:28px; font-weight:700; }}
.ring small {{ display:block; font-size:11px; color:var(--muted); font-weight:500; margin-top:-6px; }}
.verdict {{ display:inline-block; font-weight:700; font-size:14px; padding:3px 12px; border-radius:999px; color:var(--{tone}); background:var(--{tone}-bg); }}
.hero p {{ margin:8px 0 0; }}
.headline {{ font-size:17px; font-weight:600; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-top:12px; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.stat b {{ display:block; font-size:22px; }} .stat span {{ color:var(--muted); font-size:13px; }}
.summary {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; margin-top:12px; }}
ol.fixes {{ list-style:none; padding:0; margin:0; }}
.fix {{ position:relative; margin-bottom:10px; }}
.fix > input {{ position:absolute; opacity:0; pointer-events:none; }}
details {{ background:var(--card); border:1px solid var(--line); border-radius:12px; }}
summary {{ list-style:none; cursor:pointer; display:flex; align-items:center; gap:10px; padding:14px 16px; }}
summary::-webkit-details-marker {{ display:none; }}
summary::after {{ content:"›"; margin-left:auto; color:var(--muted); font-size:20px; transition:transform .15s; }}
details[open] > summary::after {{ transform:rotate(90deg); }}
.n {{ background:var(--ink); color:var(--bg); border-radius:999px; min-width:24px; height:24px; display:inline-grid; place-items:center; font-size:12px; font-weight:700; }}
.ft, .it {{ font-weight:600; }}
.tick {{ width:20px; height:20px; border:2px solid var(--muted); border-radius:6px; flex:0 0 20px; cursor:pointer; }}
.fix > input:checked + details .tick {{ background:var(--good); border-color:var(--good); box-shadow:inset 0 0 0 3px var(--card); }}
.fix > input:checked + details .ft {{ text-decoration:line-through; color:var(--muted); }}
.body {{ padding:0 16px 14px 50px; }}
.body p {{ margin:2px 0 10px; }}
.lbl {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; margin:10px 0 2px !important; }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
code {{ font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--soft); border-radius:6px; padding:2px 7px; word-break:break-all; }}
.where {{ font-size:13px; color:var(--muted); word-break:break-all; }}
.filters {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 12px; }}
.filters input {{ position:absolute; opacity:0; pointer-events:none; }}
.filters label {{ cursor:pointer; border:1px solid var(--line); background:var(--card); border-radius:999px; padding:5px 14px; font-size:14px; }}
#f-all:checked ~ .filters label[for=f-all], #f-high:checked ~ .filters label[for=f-high],
#f-medium:checked ~ .filters label[for=f-medium], #f-low:checked ~ .filters label[for=f-low] {{ background:var(--ink); color:var(--bg); border-color:var(--ink); }}
#f-high:checked ~ .list .item:not(.high), #f-medium:checked ~ .list .item:not(.medium), #f-low:checked ~ .list .item:not(.low) {{ display:none; }}
.radios {{ position:absolute; opacity:0; pointer-events:none; }}
.list {{ display:grid; gap:8px; }}
.item .dot {{ width:10px; height:10px; border-radius:50%; flex:0 0 10px; background:var(--muted); }}
.item.high .dot {{ background:var(--bad); }} .item.medium .dot {{ background:var(--mid); }}
.item .sev {{ font-size:12px; text-transform:capitalize; color:var(--muted); }}
.item .body {{ padding-left:36px; }}
.bench {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.bar {{ display:grid; grid-template-columns:120px 1fr 40px; gap:10px; align-items:center; margin:7px 0; font-size:14px; }}
.track {{ background:var(--soft); border-radius:6px; height:12px; overflow:hidden; }}
.fill {{ display:block; height:100%; background:#9aa0a6; border-radius:6px; }}
.bar.you .fill {{ background:var(--accent); }} .bar.you .bl {{ font-weight:700; }}
.bv {{ text-align:right; font-variant-numeric:tabular-nums; }}
.about {{ margin-top:30px; }}
.about .body {{ padding-left:16px; color:var(--muted); font-size:14px; }}
@media (max-width:560px) {{ .hero {{ flex-direction:column; align-items:flex-start; }} .body {{ padding-left:16px; }} .bar {{ grid-template-columns:90px 1fr 34px; }} }}
</style></head>
<body><main>
<p class="eyebrow">Bundle exposure audit · {e(report.industry)} · {e((report.scanned_at or '')[:10])}</p>
<h1>{e(report.company)}: what your website gives away</h1>

<section class="hero">
  <div class="ring"><span>{score}<small>of 100</small></span></div>
  <div><span class="verdict">{e(verdict)}</span><p class="headline">{e(report.headline)}</p><p class="sub">{e(advice)} Lower scores are better.</p></div>
</section>
<div class="stats">
  <div class="stat"><b>{e(rank)}</b><span>Rank among similar sites (1 is best)</span></div>
  <div class="stat"><b>{e(_num(report.you.get('high', 0)))}</b><span>Personal data issues</span></div>
  <div class="stat"><b>{e(_num(report.you.get('overexposedPerPage')))}</b><span>Unused data fields per page (industry {e(_num(avg.get('overexposedPerPage', 'n/a')))})</span></div>
  <div class="stat"><b>{len(report.findings)}</b><span>Things to review</span></div>
</div>
<div class="summary">{e(report.summary)}</div>

<h2>Fix these first</h2>
<p class="sub">Click a fix to see what to do and why. Tick the box when it is done.</p>
<ol class="fixes">{fixes}</ol>

<h2>Everything we found</h2>
<p class="sub">Click any finding to see what it means in plain words.</p>
<input type="radio" name="f" id="f-all" class="radios" checked><input type="radio" name="f" id="f-high" class="radios">
<input type="radio" name="f" id="f-medium" class="radios"><input type="radio" name="f" id="f-low" class="radios">
<div class="filters">
  <label for="f-all">All ({len(report.findings)})</label><label for="f-high">High ({counts['high']})</label>
  <label for="f-medium">Medium ({counts['medium']})</label><label for="f-low">Low ({counts['low']})</label>
</div>
<div class="list">{items or '<p>Nothing to report.</p>'}</div>

{f'<h2>How you compare</h2><p class="sub">{compare}</p><div class="bench">{bench}</div>' if report.peers else ''}

<details class="about"><summary>About this audit</summary><div class="body">
<p>We loaded your public pages like a visitor would, compared every piece of data your site sends with what the page actually shows, and checked your code for keys, internal addresses, and unreleased features. The same check ran on similar sites, shown only as Peer A, B, C.</p>
<p>No login, no probing, and no protections bypassed. Data values were never stored. This is not legal advice.</p>
<ul>{caveats}</ul></div></details>
</main></body></html>"""


def _short(path: str) -> str:
    """A readable name for a long field path: result.items[].widget.inventory_id -> inventory_id."""
    if '*' in path or '/' in path or len(path) < 40:
        return path
    parts = [p for p in re.split(r'[.\[\]{}]+', path) if p]
    return parts[-1] if parts else path


def _num(value: object) -> str:
    """174.0 -> 174, 2.7 -> 2.7."""
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
