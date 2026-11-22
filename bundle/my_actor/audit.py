"""The exposure audit of one site, and the score used to rank it against its peers.

One audit combines:
- overexposed fields: API data the pages never show (exposure.py), PII marked high severity
- secrets and keys in the bundles, internal and staging hosts, public source maps (extractor.py)
- internal, admin, and staging endpoints referenced in the code
- unreleased feature flags (switched off in the live flag config)

The same audit runs on the target and on every peer, so the numbers compare like with like.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .collector import Capture
from .exposure import overexposed_fields
from .findings import extract_findings

INTERNAL_ENDPOINT = re.compile(
    r'(?:^|[/._-])(?:admin|internal|staging|stage|stg|uat|qa|dev|debug|backoffice|back-office|ops|private|sandbox|superuser|impersonate)(?:[/._-]|$)',
    re.IGNORECASE,
)
FLAG_OFF_STATES = {'false', 'off', '0', 'null', '{}'}
SEVERITY_POINTS = {'high': 15, 'medium': 5, 'low': 1}

FIXES = {
    'pii_exposure': 'Remove it from the API response, or send it masked and only to its owner.',
    'overexposed_field': 'Send only the fields the page shows.',
    'secret': 'Rotate it and move it to the server.',
    'internal_endpoint': 'Remove it from client code; keep it behind login or VPN.',
    'internal_host': 'Remove internal hostnames from production code.',
    'unreleased_flag': 'Evaluate flags on the server; send only the result.',
    'source_map': 'Stop serving .map files in production.',
}
SHORT_NOTES = {
    'google_api_key': 'Public by design. Restrict it to your domains and APIs.',
    'stripe_publishable_key': 'Public by design. No action needed.',
    'public_client_key': 'Meant to be public. Check its permissions; no rotation needed.',
}


@dataclass
class Audit:
    """The findings and stats of one site. Rows never contain a field value."""

    rows: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def has(self, category: str) -> bool:
        return any(r['category'] == category for r in self.rows)


def exposure_score(rows: list[dict]) -> int:
    """0 (nothing exposed) to 100. High findings weigh 15, medium 5, low 1 (low capped at 20)."""
    high = sum(1 for r in rows if r['severity'] == 'high')
    medium = sum(1 for r in rows if r['severity'] == 'medium')
    low = min(20, sum(1 for r in rows if r['severity'] == 'low'))
    return min(100, SEVERITY_POINTS['high'] * high + SEVERITY_POINTS['medium'] * medium + low)


def run_audit(capture: Capture) -> Audit:
    """Audit one captured site."""
    rows: list[dict] = []

    # 1. Overexposed API fields (the core check)
    fields, field_stats = overexposed_fields(capture.api_responses, capture.dom_text)
    for f in fields:
        if f['pii']:
            finding = f'{f["piiLabel"].capitalize()} sent but not shown'
            category = 'pii_exposure'
        else:
            finding = 'Unused API field'
            category = 'overexposed_field'
        rows.append(_row(finding, category, f['severity'], f['field'], f'https://{f["endpoint"]}', pii=f['pii']))

    # 2. What the bundles give away
    findings = extract_findings(capture)
    for e in findings.exposures:
        if e['type'] == 'secret_like':
            kind = e.get('secret_kind', 'secret').replace('_', ' ')
            label = 'Browser API key in JavaScript' if e['severity'] == 'low' else f'Secret in JavaScript ({kind})'
            fix = SHORT_NOTES.get(e.get('secret_kind', ''), FIXES['secret'])
            if e.get('secret_kind') == 'public_client_key':
                label = 'Public client key in JavaScript'
            rows.append(_row(label, 'secret', e['severity'], e['value'], e.get('sourceUrl', ''), fix=fix))
        elif e['type'] == 'internal_host':
            rows.append(_row('Internal hostname in JavaScript', 'internal_host', 'medium', e['value'], e.get('sourceUrl', '')))
        elif e['type'] == 'source_map':
            rows.append(_row('Public source map (your source code)', 'source_map', 'medium', e['value'], e['value']))

    internal = [s for s in findings.signals if s['type'] == 'api_endpoint' and INTERNAL_ENDPOINT.search(s['value'])]
    for s in internal[:20]:
        rows.append(_row('Internal endpoint in JavaScript', 'internal_endpoint', 'medium', s['value'], s.get('sourceUrl', '')))

    off_flags = [
        s for s in findings.signals
        if s['type'] == 'feature_flag' and str(s.get('liveState', '')).strip('"').lower() in FLAG_OFF_STATES
    ]
    for s in off_flags[:25]:
        rows.append(_row('Unreleased feature flag', 'unreleased_flag', 'low', s['value'], s.get('sourceUrl', '')))

    pages = max(1, len(capture.visited))
    stats = {
        'pagesVisited': len(capture.visited),
        **field_stats,
        'overexposedPerPage': round(field_stats['overexposedFields'] / pages, 1),
        'secrets': sum(1 for r in rows if r['category'] == 'secret'),
        'internalEndpoints': sum(1 for r in rows if r['category'] in ('internal_endpoint', 'internal_host')),
        'unreleasedFlags': sum(1 for r in rows if r['category'] == 'unreleased_flag'),
        'jsFilesScanned': findings.stats.get('jsFilesScanned', 0),
        'high': sum(1 for r in rows if r['severity'] == 'high'),
        'medium': sum(1 for r in rows if r['severity'] == 'medium'),
        'low': sum(1 for r in rows if r['severity'] == 'low'),
    }
    stats['exposureScore'] = exposure_score(rows)
    order = {'high': 0, 'medium': 1, 'low': 2}
    rows.sort(key=lambda r: (order[r['severity']], r['category'], r['field_or_key']))
    return Audit(rows=rows, stats=stats)


def _row(finding: str, category: str, severity: str, field_or_key: str, evidence_url: str, fix: str | None = None, pii: str | None = None) -> dict:
    return {
        'finding': finding,
        'category': category,
        'severity': severity,
        'field_or_key': field_or_key,
        'evidence_url': evidence_url.split('?')[0],
        'peer_benchmark': '',
        'fix': fix or FIXES[category],
        'pii': pii,
    }


def benchmark_text(row: dict, you: dict, peers: list[dict]) -> str:
    """A short comparison with the peers for this kind of finding (counts only)."""
    if not peers:
        return 'No peers compared'
    n = len(peers)
    if row['category'] in ('pii_exposure', 'overexposed_field'):
        average = sum(p['stats']['overexposedPerPage'] for p in peers) / n
        text = f'You {you["overexposedPerPage"]} vs industry {average:.1f} unused fields per page'
        if row.get('pii'):
            same = sum(1 for p in peers if row['pii'] in p['piiCategories'])
            text += f'; {same} of {n} peers send {row["pii"].replace("_", " ")} too'
        return text
    key = {'secret': 'secrets', 'internal_endpoint': 'internalEndpoints', 'internal_host': 'internalEndpoints', 'unreleased_flag': 'unreleasedFlags'}.get(row['category'])
    count = sum(1 for p in peers if (p['stats'].get(key) if key else row['category'] in p['categories']))
    return f'{count} of {n} peers too'


def group_rows(rows: list[dict]) -> list[dict]:
    """One row per API for unused fields, and one row for all unreleased flags. Everything else stays."""
    grouped: list[dict] = []
    unused: dict[str, list[dict]] = {}
    flags: list[dict] = []
    for row in rows:
        if row['category'] == 'overexposed_field':
            unused.setdefault(row['evidence_url'], []).append(row)
        elif row['category'] == 'unreleased_flag':
            flags.append(row)
        else:
            grouped.append(row)
    for url, items in unused.items():
        names = list(dict.fromkeys(_leaf(r['field_or_key']) for r in items))
        api = '/'.join([p for p in urlsplit(url).path.split('/') if p][-2:]) or urlsplit(url).netloc
        noun = 'field' if len(items) == 1 else 'fields'
        grouped.append({**items[0], 'finding': f'{len(items)} unused {noun} in {api} API', 'field_or_key': _examples(names)})
    if flags:
        grouped.append({**flags[0], 'finding': f'{len(flags)} unreleased feature flag{"s" if len(flags) > 1 else ""}', 'field_or_key': _examples([r['field_or_key'] for r in flags])})
    order = {'high': 0, 'medium': 1, 'low': 2}
    return sorted(grouped, key=lambda r: (order[r['severity']], r['category']))


def _leaf(path: str) -> str:
    """The last part of a field path: result.items[].inventory_id -> inventory_id."""
    parts = [p for p in re.split(r'[.\[\]{}]+', path) if p]
    return parts[-1] if parts else path


def _examples(names: list[str], limit: int = 4) -> str:
    shown = ', '.join(names[:limit])
    return f'{shown}, +{len(names) - limit} more' if len(names) > limit else shown
