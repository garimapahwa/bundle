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


def report_to_html(report: AuditReport) -> str:
    """Render the report as a clean, self-contained HTML page."""
    e = escape
    avg = report.industry_average or {}
    tone = 'bad' if report.exposure_score >= 50 else 'mid' if report.exposure_score >= 20 else 'good'
    fixes = ''.join(
        f'<article class="fix"><h3><span class="n">{i}</span>{e(f.title)}</h3><p>{e(f.fix)}</p>'
        f'<p class="why"><strong>Why it matters:</strong> {e(f.why_it_matters)}</p>'
        + (f'<p class="rel">{"".join(f"<code>{e(_short(r))}</code>" for r in f.related[:3])}</p>' if f.related else '')
        + '</article>'
        for i, f in enumerate(report.top_fixes, start=1)
    )
    found = ''.join(
        f'<tr><td><span class="sev {e(x["severity"])}">{e(x["severity"])}</span></td><td>{e(x["finding"])}</td>'
        f'<td><code>{e(x["field_or_key"])}</code></td><td>{e(x["fix"])}</td></tr>'
        for x in report.findings
    )
    max_score = max([report.exposure_score, *[p.exposure_score for p in report.peers], 1])
    bars = [('You', report.exposure_score, True)] + [(p.label, p.exposure_score, False) for p in report.peers]
    if avg:
        bars.append(('Industry average', avg.get('exposureScore', 0), False))
    bench = ''.join(
        f'<div class="bar{" you" if you else ""}"><span class="lbl">{e(label)}</span>'
        f'<span class="track"><span class="fill" style="width:{max(2, round(100 * float(score) / max_score))}%"></span></span>'
        f'<span class="val">{e(str(score))}</span></div>'
        for label, score, you in bars
    )
    caveats = ''.join(f'<li>{e(c)}</li>' for c in report.caveats)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exposure audit: {e(report.company)}</title>
<style>
:root {{ --bg:#f7f7f5; --card:#fff; --ink:#1d1d1f; --muted:#6b6b70; --line:#e4e4e0; --bad:#c62828; --mid:#a66b00; --good:#2e7d32; --accent:#1a5fb4; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:920px; margin:0 auto; padding:32px 16px 64px; }}
.eyebrow {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.06em; margin:0; }}
h1 {{ font-size:30px; line-height:1.2; margin:6px 0 10px; }}
.headline {{ font-size:19px; margin:0 0 10px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:20px 0 8px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.kpi .v {{ font-size:28px; font-weight:700; }} .kpi .k {{ color:var(--muted); font-size:13px; }}
.v.bad {{ color:var(--bad); }} .v.mid {{ color:var(--mid); }} .v.good {{ color:var(--good); }}
h2 {{ font-size:20px; margin:32px 0 12px; }}
.fix {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:12px; }}
.fix h3 {{ font-size:17px; margin:0 0 6px; display:flex; gap:10px; align-items:baseline; }}
.n {{ background:var(--ink); color:#fff; border-radius:999px; font-size:12px; min-width:22px; height:22px; display:inline-flex; align-items:center; justify-content:center; }}
.why {{ color:#333; }}
.rel {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:0; }}
code {{ font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; background:#f0f0ec; border-radius:5px; padding:2px 6px; word-break:break-all; }}
ul.cats {{ list-style:none; padding:0; margin:0; background:var(--card); border:1px solid var(--line); border-radius:10px; }}
ul.cats li {{ display:flex; justify-content:space-between; padding:10px 14px; border-bottom:1px solid var(--line); }}
ul.cats li:last-child {{ border-bottom:0; }}
.bench {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:14px; }}
th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; font-size:13px; }}
.sev {{ font-weight:600; text-transform:capitalize; }} .sev.high {{ color:var(--bad); }} .sev.medium {{ color:var(--mid); }} .sev.low {{ color:var(--muted); }}
.bar {{ display:grid; grid-template-columns:130px 1fr 44px; gap:10px; align-items:center; margin:6px 0; font-size:14px; }}
.track {{ background:#efefeb; border-radius:6px; height:12px; overflow:hidden; }}
.fill {{ display:block; height:100%; background:#9aa0a6; }}
.bar.you .fill {{ background:var(--accent); }} .bar.you .lbl {{ font-weight:700; }}
.val {{ text-align:right; font-variant-numeric:tabular-nums; }}
footer {{ color:var(--muted); font-size:14px; margin-top:32px; }}
</style></head>
<body><main>
<p class="eyebrow">Bundle · exposure audit · {e(report.industry)}</p>
<h1>{e(report.company)} exposure audit</h1>
<p class="headline">{e(report.headline)}</p>
<p>{e(report.summary)}</p>
<div class="kpis">
<div class="kpi"><div class="v {tone}">{report.exposure_score}<small>/100</small></div><div class="k">Exposure score (lower is better)</div></div>
<div class="kpi"><div class="v">{e(report.rank.split(' (')[0] if report.rank else 'n/a')}</div><div class="k">Rank vs peers (1 is best)</div></div>
<div class="kpi"><div class="v">{e(_num(report.you.get('overexposedPerPage')))}</div><div class="k">Unused fields per page (industry {e(_num(avg.get('overexposedPerPage', 'n/a')))})</div></div>
<div class="kpi"><div class="v {'bad' if report.you.get('high') else 'good'}">{e(str(report.you.get('high')))}</div><div class="k">Personal data issues</div></div>
</div>
<h2>Top fixes</h2>
{fixes}
<h2>What we found</h2>
<div class="table-wrap"><table><thead><tr><th>Severity</th><th>Finding</th><th>Field or key</th><th>Fix</th></tr></thead><tbody>{found}</tbody></table></div>
{f'<h2>Benchmark: exposure score</h2><div class="bench">{bench}</div>' if report.peers else ''}
<h2>Caveats</h2><ul>{caveats}</ul>
<footer>Scanned {e(report.scanned_at or '')}. Public pages only, no login, no probing, no protections bypassed. Field values are never stored; peers are anonymous. Not legal advice.</footer>
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
