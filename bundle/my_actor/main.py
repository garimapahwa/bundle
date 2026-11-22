"""Bundle: a business exposure audit for your web app, benchmarked against your industry.

Input: your website and your industry (and, optionally, peer websites).
Output: every finding as a dataset row, and a REPORT with an exposure score, your rank against
peers, and the top 5 fixes with why each matters (including the DPDP Act, 2023).

How it works:
- The agent loop runs inside this Actor, and decides which tools to call and in what order.
- Its tools (see `tools.py`): fetchSite, auditExposure, findPeers, and benchmarkPeers.
- Pay per event: one `question-answered` event per finished audit.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from html import escape
from urllib.parse import urlsplit

from apify import Actor, Event
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .audit import benchmark_text, group_rows, run_audit
from .models import AuditDraft, AuditReport, FindingRow, PeerStat
from .tools import STATE, TOOLS, benchmark_summary
from .utils import log_new_messages, report_to_html, report_to_markdown

DEFAULT_PROXY = {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL']}

SYSTEM_PROMPT = """You are Bundle, a business exposure auditor. A company gives you its website and \
industry. You find what its public web app gives away, compare it with industry peers, and tell \
the founder or CISO what to fix first.

You have four tools. Decide which to call and in what order; this order works well:
1. fetchSite once, with the target website.
2. auditExposure once.
3. {peer_step}
4. benchmarkPeers once, with 3 to 5 peer homepages.
5. Write the report.

Rules:
- Use only what the tools returned. Never invent a finding, a number, or a peer.
- Never name a peer in the report: they are Peer A to Peer E. Never repeat a field value.
- top_fixes: up to 5, most important first (high-severity personal data first, then secrets, \
then internal endpoints, then overexposed fields, then unreleased flags). Each "related" list \
holds field_or_key values copied exactly from auditExposure.
- Match the fix to the severity and the "guidance" field of each finding. A low-severity key \
(for example a Google or Firebase browser key, or a Stripe publishable key) is public by design: \
advise restricting it by domain and API, never "rotate immediately" and never call it a leaked \
secret. Only medium or high secret findings may be called exposed secrets.
- why_it_matters: the business risk in plain words. Mention the Digital Personal Data Protection \
Act, 2023 (India) ONLY for findings whose "personal_data" field is set. Then explain the duty to \
take reasonable security safeguards against personal data breaches, to collect and share only \
what a purpose needs, and that penalties can reach INR 250 crore for failing to safeguard data. \
If no finding has personal data, do not mention the DPDP Act at all. Write "may", not legal \
certainty; this is not legal advice.
- related: copy field_or_key values exactly, including masked ones such as "AIza******** (39 chars, masked)".
- headline: one sentence with the biggest exposure and the rank against peers if you have one."""

PEER_STEP_FIND = (
    'findPeers with a query such as "<industry> companies in India like <company>", then pick 3 to 5 '
    'real competitor homepages from the results (not news, directories, app stores, or the target).'
)
PEER_STEP_GIVEN = 'The user gave these peers; use them as they are: {peers}. Do not call findPeers.'


def normalize_url(raw: str) -> str:
    """Accept `groww.in`, `www.groww.in`, or a full URL."""
    url = raw.strip()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    host = urlsplit(url).hostname
    if not host or '.' not in host:
        msg = f'"{raw}" is not a valid website URL'
        raise ValueError(msg)
    return url


async def proxy_url_from(proxy_input: dict | None) -> str | None:
    """Apify Proxy for the browser (RESIDENTIAL by default). Without access, run without a proxy."""
    if not proxy_input or not proxy_input.get('useApifyProxy'):
        return None
    try:
        proxy_configuration = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)
        return await proxy_configuration.new_url() if proxy_configuration else None
    except Exception as exc:  # noqa: BLE001 - a missing proxy group must not stop the run
        Actor.log.warning('Apify Proxy is not available (%s). Loading sites without a proxy.', exc)
        return None


def make_llm(model_name: str, llm_api_key: str | None) -> ChatOpenAI:
    """Your own OpenRouter key if you give one, else the Apify OpenRouter proxy (no key needed)."""
    common = {'model': model_name, 'temperature': 0.2, 'max_tokens': 5000, 'timeout': 180}
    if llm_api_key:
        return ChatOpenAI(base_url='https://openrouter.ai/api/v1', api_key=llm_api_key, **common)
    # The proxy only accepts the token of the run itself, so tokens are billed to whoever runs it.
    return ChatOpenAI(base_url='https://openrouter.apify.actor/api/v1', api_key=os.environ['APIFY_TOKEN'], **common)


async def save_blocked_report(target_url: str) -> None:
    """When a site cannot be loaded, still leave a report that says so, so Output is never empty."""
    tried = 'full Chromium via Apify Proxy, full Chromium without a proxy, and Firefox' if STATE.proxy_url else 'full Chromium and Firefox'
    message = (
        f'Bundle could not load {target_url}. It tried {tried}, and the site refused all of them. '
        'Bundle does not solve CAPTCHAs or bypass bot protection, so there is nothing to audit. '
        'Try another public page on the same site, or run it again later.'
    )
    store = await Actor.open_key_value_store()
    await store.set_value('REPORT', {'target': target_url, 'status': 'blocked', 'message': message})
    await store.set_value('report.md', f'# Could not audit {target_url}\n\n{message}\n', content_type='text/markdown')
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Bundle: site blocked</title><style>body{margin:0;background:#f7f7f5;color:#1d1d1f;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}'
        'main{max-width:720px;margin:0 auto;padding:48px 16px}h1{font-size:26px}</style></head>'
        f'<body><main><h1>Could not audit this site</h1><p>{escape(message)}</p></main></body></html>'
    )
    await store.set_value('report.html', page, content_type='text/html')


async def main() -> None:
    """Audit one website, benchmark it against peers, and store the findings and the report."""
    async with Actor:

        async def on_aborting(_event_data: object = None) -> None:
            await Actor.set_status_message('Aborted by the user or a limit')
            await Actor.exit()

        Actor.on(Event.ABORTING, on_aborting)

        # 1. Input
        actor_input = await Actor.get_input() or {}
        try:
            target_url = normalize_url(actor_input.get('targetUrl') or '')
            peer_urls = [normalize_url(u) for u in actor_input.get('peerUrls') or [] if str(u).strip()][:5]
        except ValueError as exc:
            await Actor.fail(status_message=f'Invalid input: {exc}. Give websites such as https://groww.in')
            return
        industry = (actor_input.get('industry') or '').strip() or 'the same industry'
        model_name = actor_input.get('modelName') or 'deepseek/deepseek-v4.1-flash'
        if actor_input.get('debug', False):
            Actor.log.setLevel(logging.DEBUG)

        STATE.target_url = target_url
        STATE.industry = industry
        STATE.max_pages = max(1, min(int(actor_input.get('maxPages') or 3), 10))
        STATE.use_cached_scan = bool(actor_input.get('useCachedScan', False))
        STATE.proxy_url = await proxy_url_from(actor_input.get('proxyConfiguration', DEFAULT_PROXY))
        Actor.log.info('Target %s, industry %s, %d peers given, model %s', target_url, industry, len(peer_urls), model_name)
        await Actor.set_status_message(f'Starting the exposure audit of {target_url}')

        # 2. The agent: an LLM in a loop that picks its own tools, with a fixed output shape
        llm = make_llm(model_name, (actor_input.get('llmApiKey') or '').strip() or None)
        peer_step = PEER_STEP_GIVEN.format(peers=', '.join(peer_urls)) if peer_urls else PEER_STEP_FIND
        graph = create_agent(llm, TOOLS, system_prompt=SYSTEM_PROMPT.format(peer_step=peer_step), response_format=AuditDraft)

        # 3. Run the loop. The recursion limit caps how many steps it may take, which caps the cost.
        inputs: dict = {'messages': [('user', f'Target: {target_url}\nIndustry: {industry}')]}
        draft: AuditDraft | None = None
        logged = 0
        try:
            async for state in graph.astream(inputs, {'recursion_limit': 20}, stream_mode='values'):
                logged = log_new_messages(state['messages'], logged)
                if state.get('structured_response') is not None:
                    draft = state['structured_response']
                    break
        except Exception as exc:  # noqa: BLE001 - a failed run must say why, and must not charge
            Actor.log.exception('The agent stopped before it finished the audit')
            reason = f'The agent could not finish ({type(exc).__name__}). Run it again with useCachedScan on, or try another model.'
            await Actor.fail(status_message=reason)
            return

        if STATE.capture is None:
            await save_blocked_report(target_url)
            await Actor.fail(status_message=f'Could not load {target_url} with Chromium or Firefox. The site blocks automated browsers; see report.html.')
            return
        if not draft:
            await Actor.fail(status_message='The agent did not return a report. Run it again, or try another model.')
            return
        if STATE.audit is None:  # the agent skipped the audit; the report still needs the facts
            STATE.audit = run_audit(STATE.capture)

        # 4. Rows: personal data one per field; unused fields one row per API; flags one row
        await Actor.set_status_message('Writing the findings and the report')
        audit = STATE.audit
        rows = []
        for row in group_rows(audit.rows):
            row = {**row, 'peer_benchmark': benchmark_text(row, audit.stats, STATE.peers)}
            rows.append(FindingRow(**{k: row[k] for k in FindingRow.model_fields}).model_dump())

        # 5. The report: numbers from the code, words from the agent. Fixes must point at real findings.
        known = {r['field_or_key'] for r in audit.rows}
        fixes = []
        for fix in draft.top_fixes[:5]:
            fix.related = [r for r in fix.related if r in known]
            fixes.append(fix)
        summary = benchmark_summary()
        caveats = list(draft.caveats)
        if STATE.peer_failures:
            caveats.append(f'{STATE.peer_failures} peer site(s) could not be scanned (bot checks are never bypassed).')
        if STATE.capture_source == 'cache':
            caveats.append(f'This audit uses a saved capture of the target from {STATE.capture.captured_at}.')

        store = await Actor.open_key_value_store()
        report = AuditReport(
            target=target_url,
            company=draft.company or STATE.capture.site_domain.split('.')[0].capitalize(),
            industry=industry,
            headline=draft.headline,
            summary=draft.summary,
            exposure_score=audit.stats['exposureScore'],
            rank=summary.get('rank'),
            you=summary.get('you') or {k: audit.stats[k] for k in ('exposureScore', 'overexposedPerPage', 'high', 'apiResponses')},
            industry_average=summary.get('industry_average'),
            peers=[
                PeerStat(label=p['label'], exposure_score=p['stats']['exposureScore'], overexposed_per_page=p['stats']['overexposedPerPage'], high_severity=p['stats']['high'])
                for p in STATE.peers
            ],
            top_fixes=fixes,
            findings_by_category=dict(Counter(r['category'] for r in audit.rows)),
            findings=[{k: r[k] for k in ('severity', 'finding', 'category', 'field_or_key', 'evidence_url', 'peer_benchmark', 'fix')} for r in rows[:60]],
            stats={**audit.stats, 'toolCalls': STATE.tool_calls, 'captureSource': STATE.capture_source, 'model': model_name},
            caveats=caveats,
            scanned_at=STATE.capture.captured_at,
            report_url=f'https://api.apify.com/v2/key-value-stores/{store.id}/records/report.html',
        )

        await store.set_value('REPORT', report.model_dump())
        await store.set_value('report.md', report_to_markdown(report), content_type='text/markdown')
        await store.set_value('report.html', report_to_html(report), content_type='text/html')
        if rows:
            await Actor.push_data(rows)
        Actor.log.info('Pushed %d findings, saved REPORT, report.md, and report.html: %s', len(rows), report.report_url)

        # Pay per event: one finished audit
        await Actor.charge(event_name='question-answered')
        await Actor.set_status_message(
            f'Done: exposure score {report.exposure_score}/100, rank {report.rank or "n/a"}, {audit.stats["high"]} high-severity findings'[:400]
        )
