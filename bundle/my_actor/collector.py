"""Load a web app in a real browser and capture the JavaScript it ships.

What it collects, from public pages only (no login, no form submission):
- every first-party JavaScript file the pages load (third-party scripts are only counted)
- inline <script> blocks, including Next.js __NEXT_DATA__
- JSON responses from feature-flag and remote-config services, and i18n translation files
- non-standard window globals (app state, flag caches) and localStorage/sessionStorage
- Next.js: the build manifest (every app route) and the chunks not loaded yet
- Other bundlers: lazy chunks found in the webpack chunk map or as chunk file names (best effort)
- which source maps referenced by the bundles are really downloadable

Nothing here raises on a missing pattern: a site that is not Next.js or has no flags just
yields fewer captures.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from apify import Actor
from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

from .extractor import SOURCE_MAP_COMMENT, host_of, is_library_file, is_third_party_script, registrable_domain, same_org

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)

# Limits that keep a scan fast and cheap, whatever the site does.
MAX_FILE_BYTES = 6_000_000
MAX_TOTAL_BYTES = 120_000_000
MAX_SCRIPTS = 500
MAX_EXTRA_CHUNKS = 250
MAX_FLAG_RESPONSES = 30
MAX_SOURCE_MAP_CHECKS = 12
MAX_SOURCE_MAPS_READ = 3
FETCH_CONCURRENCY = 8

# Flag vendors, recognized on any host
FLAG_VENDOR_HINTS = (
    'growthbook', 'launchdarkly', 'statsig', 'featuregates', 'optimizely', 'posthog', 'flagsmith',
    'firebaseremoteconfig', 'split.io', 'unleash', 'configcat', 'featurehub', 'devcycle', 'hypertune',
)
# Flag and config paths, recognized only on the site's own domain
FLAG_PATH_HINTS = (
    '/features', '/flags', '/feature-flags', '/featureflags', '/feature_flags', '/config',
    '/remote-config', '/remoteconfig', '/experiments', '/decide', '/toggles',
)

# Titles of bot-check and block pages (Cloudflare, Akamai, AWS WAF, and others)
CHECK_PAGE = re.compile(r'just a moment|attention required|access denied|verify you are human|are you a robot|request blocked|checking your browser|^\s*403\b', re.IGNORECASE)

# Translation files: unreleased copy often ships here first
I18N_PATH = re.compile(r'/(?:locales?|i18n|translations?|lang|messages|intl)/', re.IGNORECASE)
MAX_I18N_FILES = 20
MAX_API_RESPONSES = 80
MAX_API_BYTES = 1_500_000

# Everything a visitor can see: visible text plus the attribute values that show up in the UI
READ_DOM_JS = '''() => {
  const parts = [document.title, document.body ? document.body.innerText : ''];
  const attrs = ['value', 'title', 'alt', 'aria-label', 'placeholder', 'content', 'href', 'src'];
  for (const el of document.querySelectorAll('*')) {
    for (const name of attrs) {
      const v = el.getAttribute && el.getAttribute(name);
      if (v && v.length < 500) parts.push(v);
    }
  }
  return parts.join('\\n').slice(0, 3000000);
}'''

# Collect non-standard window globals (compared with a clean iframe) and web storage.
READ_GLOBALS_JS = '''() => {
  const frame = document.createElement('iframe');
  frame.style.display = 'none';
  document.body.appendChild(frame);
  const standard = new Set(Object.keys(frame.contentWindow));
  frame.remove();
  const globals = {};
  let count = 0;
  for (const key of Object.keys(window)) {
    if (standard.has(key) || count >= 150) continue;
    let value;
    try { value = window[key]; } catch (e) { continue; }
    if (value === null || value === undefined || typeof value === 'function') continue;
    if (typeof value === 'object' && (value instanceof Node || value === window)) continue;
    let text;
    try { text = JSON.stringify(value, (k, v) => (typeof v === 'function' ? undefined : v)); } catch (e) { continue; }
    if (text && text.length > 2) { globals[key] = text.slice(0, 300000); count += 1; }
  }
  const storage = {};
  for (const store of [window.localStorage, window.sessionStorage]) {
    try {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i);
        storage[key] = (store.getItem(key) || '').slice(0, 200000);
      }
    } catch (e) { /* storage blocked */ }
  }
  return { globals, storage };
}'''

# Pages fetchSite should not open: they need a login, change state, or download files.
SKIP_LINK = re.compile(r'login|logout|signin|sign-in|signup|sign-up|register|auth|account|cart|checkout|download|\.pdf$|\.zip$|mailto:|tel:', re.IGNORECASE)

# Webpack runtime: "static/chunks/" + ({12:"name"}[e] || e) + "." + {12:"hash"}[e] + ".js"
LAZY_CHUNK_MAP = re.compile(
    r'"([\w/.\-]*)"\s*\+\s*(?:\(\s*\(?\{([^{}]{1,20000})\}\)?\[\w+\]\s*\|\|\s*\w+\s*\)|\w+)'
    r'\s*\+\s*"([.\-])"\s*\+\s*\(?\{([^{}]{1,80000})\}\)?\[\w+\]\s*\+\s*"((?:\.chunk)?\.m?js)"'
)
CHUNK_MAP_PAIR = re.compile(r'(\w+|"[^"]+"):"([^"]+)"')
# Chunk file names written out in full: "static/js/12.ab12cd34.chunk.js", "./assets/Page-9f8e7d6c.js"
CHUNK_LITERAL = re.compile(r'["\']((?:\.{0,2}/)?(?:[\w.~-]+/)*(?:[\w~-]+[.-])[0-9a-zA-Z_-]{6,}(?:\.chunk)?\.m?js)["\']')
BUILD_MANIFEST_CHUNK = re.compile(r'"(static/(?:chunks|css)/[^"]+\.js)"')
BUILD_MANIFEST_ROUTE = re.compile(r'"(/[^"\s]*)"\s*:\s*\[')


@dataclass
class Capture:
    """Everything one scan collected. The extractor turns it into signals and exposures."""

    start_url: str
    final_url: str = ''
    site_domain: str = ''
    scripts: dict[str, str] = field(default_factory=dict)  # first-party JS: url -> text
    library_scripts: set[str] = field(default_factory=set)  # framework/vendor chunks among them
    inline_scripts: dict[str, str] = field(default_factory=dict)  # label -> text
    flag_configs: dict[str, str] = field(default_factory=dict)  # url -> JSON text
    i18n_files: dict[str, str] = field(default_factory=dict)  # url -> JSON text of translations
    window_globals: dict[str, str] = field(default_factory=dict)  # name -> JSON of the value
    source_map_files: dict[str, str] = field(default_factory=dict)  # public map url -> original sources
    api_responses: dict[str, dict] = field(default_factory=dict)  # url -> {method, status, page, body}
    dom_text: dict[str, str] = field(default_factory=dict)  # page url -> visible text and attribute values
    storage: dict[str, str] = field(default_factory=dict)  # localStorage/sessionStorage key -> value
    third_party_hosts: Counter = field(default_factory=Counter)
    visited: list[str] = field(default_factory=list)
    link_paths: set[str] = field(default_factory=set)  # paths linked from the pages we saw
    next_routes: list[str] = field(default_factory=list)
    queued_chunks: set[str] = field(default_factory=set)  # chunk URLs to fetch after the visits
    lazy_chunks_fetched: int = 0
    lazy_urls: set[str] = field(default_factory=set)  # chunks fetched directly, not loaded by a page
    exposed_source_maps: dict[str, str] = field(default_factory=dict)  # map url -> script url
    sourcemap_headers: dict[str, str] = field(default_factory=dict)  # script url -> map url
    bytes_total: int = 0
    errors: list[str] = field(default_factory=list)
    page_titles: list[str] = field(default_factory=list)
    captured_at: str = ''

    def to_dict(self) -> dict:
        """The capture as plain JSON, saved per site for useCachedScan."""
        return {
            'startUrl': self.start_url,
            'finalUrl': self.final_url,
            'siteDomain': self.site_domain,
            'scripts': self.scripts,
            'libraryScripts': sorted(self.library_scripts),
            'inlineScripts': self.inline_scripts,
            'flagConfigs': self.flag_configs,
            'i18nFiles': self.i18n_files,
            'windowGlobals': self.window_globals,
            'storage': self.storage,
            'sourceMapFiles': self.source_map_files,
            'apiResponses': self.api_responses,
            'domText': self.dom_text,
            'thirdPartyHosts': dict(self.third_party_hosts.most_common()),
            'visited': self.visited,
            'linkPaths': sorted(self.link_paths),
            'nextRoutes': self.next_routes,
            'lazyChunksFetched': self.lazy_chunks_fetched,
            'exposedSourceMaps': self.exposed_source_maps,
            'bytesTotal': self.bytes_total,
            'errors': self.errors,
            'capturedAt': self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Capture:
        """Rebuild a capture saved with `to_dict` (used by useCachedScan)."""
        capture = cls(start_url=data.get('startUrl', ''), final_url=data.get('finalUrl', ''), site_domain=data.get('siteDomain', ''))
        capture.scripts = data.get('scripts', {})
        capture.library_scripts = set(data.get('libraryScripts', []))
        capture.inline_scripts = data.get('inlineScripts', {})
        capture.flag_configs = data.get('flagConfigs', {})
        capture.i18n_files = data.get('i18nFiles', {})
        capture.window_globals = data.get('windowGlobals', {})
        capture.storage = data.get('storage', {})
        capture.source_map_files = data.get('sourceMapFiles', {})
        capture.api_responses = data.get('apiResponses', {})
        capture.dom_text = data.get('domText', {})
        capture.third_party_hosts = Counter(data.get('thirdPartyHosts', {}))
        capture.visited = data.get('visited', [])
        capture.link_paths = set(data.get('linkPaths', []))
        capture.next_routes = data.get('nextRoutes', [])
        capture.lazy_chunks_fetched = data.get('lazyChunksFetched', 0)
        capture.exposed_source_maps = data.get('exposedSourceMaps', {})
        capture.bytes_total = data.get('bytesTotal', 0)
        capture.errors = data.get('errors', [])
        capture.captured_at = data.get('capturedAt', '')
        return capture

    @property
    def loaded(self) -> bool:
        """True when real app code or data arrived, not just a bot-check page."""
        if any(CHECK_PAGE.search(title) for title in self.page_titles[:1]):
            return False
        app_code = any(url not in self.library_scripts for url in self.scripts)
        return app_code or bool(self.api_responses)

    def add_script(self, url: str, text: str) -> None:
        """Keep one first-party script, within the size limits."""
        if url in self.scripts or len(self.scripts) >= MAX_SCRIPTS or self.bytes_total >= MAX_TOTAL_BYTES:
            return
        self.scripts[url] = text
        self.bytes_total += len(text)
        if is_library_file(url, text):
            self.library_scripts.add(url)


def is_flag_service(url: str, site_domain: str = '') -> bool:
    """True for responses from feature-flag vendors, or flag/config paths on the site itself."""
    lowered = url.lower().split('?')[0]
    if any(hint in lowered for hint in FLAG_VENDOR_HINTS):
        return True
    first_party = not site_domain or same_org(host_of(url), site_domain)
    return first_party and any(hint in lowered for hint in FLAG_PATH_HINTS)


def resolve_chunk(script_url: str, path: str) -> str:
    """Resolve a chunk path written inside a script to a full URL."""
    if path.startswith(('http://', 'https://')):
        return path
    parts = urlsplit(script_url)
    origin = f'{parts.scheme}://{parts.netloc}'
    if path.startswith('/'):
        return origin + path
    clean = path.lstrip('./')
    first = clean.split('/')[0]
    idx = parts.path.find(f'/{first}/') if '/' in clean else -1
    if idx >= 0:
        return f'{origin}{parts.path[:idx]}/{clean}'
    return urljoin(script_url, path)


def find_lazy_chunks(script_url: str, text: str) -> set[str]:
    """Best-effort discovery of chunks a bundle can load later. Never raises."""
    found: set[str] = set()
    try:
        for match in LAZY_CHUNK_MAP.finditer(text):
            prefix, names_raw, sep, hashes_raw, suffix = match.groups()
            names = {k.strip('"'): v for k, v in CHUNK_MAP_PAIR.findall(names_raw or '')}
            for key, chunk_hash in CHUNK_MAP_PAIR.findall(hashes_raw):
                chunk_id = key.strip('"')
                found.add(resolve_chunk(script_url, f'{prefix}{names.get(chunk_id, chunk_id)}{sep}{chunk_hash}{suffix}'))
        for match in CHUNK_LITERAL.finditer(text):
            found.add(resolve_chunk(script_url, match.group(1)))
    except Exception as exc:  # noqa: BLE001 - discovery is best effort
        Actor.log.debug('Lazy chunk discovery failed for %s: %s', script_url, exc)
    return found


async def launch_browser(playwright: object, kind: str, proxy_url: str | None) -> Browser:
    """A complete, real browser: full Chromium (not the stripped headless shell), or Firefox.

    Some sites refuse the headless shell outright. A full browser loads them like any visitor's
    browser does. Nothing here solves challenges or fakes an identity.
    """
    proxy = _playwright_proxy(proxy_url)
    if kind == 'firefox':
        return await playwright.firefox.launch(headless=True, proxy=proxy)
    try:
        return await playwright.chromium.launch(channel='chromium', headless=True, proxy=proxy)
    except Exception as exc:  # noqa: BLE001 - the full build is missing; use the default one
        Actor.log.debug('Full Chromium is not available (%s); using the default build', exc)
        return await playwright.chromium.launch(headless=True, proxy=proxy)


async def collect(start_url: str, max_pages: int = 3, proxy_url: str | None = None, browser_kind: str = 'chromium') -> Capture:
    """Open the site, visit up to `max_pages` same-domain pages, and capture its JavaScript."""
    capture = Capture(start_url=start_url, site_domain=registrable_domain(host_of(start_url)))
    pending: set[asyncio.Task] = set()

    async with async_playwright() as playwright:
        browser = await launch_browser(playwright, browser_kind, proxy_url)
        # Firefox keeps its own user agent; Chromium gets a current desktop Chrome one
        user_agent = None if browser_kind == 'firefox' else USER_AGENT
        context = await browser.new_context(user_agent=user_agent, viewport={'width': 1440, 'height': 900}, locale='en-IN')
        page = await context.new_page()

        def on_response(response: Response) -> None:
            task = asyncio.create_task(_handle_response(response, capture))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on('response', on_response)

        try:
            # 1. The start page, then a few same-domain pages linked from it
            await _visit(page, start_url, capture)
            if pending:
                await asyncio.wait(pending, timeout=15)
            if not capture.scripts:
                # Some sites show a short passive browser check first. Give it time to finish on
                # its own, as a normal browser would. Bundle never solves or bypasses challenges.
                Actor.log.info('No app code yet (the site may be running a browser check); waiting a few seconds')
                await page.wait_for_timeout(8_000)
                try:
                    await page.wait_for_load_state('networkidle', timeout=15_000)
                except Exception:  # noqa: BLE001
                    pass
            capture.final_url = page.url
            capture.site_domain = registrable_domain(host_of(page.url)) or capture.site_domain
            await _read_page(page, capture)
            for url in _pick_links(capture, max_pages - 1):
                await _visit(page, url, capture)
                await _read_page(page, capture)
            if pending:
                await asyncio.wait(pending, timeout=30)

            # 2. Code the pages did not load yet: Next.js routes and lazy webpack/Vite chunks
            await _read_next_manifest(page, capture)
            await _fetch_lazy_chunks(context, capture)

            # 3. Source maps referenced by the bundles: are they really public?
            await _check_source_maps(context, capture)
        finally:
            await _close(browser, context)
    return capture


async def _handle_response(response: Response, capture: Capture) -> None:
    """Keep first-party scripts and flag-service JSON; count third-party scripts."""
    try:
        url = response.url
        if url.startswith('data:') or response.status >= 400:
            return
        resource_type = response.request.resource_type
        content_type = (response.headers.get('content-type') or '').lower()
        is_script = resource_type == 'script' or url.split('?')[0].endswith(('.js', '.mjs'))
        if is_script:
            if is_third_party_script(url, capture.site_domain):
                capture.third_party_hosts[registrable_domain(host_of(url))] += 1
                return
            if url in capture.scripts:
                return
            body = await response.body()
            if len(body) <= MAX_FILE_BYTES:
                capture.add_script(url, body.decode('utf-8', errors='replace'))
            map_header = response.headers.get('sourcemap') or response.headers.get('x-sourcemap')
            if map_header:
                capture.sourcemap_headers[url] = urljoin(url, map_header)
        elif 'json' in content_type and is_flag_service(url, capture.site_domain) and len(capture.flag_configs) < MAX_FLAG_RESPONSES:
            body = await response.body()
            if len(body) <= 2_000_000:
                capture.flag_configs[url] = body.decode('utf-8', errors='replace')
        elif (
            'json' in content_type
            and resource_type in ('xhr', 'fetch')
            and not I18N_PATH.search(url)
            and same_org(host_of(url), capture.site_domain)
            and len(capture.api_responses) < MAX_API_RESPONSES
        ):
            key, operation = _api_key(url, response.request.method, response.request.post_data)
            if key in capture.api_responses:
                return
            body = await response.body()
            if len(body) <= MAX_API_BYTES:
                frame = response.frame
                capture.api_responses[key] = {
                    'operation': operation,
                    'method': response.request.method,
                    'status': response.status,
                    'page': frame.url if frame else capture.final_url,
                    'body': body.decode('utf-8', errors='replace'),
                }
        elif (
            'json' in content_type
            and I18N_PATH.search(url)
            and same_org(host_of(url), capture.site_domain)
            and len(capture.i18n_files) < MAX_I18N_FILES
        ):
            body = await response.body()
            if len(body) <= 3_000_000:
                capture.i18n_files[url] = body.decode('utf-8', errors='replace')
    except Exception as exc:  # noqa: BLE001 - one bad response must not stop the scan
        Actor.log.debug('Skipped a response: %s', exc)


def _api_key(url: str, method: str, post_data: str | None) -> tuple[str, str]:
    """One entry per distinct API call. GraphQL-style APIs share one URL, so the operation tells them apart."""
    if method == 'GET' or not post_data:
        return url, ''
    operation = ''
    try:
        payload = json.loads(post_data)
        first = payload[0] if isinstance(payload, list) and payload else payload
        if isinstance(first, dict):
            operation = str(first.get('operationName') or '')
            if not operation and isinstance(first.get('query'), str):
                match = re.search(r'(?:query|mutation)\s+(\w+)', first['query'])
                operation = match.group(1) if match else ''
    except (ValueError, TypeError):
        pass
    digest = hashlib.sha1(post_data.encode('utf-8', errors='replace')).hexdigest()[:10]
    return f'{url}#{operation or digest}', operation


async def _visit(page: Page, url: str, capture: Capture) -> None:
    """Open one page, let it settle, and scroll so lazy code loads."""
    Actor.log.info('Opening %s', url)
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=45_000)
    except Exception as exc:  # noqa: BLE001 - keep whatever loaded
        capture.errors.append(f'{url}: {type(exc).__name__}')
        Actor.log.warning('Could not fully load %s: %s', url, exc)
        if not capture.visited:
            # Without the first page there is nothing to scan
            if not page.url or page.url == 'about:blank':
                raise
    try:
        await page.wait_for_load_state('networkidle', timeout=15_000)
    except Exception:  # noqa: BLE001 - busy sites never go idle; that is fine
        pass
    try:
        for fraction in (0.33, 0.66, 1.0):
            await page.evaluate(f'window.scrollTo(0, document.body.scrollHeight * {fraction})')
            await page.wait_for_timeout(700)
    except Exception:  # noqa: BLE001 - scrolling is a nice-to-have
        pass
    capture.visited.append(page.url)
    try:
        capture.page_titles.append(await page.title())
    except Exception:  # noqa: BLE001
        capture.page_titles.append('')


async def _read_page(page: Page, capture: Capture) -> None:
    """Collect links and inline scripts from the current page."""
    try:
        hrefs = await page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
    except Exception:  # noqa: BLE001
        hrefs = []
    for href in hrefs:
        if registrable_domain(host_of(href)) == capture.site_domain:
            capture.link_paths.add(urlsplit(href).path.rstrip('/') or '/')
    try:
        inline = await page.evaluate(
            '() => Array.from(document.scripts).filter(s => !s.src && s.textContent && s.textContent.length > 80)'
            '.map(s => ({id: s.id || s.type || "", text: s.textContent.slice(0, 3000000)}))'
        )
    except Exception:  # noqa: BLE001
        inline = []
    path = urlsplit(page.url).path or '/'
    try:
        capture.dom_text[page.url] = await page.evaluate(READ_DOM_JS)
    except Exception as exc:  # noqa: BLE001
        Actor.log.debug('Could not read the DOM of %s: %s', page.url, exc)
    try:
        state = await page.evaluate(READ_GLOBALS_JS)
        for name, value in (state.get('globals') or {}).items():
            capture.window_globals.setdefault(name, value)
        for key, value in (state.get('storage') or {}).items():
            capture.storage.setdefault(key, value)
    except Exception as exc:  # noqa: BLE001 - globals are a nice-to-have
        Actor.log.debug('Could not read window globals: %s', exc)
    for number, script in enumerate(inline):
        label = f'inline:{path}#{script["id"] or number}'
        capture.inline_scripts.setdefault(label, script['text'])


def _pick_links(capture: Capture, count: int) -> list[str]:
    """Pick same-domain public pages to visit next, one per top-level section first."""
    if count <= 0:
        return []
    base = capture.final_url or capture.start_url
    host = host_of(base)
    origin = f'{urlsplit(base).scheme}://{host}'
    visited_paths = {urlsplit(u).path.rstrip('/') or '/' for u in capture.visited}
    candidates = sorted(p for p in capture.link_paths if p not in visited_paths and not SKIP_LINK.search(p) and len(p) < 120)
    picked: list[str] = []
    sections: set[str] = set()
    for path in candidates:  # first pass: different sections
        section = path.strip('/').split('/')[0]
        if section and section not in sections:
            sections.add(section)
            picked.append(path)
        if len(picked) >= count:
            break
    for path in candidates:  # second pass: fill up
        if len(picked) >= count:
            break
        if path not in picked:
            picked.append(path)
    return [origin + path for path in picked[:count]]


async def _read_next_manifest(page: Page, capture: Capture) -> None:
    """Next.js: read window.__BUILD_MANIFEST (all routes) and queue the chunks behind them."""
    manifest = None
    try:
        manifest = await page.evaluate(
            '() => window.__BUILD_MANIFEST ? JSON.parse(JSON.stringify(window.__BUILD_MANIFEST)) : null'
        )
    except Exception:  # noqa: BLE001 - not a Next.js site
        manifest = None

    routes: set[str] = set()
    chunk_paths: set[str] = set()
    if isinstance(manifest, dict):
        for key, value in manifest.items():
            if key.startswith('/') and isinstance(value, list):
                routes.add(key)
                chunk_paths.update(v for v in value if isinstance(v, str) and v.endswith('.js'))
        routes.update(r for r in manifest.get('sortedPages', []) if isinstance(r, str))

    # Also read any _buildManifest.js file we captured (covers sites that clear the global)
    for url, text in capture.scripts.items():
        if url.split('?')[0].endswith('_buildManifest.js'):
            routes.update(BUILD_MANIFEST_ROUTE.findall(text))
            chunk_paths.update(BUILD_MANIFEST_CHUNK.findall(text))

    capture.next_routes = sorted(r for r in routes if not r.startswith(('/_app', '/_error', '/_document', '/404', '/500')))
    if not chunk_paths:
        return
    prefix = next((u.split('/_next/')[0] for u in capture.scripts if '/_next/' in u), None)
    if prefix is None:
        prefix = f'{urlsplit(capture.final_url).scheme}://{host_of(capture.final_url)}'
    capture.queued_chunks.update(f'{prefix}/_next/{p}' for p in chunk_paths)
    Actor.log.info('Next.js build manifest: %d routes, %d page chunks', len(capture.next_routes), len(chunk_paths))


async def _fetch_lazy_chunks(context: BrowserContext, capture: Capture) -> None:
    """Fetch chunks the pages did not load: Next.js page chunks first, then lazy chunks."""
    queued: set[str] = set(capture.queued_chunks)
    for url, text in list(capture.scripts.items()):
        queued.update(find_lazy_chunks(url, text))
    script_domains = {capture.site_domain} | {registrable_domain(host_of(u)) for u in capture.scripts}
    todo = [
        u for u in sorted(queued)
        if u not in capture.scripts
        and registrable_domain(host_of(u)) in script_domains
        and not is_third_party_script(u, capture.site_domain)
    ][:MAX_EXTRA_CHUNKS]
    if not todo:
        return
    await Actor.set_status_message(f'Fetching {len(todo)} code chunks the pages did not load yet')
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch(url: str) -> None:
        async with semaphore:
            if capture.bytes_total >= MAX_TOTAL_BYTES:
                return
            try:
                response = await context.request.get(url, timeout=20_000)
                if response.ok:
                    body = await response.body()
                    if len(body) <= MAX_FILE_BYTES and body[:15].lstrip()[:1] not in (b'<',):
                        capture.add_script(url, body.decode('utf-8', errors='replace'))
                        capture.lazy_chunks_fetched += 1
                        capture.lazy_urls.add(url)
            except Exception as exc:  # noqa: BLE001 - a missing chunk is fine
                Actor.log.debug('Chunk fetch failed %s: %s', url, exc)

    await asyncio.gather(*(fetch(url) for url in todo))
    Actor.log.info('Fetched %d of %d extra chunks', capture.lazy_chunks_fetched, len(todo))


async def _check_source_maps(context: BrowserContext, capture: Capture) -> None:
    """Check whether referenced source maps can be downloaded. Only the first bytes are read."""
    candidates: dict[str, str] = dict((m, s) for s, m in capture.sourcemap_headers.items())
    for script_url, text in capture.scripts.items():
        match = SOURCE_MAP_COMMENT.search(text[-2000:])
        if match and not match.group(1).startswith('data:'):
            candidates.setdefault(urljoin(script_url, match.group(1)), script_url)
    for map_url, script_url in list(candidates.items())[:MAX_SOURCE_MAP_CHECKS]:
        try:
            response = await context.request.get(map_url, timeout=15_000)
            if response.ok:
                head = (await response.body())[:4000]
                if b'"mappings"' in head or b'"sources"' in head:
                    capture.exposed_source_maps[map_url] = script_url
                    await _read_source_map(response, map_url, capture)
        except Exception as exc:  # noqa: BLE001
            Actor.log.debug('Source map check failed %s: %s', map_url, exc)


async def _read_source_map(response: object, map_url: str, capture: Capture) -> None:
    """When a source map is public, scan its original sources too (they are not minified)."""
    if len(capture.source_map_files) >= MAX_SOURCE_MAPS_READ:
        return
    try:
        data = await response.json()
        sources = [s for s in (data.get('sourcesContent') or []) if isinstance(s, str) and 'node_modules' not in s[:200]]
        text = '\n'.join(sources)[:MAX_FILE_BYTES]
        if text:
            capture.source_map_files[map_url] = text
            capture.bytes_total += len(text)
    except Exception as exc:  # noqa: BLE001 - a broken map is fine
        Actor.log.debug('Could not read source map %s: %s', map_url, exc)


def _playwright_proxy(proxy_url: str | None) -> dict | None:
    """Turn an Apify Proxy URL into Playwright's proxy settings."""
    if not proxy_url:
        return None
    parts = urlsplit(proxy_url)
    proxy = {'server': f'{parts.scheme}://{parts.hostname}:{parts.port}'}
    if parts.username:
        proxy['username'] = parts.username
    if parts.password:
        proxy['password'] = parts.password
    return proxy


async def _close(browser: Browser, context: BrowserContext) -> None:
    try:
        await context.close()
        await browser.close()
    except Exception:  # noqa: BLE001
        pass
