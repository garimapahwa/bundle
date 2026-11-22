"""The agent's tools. They are plain functions inside this Actor; the LLM decides which to call.

- fetchSite: load the target in a browser and capture its API responses, rendered pages,
  JavaScript, flag responses, window globals, and storage.
- auditExposure: compare API fields with what the pages show, and check the code for secrets,
  internal endpoints, and unreleased flags.
- findPeers: search Google for similar companies in the same industry.
- benchmarkPeers: run the same capture and audit on 3 to 5 peers, keeping only their counts.

Every tool logs "[agent] calling <tool> on <site>", so the reasoning shows up in the run log.
No tool ever returns a field value: findings hold field paths and kinds of data only.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from apify import Actor
from apify.storages import KeyValueStore
from langchain_core.tools import tool

from .audit import Audit, run_audit
from .collector import Capture, collect
from .extractor import registrable_domain

GOOGLE_SEARCH_ACTOR = 'apify/google-search-scraper'
PEER_LABELS = ['Peer A', 'Peer B', 'Peer C', 'Peer D', 'Peer E']
MAX_PEERS = 5
PEER_PAGES = 2


@dataclass
class RunState:
    """What the tools share during one run. main.py fills in the settings before the loop."""

    target_url: str = ''
    industry: str = ''
    max_pages: int = 3
    proxy_url: str | None = None
    use_cached_scan: bool = False
    capture: Capture | None = None
    capture_source: str = ''  # 'live' or 'cache'
    audit: Audit | None = None
    peers: list[dict] = field(default_factory=list)  # {label, url, stats, categories, piiCategories}
    peer_failures: int = 0
    peer_searches: int = 0
    anonymize_peers: bool = False
    benchmark_calls: int = 0
    tool_calls: list[str] = field(default_factory=list)

    @property
    def host(self) -> str:
        return host_name(self.target_url)


STATE = RunState()


def host_name(url: str) -> str:
    return (urlsplit(url if '//' in url else f'//{url}').hostname or '').removeprefix('www.')


def log_call(name: str, target: str, detail: str = '') -> None:
    """The line that makes the agent's choices visible in the run log."""
    STATE.tool_calls.append(name)
    Actor.log.info('[agent] calling %s on %s%s', name, target, f' ({detail})' if detail else '')


async def site_store(host: str) -> KeyValueStore:
    """A named key-value store per site, for example `bundle-groww-in`. It keeps the last capture."""
    slug = re.sub(r'[^a-z0-9-]+', '-', host.lower()).strip('-')[:55] or 'site'
    return await Actor.open_key_value_store(name=f'bundle-{slug}')


async def load_capture(host: str) -> Capture | None:
    """The capture saved by the last successful run for this site, if there is one."""
    payload = await (await site_store(host)).get_value('CAPTURE')
    if not payload:
        return None
    if isinstance(payload, str):
        payload = payload.encode('latin-1')
    data = json.loads(gzip.decompress(payload)) if isinstance(payload, bytes | bytearray) else payload
    return Capture.from_dict(data)


async def save_capture(host: str, capture: Capture) -> None:
    payload = gzip.compress(json.dumps(capture.to_dict(), ensure_ascii=False).encode('utf-8'))
    await (await site_store(host)).set_value('CAPTURE', payload, content_type='application/gzip')


def load_attempts() -> list[tuple[str, str | None]]:
    """How to load a site, cheapest first: full Chromium direct, then via Apify Proxy, then Firefox.

    Most sites load directly. Residential proxy traffic is the biggest cost of a run, so it is
    used only when a site refuses the direct connection.
    """
    attempts: list[tuple[str, str | None]] = [('chromium', None)]
    if STATE.proxy_url:
        attempts.append(('chromium', STATE.proxy_url))
    attempts.append(('firefox', STATE.proxy_url))
    return attempts


async def capture_site(url: str, max_pages: int) -> tuple[Capture | None, str]:
    """Load a site live (and save it), or from the saved copy. Returns the capture and its source."""
    host = host_name(url)
    if STATE.use_cached_scan:
        cached = await load_capture(host)
        if cached:
            return cached, 'cache'
    capture = None
    for attempt, (browser_kind, proxy_url) in enumerate(load_attempts()):
        label = f'{browser_kind}{" via Apify Proxy" if proxy_url else ""}'
        if attempt:
            Actor.log.info('[agent] %s did not load yet; retrying with %s', host, label)
        try:
            capture = await collect(url, max_pages=max_pages, proxy_url=proxy_url, browser_kind=browser_kind)
        except Exception as exc:  # noqa: BLE001 - try the next option, then the saved copy
            Actor.log.warning('Could not load %s with %s: %s', host, label, str(exc).splitlines()[0][:160])
            capture = None
        if capture and (capture.scripts or capture.api_responses):
            Actor.log.info('[agent] loaded %s with %s', host, label)
            break
    if capture is None:
        cached = await load_capture(host)
        return (cached, 'cache') if cached else (None, '')
    if not capture.scripts and not capture.api_responses:
        Actor.log.warning('%s loaded no first-party code (probably a bot check). Bundle does not bypass protections.', host)
        cached = await load_capture(host)
        return (cached, 'cache') if cached else (None, '')
    capture.captured_at = datetime.now(UTC).isoformat(timespec='seconds')
    await save_capture(host, capture)
    return capture, 'live'


@tool('fetchSite')
async def fetch_site(url: str) -> dict | str:
    """Load the target website in a real browser (public pages only) and capture what it sends.

    Captures every first-party API (XHR/fetch) JSON response, the text and attributes each page
    renders, all first-party JavaScript, feature-flag responses, window globals, and storage.
    Call it once, first.

    Args:
        url: The target website, for example https://groww.in.

    Returns:
        What was captured: pages, API responses, JavaScript files, and flag services.
    """
    if STATE.capture is not None:
        return {'already_fetched': True, 'note': 'The target is already captured. Call auditExposure next.'}
    log_call('fetchSite', STATE.host, f'up to {STATE.max_pages} pages' + (', saved copy if any' if STATE.use_cached_scan else ''))
    await Actor.set_status_message(f'fetchSite: loading {STATE.target_url} in a browser')
    capture, source = await capture_site(STATE.target_url, STATE.max_pages)
    if capture is None:
        return 'fetchSite could not load the site (it may show a bot check; Bundle does not bypass protections). Stop and report that.'
    STATE.capture, STATE.capture_source = capture, source
    await Actor.set_status_message(f'fetchSite: {len(capture.api_responses)} API responses and {len(capture.scripts)} JS files from {STATE.host}')
    return {
        'site': capture.site_domain,
        'source': source,
        'captured_at': capture.captured_at,
        'pages_visited': capture.visited,
        'api_responses': len(capture.api_responses),
        'js_files': len(capture.scripts),
        'flag_service_responses': len(capture.flag_configs),
    }


@tool('auditExposure')
async def audit_exposure() -> dict | str:
    """Audit the captured target for business exposure. Call it after fetchSite.

    Compares every API field with what the pages render, and flags fields the UI never shows
    (personal data such as PAN, Aadhaar, phone, email, date of birth, account numbers, internal
    IDs, and risk scores is high severity). Also flags secrets and keys in the JavaScript,
    internal/admin/staging endpoints and hosts, public source maps, and unreleased feature flags.

    Returns:
        Counts, the exposure score, and the findings (field paths and kinds only, never values).
    """
    if STATE.capture is None:
        return 'Nothing is captured yet. Call fetchSite first.'
    log_call('auditExposure', STATE.host, f'{len(STATE.capture.api_responses)} API responses, {len(STATE.capture.scripts)} JS files')
    await Actor.set_status_message('auditExposure: comparing API fields with what the pages show')
    if STATE.audit is None:
        STATE.audit = run_audit(STATE.capture)
    audit = STATE.audit
    await Actor.set_status_message(f'auditExposure: score {audit.stats["exposureScore"]}, {audit.stats["high"]} high-severity findings')
    by_category = Counter(r['category'] for r in audit.rows)
    return {
        'stats': audit.stats,
        'by_category': dict(by_category),
        'findings': [
            {
                'finding': r['finding'],
                'category': r['category'],
                'severity': r['severity'],
                'field_or_key': r['field_or_key'],
                'personal_data': r.get('pii') or None,
                'evidence': r['evidence_url'][:120],
                'guidance': r['fix'][:200],
            }
            for r in audit.rows[:40]
        ],
    }


@tool('findPeers')
async def find_peers(query: str) -> list[dict] | str:
    """Search Google for companies similar to the target, to benchmark against.

    Use a query such as "top online stock broking platforms India" or "<industry> companies like
    <company>". Then pick 3 to 5 company homepages from the results: real competitors in the same
    industry, not news sites, directories, app stores, or the target itself.

    Args:
        query: The Google search.

    Returns:
        Results with title, url, and snippet.
    """
    if STATE.peer_searches >= 2:
        return 'The peer search budget is used up. Pick peers from the results you have.'
    STATE.peer_searches += 1
    log_call('findPeers', STATE.host, f'"{query}" via {GOOGLE_SEARCH_ACTOR}')
    await Actor.set_status_message(f'findPeers: searching "{query}"')
    try:
        run = await Actor.apify_client.actor(GOOGLE_SEARCH_ACTOR).call(
            run_input={'queries': query, 'maxPagesPerQuery': 1, 'mobileResults': False, 'saveHtml': False}, timeout_secs=180
        )
        if not run or run.get('status') != 'SUCCEEDED':
            msg = f'the search finished with status {(run or {}).get("status")}'
            raise RuntimeError(msg)
        items = (await Actor.apify_client.dataset(run['defaultDatasetId']).list_items()).items
    except Exception as exc:  # noqa: BLE001 - report the failure to the agent so it can react
        Actor.log.warning('findPeers failed: %s', exc)
        return f'The search failed: {exc}. Benchmark without peers and say so in the caveats.'
    return [
        {'title': r.get('title') or '', 'url': r.get('url') or '', 'snippet': (r.get('description') or '')[:160]}
        for item in items
        for r in item.get('organicResults') or []
        if r.get('url')
    ][:10]


@tool('benchmarkPeers')
async def benchmark_peers(urls: list[str]) -> dict | str:
    """Run the same capture and audit on 3 to 5 peer websites, and compare.

    Public pages only, no login, no probing. Only counts are kept for peers (never their field
    names or values). Peers are named by their site, or Peer A to Peer E when anonymized. Call it once.

    Args:
        urls: 3 to 5 peer homepages, for example ["https://zerodha.com", "https://upstox.com"].

    Returns:
        Each peer's counts and score, the industry average, and the target's rank.
    """
    if STATE.audit is None:
        return 'Audit the target first: call fetchSite, then auditExposure.'
    if STATE.benchmark_calls >= 1:
        return 'Peers are already benchmarked. Write the report now.'
    STATE.benchmark_calls += 1
    own = registrable_domain(STATE.host)
    picked, seen = [], {own}
    for url in urls:
        url = url if url.startswith('http') else f'https://{url}'
        domain = registrable_domain(host_name(url))
        if domain and domain not in seen:
            seen.add(domain)
            picked.append(f'https://{host_name(url)}')
    picked = picked[:MAX_PEERS]
    log_call('benchmarkPeers', STATE.host, f'{len(picked)} peers, {PEER_PAGES} pages each')

    for number, url in enumerate(picked):
        label = PEER_LABELS[len(STATE.peers)] if STATE.anonymize_peers else host_name(url)
        Actor.log.info('[agent] benchmarkPeers: scanning %s as %s', host_name(url), label)
        await Actor.set_status_message(f'benchmarkPeers: scanning peer {number + 1} of {len(picked)}')
        capture, _source = await capture_site(url, PEER_PAGES)
        if capture is None:
            STATE.peer_failures += 1
            continue
        audit = run_audit(capture)
        STATE.peers.append(
            {
                'label': label,
                'url': url,
                'stats': audit.stats,
                'categories': {r['category'] for r in audit.rows},
                'piiCategories': {r['pii'] for r in audit.rows if r.get('pii')},
            }
        )
    return benchmark_summary()


def benchmark_summary() -> dict:
    """Peer counts (never their field details), the industry average, and the target's rank (1 = least exposed)."""
    you = STATE.audit.stats if STATE.audit else {}
    peers = [{'label': p['label'], **{k: p['stats'][k] for k in ('exposureScore', 'overexposedPerPage', 'high', 'apiResponses')}} for p in STATE.peers]
    if not peers:
        return {'peers': [], 'note': f'No peer could be scanned ({STATE.peer_failures} failed).'}
    scores = sorted([you.get('exposureScore', 0)] + [p['exposureScore'] for p in peers])
    return {
        'you': {k: you.get(k) for k in ('exposureScore', 'overexposedPerPage', 'high', 'apiResponses')},
        'peers': peers,
        'industry_average': {
            'exposureScore': round(sum(p['exposureScore'] for p in peers) / len(peers), 1),
            'overexposedPerPage': round(sum(p['overexposedPerPage'] for p in peers) / len(peers), 1),
        },
        'rank': f'{scores.index(you.get("exposureScore", 0)) + 1} of {len(scores)} (1 = least exposed)',
        'peers_failed': STATE.peer_failures,
    }


TOOLS = [fetch_site, audit_exposure, find_peers, benchmark_peers]
