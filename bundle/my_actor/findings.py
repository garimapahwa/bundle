"""Turn a capture into findings: scored signals, exposures, and stats.

auditExposure runs this for the JavaScript side of the audit (secrets, internal hosts and
endpoints, feature flags). The extraction rules live in `extractor.py` (pure, with a CLI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .collector import Capture
from .extractor import EXPOSURE_FIXES, _signal, classify_route, extract_exposures, extract_flag_config, extract_signals, is_platform_file, merge_signals

MIN_SCORE = 25  # below this a signal is almost always noise
LOCALE_IN_PATH = re.compile(r'/(?:locales?|i18n|translations?|lang|messages|intl)/([a-z]{2}(?:[-_][A-Za-z]{2})?)(?:/|\.json)', re.IGNORECASE)


@dataclass
class Findings:
    """Everything found in the JavaScript of one capture."""

    signals: list[dict] = field(default_factory=list)  # sorted by score
    exposures: list[dict] = field(default_factory=list)  # high severity first
    stats: dict = field(default_factory=dict)


def short_name(url: str) -> str:
    """The file name of a script URL, for compact context."""
    return urlsplit(url).path.rsplit('/', 1)[-1] or url[:80]


def extract_findings(capture: Capture) -> Findings:
    """Run every extractor over every captured source, then score, deduplicate, and rank."""
    site = capture.site_domain
    signals: list[dict] = []
    exposures: dict[tuple[str, str], dict] = {}

    def add_exposures(items: list[dict], source_url: str) -> None:
        for item in items:
            if item['type'] == 'source_map':
                continue  # only verified, downloadable maps are reported (below)
            key = (item['type'], item['value'])
            if key in exposures:
                exposures[key]['occurrences'] += item['occurrences']
            else:
                exposures[key] = {**item, 'sourceUrl': source_url}

    # 1. JavaScript files (library chunks only for exposures) and inline scripts
    for url, text in capture.scripts.items():
        if url not in capture.library_scripts:
            signals += [{**s, 'sourceUrl': url} for s in extract_signals(text, short_name(url), site)]
        if not is_platform_file(url):  # the platform's own code is not the site's exposure
            add_exposures(extract_exposures(text, short_name(url), site), url)
    for map_url, text in capture.source_map_files.items():
        signals += [{**s, 'sourceUrl': map_url} for s in extract_signals(text, f'sourcemap:{short_name(map_url)}', site)]
    for label, text in capture.inline_scripts.items():
        signals += [{**s, 'sourceUrl': capture.final_url} for s in extract_signals(text, label, site)]
        add_exposures(extract_exposures(text, label, site), capture.final_url)

    # 2. Live flag-service responses, window globals, and web storage (flag caches live here)
    sources = [(urlsplit(u).netloc + urlsplit(u).path, u, t) for u, t in capture.flag_configs.items()]
    sources += [(f'window.{name}', capture.final_url, t) for name, t in capture.window_globals.items()]
    sources += [(f'storage:{key}', capture.final_url, t) for key, t in capture.storage.items()]
    for name, url, text in sources:
        signals += [{**s, 'sourceUrl': url} for s in extract_flag_config(text, name) + extract_signals(text, name, site)]
        add_exposures(extract_exposures(text, name, site), url)

    # 3. i18n files: teaser copy, and the locales the app is translated into
    locales: set[str] = set()
    for url, text in capture.i18n_files.items():
        match = LOCALE_IN_PATH.search(url)
        if match:
            locales.add(match.group(1).replace('_', '-'))
        signals += [{**s, 'sourceUrl': url} for s in extract_signals(text, short_name(url), site) if s['type'] in {'ui_copy', 'plan_or_pricing', 'locale'}]
    signals += [_signal('locale', loc, 'translation file loaded by the app', 'i18n', 35) for loc in sorted(locales)]

    # 4. Next.js routes from the build manifest. A route nobody links to is a stronger clue.
    for route in capture.next_routes:
        signal = classify_route(route, '_buildManifest', 'Next.js build manifest: a route this app can render')
        if not signal or signal['type'] != 'hidden_route':
            continue
        linked = route.rstrip('/') in capture.link_paths or route == '/'
        signal['score'] += -20 if linked else 10
        signals.append({**signal, 'sourceUrl': capture.final_url})

    # 5. Source maps that are really downloadable
    for map_url, script_url in capture.exposed_source_maps.items():
        exposures[('source_map', map_url)] = {
            'type': 'source_map',
            'value': map_url,
            'context': f'Downloadable source map for {short_name(script_url)}',
            'source': short_name(script_url),
            'sourceUrl': script_url,
            'severity': 'medium',
            'occurrences': 1,
            'fix': EXPOSURE_FIXES['source_map'],
        }

    merged = [s for s in merge_signals(signals) if s['score'] >= MIN_SCORE]
    order = {'high': 0, 'medium': 1, 'low': 2}
    exposure_list = sorted(exposures.values(), key=lambda e: (order.get(e['severity'], 3), e['type'], e['value']))
    stats = {
        'pagesVisited': len(capture.visited),
        'jsFilesScanned': len(capture.scripts) - len(capture.library_scripts),
        'libraryFilesSkipped': len(capture.library_scripts),
        'thirdPartyScriptsDropped': sum(capture.third_party_hosts.values()),
        'flagConfigResponses': len(capture.flag_configs),
        'windowGlobals': len(capture.window_globals),
        'storageKeys': len(capture.storage),
        'i18nFiles': len(capture.i18n_files),
        'nextjsRoutes': len(capture.next_routes),
        'lazyChunksFetched': capture.lazy_chunks_fetched,
        'megabytesScanned': round(capture.bytes_total / 1_000_000, 1),
        'signals': len(merged),
        'exposures': len(exposure_list),
        'signalsByType': {t: sum(1 for s in merged if s['type'] == t) for t in sorted({s['type'] for s in merged})},
    }
    return Findings(signals=merged, exposures=exposure_list, stats=stats)
