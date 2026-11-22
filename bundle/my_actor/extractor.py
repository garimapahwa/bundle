"""Find product signals and exposures in JavaScript bundles and feature-flag config.

This module is pure Python: no Apify, no network, no browser. It takes text in and returns plain
dicts out, so it can be tested on a saved bundle and run from the command line:

    python -m my_actor.extractor path/to/chunk.js --domain groww.in

Signals are clues about what a product team is building:
    feature_flag, hidden_route, api_endpoint, partner_integration, native_capability,
    plan_or_pricing, locale, ui_copy

Exposures are things a site owner probably did not mean to ship:
    internal_host, source_map, secret_like (always masked, never tested)

Every signal gets a score from 0 to 100. Real product clues rank high, library noise ranks low
or is dropped before it gets a score.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

SIGNAL_TYPES = (
    'feature_flag',
    'hidden_route',
    'api_endpoint',
    'partner_integration',
    'native_capability',
    'plan_or_pricing',
    'locale',
    'ui_copy',
)

BASE_SCORE = {
    'feature_flag': 45,
    'hidden_route': 40,
    'api_endpoint': 45,
    'partner_integration': 50,
    'native_capability': 50,
    'plan_or_pricing': 45,
    'locale': 20,
    'ui_copy': 50,
}

# --------------------------------------------------------------------------------------------
# Noise: third-party scripts, library files, and words that mean nothing on their own
# --------------------------------------------------------------------------------------------

# Scripts from these hosts are analytics, ads, monitoring, chat, consent, or generic CDNs.
# They are dropped before extraction: they say nothing about the target's product.
THIRD_PARTY_SCRIPT_HOSTS = (
    'googletagmanager.com', 'google-analytics.com', 'analytics.google.com', 'doubleclick.net',
    'googlesyndication.com', 'googleadservices.com', 'google.com', 'gstatic.com', 'googleapis.com',
    'youtube.com', 'ytimg.com', 'facebook.net', 'facebook.com', 'fbcdn.net', 'connect.facebook.net',
    'hotjar.com', 'clarity.ms', 'newrelic.com', 'nr-data.net', 'sentry.io', 'sentry-cdn.com',
    'datadoghq.com', 'datadoghq-browser-agent.com', 'browser-intake-datadoghq.com', 'segment.com',
    'segment.io', 'mixpanel.com', 'mxpnl.com', 'amplitude.com', 'intercom.io', 'intercomcdn.com',
    'zendesk.com', 'zdassets.com', 'freshchat.com', 'freshworks.com', 'wchat.freshchat.com',
    'drift.com', 'driftt.com', 'crisp.chat', 'tawk.to', 'hubspot.com', 'hs-scripts.com',
    'hs-analytics.net', 'licdn.com', 'linkedin.com', 'ads-twitter.com', 'twitter.com',
    'analytics.tiktok.com', 'tiktok.com', 'moengage.com', 'clevertap.com', 'clevertap-prod.com',
    'webengage.com', 'webengage.co', 'branch.io', 'appsflyer.com', 'onesignal.com', 'recaptcha.net',
    'cloudflareinsights.com', 'cookielaw.org', 'onetrust.com', 'cookiebot.com', 'usercentrics.eu',
    'unpkg.com', 'jsdelivr.net', 'cdnjs.cloudflare.com', 'polyfill.io', 'bing.com', 'bat.bing.com',
    'snapchat.com', 'sc-static.net', 'pinterest.com', 'pinimg.com', 'quantserve.com',
    'scorecardresearch.com', 'criteo.com', 'criteo.net', 'taboola.com', 'outbrain.com',
    'adroll.com', 'optimizely.com', 'posthog.com', 'growthbook.io', 'launchdarkly.com',
    'statsig.com', 'statsigapi.net', 'featuregates.org', 'flagsmith.com', 'split.io',
    'vwo.com', 'visualwebsiteoptimizer.com', 'fullstory.com', 'logrocket.com', 'lr-ingest.io',
    'smartlook.com', 'mouseflow.com', 'heapanalytics.com', 'heap.io', 'pendo.io', 'appcues.com',
    'userpilot.io', 'chameleon.io', 'yellow.ai', 'haptik.ai', 'verloop.io', 'gupshup.io',
    'razorpay.com', 'checkout.razorpay.com', 'js.stripe.com', 'paypal.com', 'paypalobjects.com',
    'cashfree.com', 'juspay.in', 'apple.com', 'trustpilot.com', 'vimeo.com', 'jwplayer.com',
    # Bot checks and captchas: never product code
    'awswaf.com', 'challenges.cloudflare.com', 'hcaptcha.com', 'captcha-delivery.com', 'perimeterx.net',
    'px-cdn.net', 'px-cloud.net', 'kasada.io', 'arkoselabs.com', 'funcaptcha.com', 'akamaihd.net',
)

# Partner candidates from these hosts are infrastructure or social links, not partnerships.
NOISE_PARTNER_HOSTS = THIRD_PARTY_SCRIPT_HOSTS + (
    'w3.org', 'schema.org', 'reactjs.org', 'react.dev', 'github.com', 'githubusercontent.com',
    'github.io', 'npmjs.com', 'npmjs.org', 'nodejs.org', 'cloudflare.com', 'cloudfront.net',
    'amazonaws.com', 'akamaized.net', 'akamaihd.net', 'azureedge.net', 'fastly.net', 'mozilla.org',
    'wikipedia.org', 'example.com', 'example.org', 'localhost', 'typekit.net', 'fonts.com',
    'whatsapp.com', 'wa.me', 't.me', 'telegram.me', 'telegram.org', 'instagram.com', 'x.com',
    't.co', 'youtu.be', 'app.link', 'onelink.me', 'firebaseio.com', 'firebaseapp.com',
    'firebase.com', 'gravatar.com', 'yahoo.com', 'microsoft.com', 'live.com', 'outlook.com',
    'gmail.com', 'ampproject.org', 'apache.org', 'jquery.com', 'lodash.com', 'babeljs.io',
    'webpack.js.org', 'nextjs.org', 'vercel.com', 'vercel.app', 'netlify.app', 'herokuapp.com',
    'goo.gl', 'bit.ly', 'medium.com', 'reddit.com', 'quora.com', 'play.google.com',
    'apps.apple.com', 'itunes.apple.com', 'mathjax.org', 'json-schema.org', 'openstreetmap.org',
    'mapbox.com', 'here.com', 'gstatic.cn', 'feross.org', 'momentjs.com', 'date-fns.org',
    'tc39.es', 'ecma-international.org', 'whatwg.org', 'chromium.org', 'webkit.org',
    'stackoverflow.com', 'npm.im', 'unsplash.com', 'cdn.ampproject.org', 'opensource.org',
    'creativecommons.org', 'xmlsoap.org', 'purl.org', 'ogp.me', 'iana.org', 'ietf.org',
    'graphql.org', 'apollographql.com', 'redux.js.org', 'mui.com', 'material-ui.com',
    'tailwindcss.com', 'swiperjs.com', 'lottiefiles.com', 'airbnb.io', 'fb.me', 'fb.com',
)

# Chunks that are framework or polyfill code, not product code.
LIBRARY_FILE_PATTERN = re.compile(
    r'(?:^|/)(?:framework|polyfills?|webpack|webpack-runtime|runtime|main-app|react-dom|'
    r'react|vendors?(?:~[\w~.-]+)?|commons|lib-[0-9a-f]+|amp)[.-][\w.-]*\.js$',
    re.IGNORECASE,
)
LIBRARY_TEXT_MARKERS = (
    'react-dom.production.min.js',
    '__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED',
    'Minified React error #',
)

# Words that carry no product meaning on their own.
GENERIC_TOKENS = {
    'is', 'has', 'can', 'should', 'show', 'hide', 'use', 'allow', 'allowed', 'enable', 'enabled',
    'disable', 'disabled', 'flag', 'flags', 'feature', 'features', 'toggle', 'switch', 'on', 'off',
    'true', 'false', 'active', 'inactive', 'visible', 'hidden', 'live', 'value', 'default',
    'state', 'status', 'type', 'key', 'id', 'name', 'data', 'config', 'settings', 'setting',
    'mode', 'the', 'a', 'an', 'of', 'for', 'to', 'in', 'and', 'or', 'ff', 'ui', 'eligible',
    'v', 'item', 'items', 'list', 'new', 'old', 'flow', 'page', 'screen', 'view', 'all', 'web',
    'app', 'button', 'modal', 'popup', 'banner', 'card', 'section', 'tab', 'text', 'icon',
}

# Tokens that mean a flag is about tooling, not the product (React, logging, analytics, ...).
TECH_NOISE_TOKENS = {
    'debug', 'logging', 'log', 'logs', 'logger', 'tracking', 'track', 'analytics', 'sentry',
    'cookie', 'cookies', 'dev', 'devtools', 'profiler', 'profiling', 'strict', 'scheduler',
    'cache', 'caching', 'ssr', 'hydration', 'hydrate', 'animation', 'animations', 'transition',
    'transitions', 'scroll', 'focus', 'keyboard', 'touch', 'passive', 'pointer', 'mouse', 'hover',
    'drag', 'resize', 'observer', 'fetch', 'prefetch', 'preload', 'lazy', 'polyfill', 'react',
    'redux', 'router', 'worker', 'sw', 'pwa', 'vitals', 'perf', 'performance', 'telemetry',
    'metrics', 'gtm', 'ga', 'fb', 'pixel', 'hotjar', 'clarity', 'newrelic', 'datadog', 'csp',
    'cors', 'test', 'tests', 'testing', 'mock', 'mocks', 'e2e', 'storybook', 'hmr', 'console',
    'warning', 'warnings', 'error', 'errors', 'trace', 'tracing', 'suspense', 'concurrent',
    'legacy', 'fizz', 'offscreen', 'portal', 'ref', 'refs', 'memo', 'effect',
    'effects', 'hooks', 'hook', 'context', 'dom', 'shadow', 'css', 'style', 'styles', 'theme',
    'dark', 'rtl', 'a11y', 'aria', 'swipe', 'autoplay', 'loop', 'zoom', 'pagination', 'navigation',
    'mousewheel', 'grab', 'cursor', 'slides', 'virtual', 'freemode',
}

# Words that make a clue more interesting: launches, new products, money, partners.
TEASER_TOKENS = {
    'beta', 'launch', 'launching', 'waitlist', 'early', 'preview', 'coming', 'soon', 'invite',
    'pilot', 'labs', 'experiment', 'experimental', 'v2', 'v3', 'redesign', 'revamp', 'arch',
    'rearch', 'migration', 'upcoming', 'pro', 'premium', 'plus', 'gold', 'silver', 'wallet',
    'api', 'developer', 'developers', 'partner', 'partners', 'international', 'global', 'us',
    'uss', 'crypto', 'ai', 'assistant', 'copilot', 'gpt', 'llm', 'credit', 'loan', 'loans',
    'insurance', 'upi', 'card', 'cards', 'subscription', 'membership', 'rewards', 'oauth',
    'consent', 'algo', 'trading', 'futures', 'options', 'fno', 'mtf', 'bonds', 'ipo', 'nps',
    'sip', 'mutual', 'fund', 'funds', 'stocks', 'etf', 'fd', 'deposit', 'payments', 'pay',
    'checkout', 'delivery', 'instamart', 'dineout', 'genie', 'minis', 'quick', 'express',
    'marketplace', 'b2b', 'enterprise', 'business', 'grocery', 'pharmacy', 'health', 'travel',
    'quiz', 'game', 'games', 'live', 'video', 'voice', 'chatbot', 'bot', 'agent',
}

# Next.js CSS module class names (`card_title__aB3x9`) and other hashed class names.
CSS_MODULE_PATTERN = re.compile(r'^[A-Za-z][\w-]*__[\w-]{5,8}$|^[A-Za-z][\w-]*_[\w-]+__[\w-]{4,8}$')
HASHED_CLASS_PATTERN = re.compile(r'^(?:css|sc|jsx|emotion|tw|chakra|mui)-[\w-]{4,}$', re.IGNORECASE)

# --------------------------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------------------------

# One pass over all three quote styles, in order, so a quote inside another string is consumed
# with it and does not throw the matching out of step.
STRING_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')
TEMPLATE_PART = re.compile(r'\$\{[^}]{0,80}\}')

# `e.SOME_FLAG = "some_flag_enabled"`: how GrowthBook-style flag enums look after minification
ENUM_ASSIGNMENT = re.compile(r'\b[A-Za-z_$][\w$]{0,3}\.([A-Z][A-Z0-9_]{2,80})\s*=\s*["\']([A-Za-z0-9_.:\-]{3,100})["\']')
# `{GROWW_API_ENABLED:"groww_api_enabled"}`: the same enum written as an object map
OBJECT_ENUM = re.compile(r'[{,]\s*([A-Z][A-Z0-9_]{2,80})\s*:\s*["\']([a-z][a-z0-9_.\-]{2,100})["\']')
# `isUSSEnabled`, `showNewOnboardingFlag`, `hasCreditLineAccess`: only in property positions
# (`o.isX`, `{isX:`, `,isX:`, `"isX"`). Property names and strings survive minification;
# local variable and function names do not, so they are never read.
CAMEL_FLAG = re.compile(
    r'(?<=[.{,"\'`])((?:is|has|show|enable|can|should)[A-Z][A-Za-z0-9]{1,50}?'
    r'(?:Enabled|Enable|Flag|Allowed|Visible|Live|Active|Eligible|Available|Access|Beta))\b'
)
CAMEL_SPLIT = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')

SNAKE_OR_KEBAB = re.compile(r'^[a-z][a-z0-9]*(?:[_.\-][a-z0-9]+){1,8}$')
UPPER_SNAKE = re.compile(r'^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,8}$')
LOCALE = re.compile(r'^[a-z]{2}[-_][A-Z]{2}$')
PATH = re.compile(r'^/[A-Za-z0-9\[\]:_-][A-Za-z0-9\[\]:_./%{}?=&-]{0,120}$')
ASSET_EXTENSION = re.compile(
    r'\.(?:js|mjs|cjs|css|scss|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot|mp4|webm|'
    r'mp3|wav|ogg|pdf|txt|xml|html?|lottie|wasm|zip)(?:[?#].*)?$',
    re.IGNORECASE,
)
API_PATH = re.compile(r'(?:^|/)(?:api|apis|graphql|gql|rest|rpc|v\d{1,2}|gateway|oauth2?|bff)(?:/|$)', re.IGNORECASE)
STATIC_ROUTE_PREFIXES = ('/_next', '/static', '/assets', '/fonts', '/images', '/img', '/icons', '/favicon', '/build', '/dist', '/public', '/media', '/cdn-cgi', '/__')
COMMON_ROUTES = {
    '/', '/login', '/logout', '/signin', '/sign-in', '/signup', '/sign-up', '/register', '/about',
    '/about-us', '/contact', '/contact-us', '/terms', '/terms-and-conditions', '/privacy',
    '/privacy-policy', '/help', '/support', '/faq', '/faqs', '/blog', '/careers', '/search',
    '/home', '/404', '/500', '/_error', '/_app', '/_document', '/sitemap', '/settings', '/profile',
    '/account', '/dashboard', '/cart', '/checkout', '/orders', '/offers', '/press', '/disclaimer',
}
DOMAIN_LITERAL = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
    r'(?:com|in|io|ai|co|xyz|app|dev|net|org|tech|money|finance|me|so|sh|cloud|us|uk|gg|tv|club|store|shop|biz|info|trade|exchange)$'
)
URL_IN_TEXT = re.compile(r'(?:https?:)?//([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+)(?::\d+)?(?=[/"\'`?#\s)]|$)', re.IGNORECASE)
PRIVATE_IP = re.compile(r'//((?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3})\.\d{1,3}\.\d{1,3})\b')
SOURCE_MAP_COMMENT = re.compile(r'//[#@]\s*sourceMappingURL=([^\s\'"]+)')
PLAN_OR_PRICING = re.compile(
    r'\b(?:free|pro|premium|plus|gold|platinum|elite|enterprise|business|starter|basic|one|max|lite)'
    r'[ _-]?(?:plan|tier|subscription|membership|pass|trial)s?\b'
    r'|(?:₹|rs\.?\s?|inr\s?|\$|usd\s?)\d[\d,]*(?:\.\d+)?\s*(?:/|per\s)\s*(?:mo|month|yr|year|order|user)'
    r'|\b(?:free trial|per month|billed (?:monthly|annually)|pricing plan|upgrade to)\b',
    re.IGNORECASE,
)
UI_TEASER = re.compile(
    r'\b(?:coming soon|introducing|new feature|now live|now available|launching|early access|'
    r'join (?:the )?waitlist|beta|be the first|sneak peek|pre-?register|try the new|exclusive access|'
    r'get notified|notify me|limited access|invite only|by invitation)\b',
    re.IGNORECASE,
)
REDUX_SUFFIXES = ('_REQUEST', '_SUCCESS', '_FAILURE', '_FAILED', '_PENDING', '_FULFILLED', '_REJECTED', '_ERROR', '_RESET', '_START', '_END')
BRIDGE_MARKERS = (
    'reactnativewebview', 'messagehandlers', 'jsbridge', 'nativebridge', 'bridge', 'postmessage',
    'androidinterface', 'window.android', 'callnative', 'invokenative', 'sendtonative',
    'flutter_inappwebview', 'webviewbridge', 'isinapp', 'inappwebview', 'native',
)
NATIVE_TOKENS = {
    'installed', 'apps', 'app', 'upi', 'camera', 'contact', 'contacts', 'location', 'gps',
    'biometric', 'fingerprint', 'faceid', 'haptic', 'vibrate', 'share', 'notification',
    'notifications', 'permission', 'permissions', 'deeplink', 'clipboard', 'sms', 'otp',
    'bluetooth', 'nfc', 'qr', 'scan', 'scanner', 'inapp', 'native', 'device', 'battery',
    'storage', 'download', 'webview', 'close', 'open', 'launch', 'quiz', 'payment', 'pay',
}
INTERNAL_HOST_LABELS = {
    'internal', 'intranet', 'corp', 'staging', 'stage', 'stg', 'uat', 'qa', 'dev', 'develop',
    'development', 'preprod', 'pre-prod', 'nonprod', 'non-prod', 'sandbox', 'test', 'testing',
    'int', 'perf', 'admin', 'local', 'devel', 'sit', 'canary',
}
INTERNAL_TLDS = ('.internal', '.local', '.corp', '.lan', '.intranet')

# Secret-like strings. Every match is masked; none is ever sent anywhere to check if it works.
SECRET_PATTERNS = (
    ('aws_access_key', re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), 'high'),
    ('stripe_secret_key', re.compile(r'\b(sk_live_[0-9a-zA-Z]{20,})\b'), 'high'),
    ('github_token', re.compile(r'\b(gh[pousr]_[A-Za-z0-9]{36,})\b'), 'high'),
    ('slack_token', re.compile(r'\b(xox[baprs]-[A-Za-z0-9-]{10,})\b'), 'high'),
    ('private_key', re.compile(r'(-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----)'), 'high'),
    ('openai_key', re.compile(r'\b(sk-(?:proj-)?[A-Za-z0-9_-]{32,})\b'), 'high'),
    ('jwt', re.compile(r'\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b'), 'medium'),
    ('google_api_key', re.compile(r'\b(AIza[0-9A-Za-z_-]{35})\b'), 'low'),
    ('stripe_publishable_key', re.compile(r'\b(pk_live_[0-9a-zA-Z]{20,})\b'), 'low'),
    (
        'generic_secret',
        re.compile(
            r'(?:api[_-]?key|api[_-]?secret|client[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password)'
            r'["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-+/=]{16,120})["\']',
            re.IGNORECASE,
        ),
        'medium',
    ),
)
# Keys that are meant to be in the browser: storefront tokens, publishable keys, error trackers
PUBLIC_KEY_HINT = re.compile(
    r'storefront|publishable|public[_-]?key|bugsnag|sentry|datadog|client[_-]?token|shopify-features|recaptcha|site[_-]?key|analytics|segment|mixpanel|amplitude',
    re.IGNORECASE,
)
SECRET_NOTES = {
    'public_client_key': 'A client key meant to be public (for example a storefront or error-tracking key). Check its permissions; no rotation needed.',
    'google_api_key': 'Google browser API keys (for example Firebase) are public by design. Check that it is restricted to your domains and APIs.',
    'stripe_publishable_key': 'Stripe publishable keys are meant to be public. No action unless it is a secret key.',
    'jwt': 'A token embedded in a bundle. If it grants access to anything, revoke it and fetch tokens at runtime instead.',
}

EXPOSURE_FIXES = {
    'internal_host': 'Keep staging and internal hostnames out of production bundles: inject per-environment config at build time, and evaluate environment switches on the server.',
    'source_map': 'Stop serving .map files in production. Upload source maps privately to your error tracker (Sentry, Datadog) instead.',
    'secret_like': 'If this is a server secret, rotate it now and move it server-side. If it is a browser key, restrict it by domain and API scope.',
}

# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------

_TWO_PART_SUFFIXES = {'co.in', 'co.uk', 'com.au', 'co.jp', 'com.br', 'co.id', 'com.sg', 'net.in', 'org.in', 'firm.in', 'gen.in', 'ac.in', 'gov.in', 'com.mx', 'co.za', 'com.tr'}


def registrable_domain(host: str) -> str:
    """Return the registrable part of a hostname: `assets.groww.in` -> `groww.in`."""
    host = (host or '').lower().strip('.').split(':')[0]
    labels = host.split('.')
    if len(labels) <= 2:
        return host
    if '.'.join(labels[-2:]) in _TWO_PART_SUFFIXES:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:])


def same_org(host: str, site_domain: str) -> bool:
    """True when a host belongs to the same company: matiks.org and api.matiks.in are matiks.com's own."""
    if not host or not site_domain:
        return False
    a, b = registrable_domain(host), registrable_domain(site_domain)
    return a == b or (a.split('.')[0] == b.split('.')[0] and len(a.split('.')[0]) >= 4)


def host_of(url: str) -> str:
    """Return the lowercase hostname of a URL, or '' if there is none."""
    try:
        return (urlsplit(url if '//' in url else f'//{url}').hostname or '').lower()
    except ValueError:
        return ''


def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == s or host.endswith('.' + s) for s in suffixes)


def is_third_party_script(url: str, site_domain: str = '') -> bool:
    """True for analytics, ads, monitoring, chat, consent, and generic CDN scripts."""
    host = host_of(url)
    if not host:
        return False
    if site_domain and same_org(host, site_domain):
        return False
    return _host_matches(host, THIRD_PARTY_SCRIPT_HOSTS)


# Platform code served from the site's own domain, but written by the platform vendor
PLATFORM_PATH = re.compile(r'/cdn/shopifycloud/|/cdn/wpm/|/cdn/shopify/s/files/[^/]+/assets/shopify|/wp-includes/|/_vercel/|/cdn-cgi/', re.IGNORECASE)


def is_platform_file(url: str) -> bool:
    """True for scripts the hosting platform ships (Shopify, WordPress core, Cloudflare), not the site's team."""
    return bool(PLATFORM_PATH.search(urlsplit(url).path if '://' in url else url))


def is_library_file(url: str, text: str = '') -> bool:
    """True for framework, polyfill, and vendor chunks that hold library code only."""
    path = urlsplit(url).path if '://' in url else url
    if LIBRARY_FILE_PATTERN.search(path) or PLATFORM_PATH.search(path):
        return True
    head = text[:200_000]
    return any(marker in head for marker in LIBRARY_TEXT_MARKERS)


def split_tokens(value: str) -> list[str]:
    """Split a camelCase, snake_case, kebab-case, or dotted name into lowercase tokens."""
    parts: list[str] = []
    for chunk in re.split(r'[_\-.:/\s]+', value):
        if not chunk:
            continue
        parts.extend(CAMEL_SPLIT.findall(chunk) or [chunk])
    return [p.lower() for p in parts if p]


def meaningful_tokens(value: str) -> list[str]:
    """Tokens that say something about the product: not generic words, not tech noise."""
    return [t for t in split_tokens(value) if t not in GENERIC_TOKENS and t not in TECH_NOISE_TOKENS and len(t) > 1]


def is_css_module_name(value: str) -> bool:
    """True for `card_title__aB3x9`-style CSS module names and hashed class names."""
    return bool(CSS_MODULE_PATTERN.match(value) or HASHED_CLASS_PATTERN.match(value))


def mask_secret(value: str) -> str:
    """Mask a secret so it can be shown but not used: first 4 characters and the length."""
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}{"*" * 8} ({len(value)} chars, masked)'


def mask_secrets_in(text: str) -> str:
    """Replace every secret-like string inside a piece of text with its masked form."""
    for _name, pattern, _severity in SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(0).replace(m.group(1), mask_secret(m.group(1))), text)
    return text


def context_at(text: str, start: int, end: int, radius: int = 70) -> str:
    """A short, single-line, secret-free snippet around a match."""
    snippet = text[max(0, start - radius) : min(len(text), end + radius)]
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    return mask_secrets_in(snippet)[:220]


def _teaser_boost(tokens: list[str]) -> int:
    return min(15, 5 * sum(1 for t in tokens if t in TEASER_TOKENS))


def _clip(score: float) -> int:
    return max(0, min(100, round(score)))


def _signal(kind: str, value: str, context: str, source: str, score: float, **extra: object) -> dict:
    return {
        'type': kind,
        'value': value,
        'context': context,
        'source': source,
        'occurrences': 1,
        'score': _clip(score),
        **extra,
    }


# --------------------------------------------------------------------------------------------
# Classification of single values
# --------------------------------------------------------------------------------------------


def _flag_score(value: str, base: float) -> float | None:
    """Score a flag-like name, or return None if it is noise."""
    tokens = split_tokens(value)
    meaningful = meaningful_tokens(value)
    if not meaningful:
        return None
    if any(t in TECH_NOISE_TOKENS for t in tokens) and len(meaningful) < 2:
        return None
    score = base + min(9, 3 * (len(meaningful) - 1)) + _teaser_boost(tokens)
    if any(t in {'test', 'mock', 'dummy', 'sample', 'demo', 'qa'} for t in tokens):
        score -= 25
    return score


def _is_flag_literal(value: str) -> bool:
    tokens = split_tokens(value)
    return any(t in {'enabled', 'enable', 'flag', 'ff', 'rollout', 'experiment', 'killswitch', 'gate', 'gated'} for t in tokens)


def classify_route(path: str, source: str, context: str) -> dict | None:
    """Turn a path literal into an api_endpoint or hidden_route signal, or None for noise."""
    clean = path.split('?')[0].split('#')[0].rstrip('/') or '/'
    if ASSET_EXTENSION.search(clean) or clean.lower().startswith(STATIC_ROUTE_PREFIXES):
        return None
    if '//' in clean or clean.count('/') > 10 or re.fullmatch(r'/[a-z]{1,3}', clean):
        return None  # regex flags (/g, /gi), protocol fragments
    if re.fullmatch(r'[/\d.\-:]+', clean):
        return None  # numbers, dates, versions
    tokens = split_tokens(clean)
    if API_PATH.search(clean):
        score = BASE_SCORE['api_endpoint'] + _teaser_boost([t for t in tokens if t not in {'api', 'apis'}])
        if any(t in {'oauth', 'oauth2', 'consent', 'partner', 'partners', 'developer', 'webhook', 'callback', 'token'} for t in tokens):
            score += 15
        if any(t in {'log', 'logs', 'track', 'tracking', 'event', 'events', 'health', 'ping', 'metrics', 'collect', 'beacon', 'analytics'} for t in tokens):
            score -= 25
        return _signal('api_endpoint', clean, context, source, score)
    if any(c.isupper() for c in clean if c.isalpha()) and not re.search(r'\[[A-Za-z]+\]', clean):
        return None  # routes are lowercase; mixed case is usually code or a file name
    score = BASE_SCORE['hidden_route'] + _teaser_boost(tokens)
    if clean in COMMON_ROUTES:
        score -= 25
    elif clean.count('/') == 1 and '-' not in clean:
        score -= 10  # one-word paths in code are often fragments, not pages
    if len(meaningful_tokens(clean)) == 0:
        score -= 15
    return _signal('hidden_route', clean, context, source, score)


def classify_url(url: str, source: str, context: str, site_domain: str) -> dict | None:
    """Turn a full URL literal into a partner, an endpoint on the site, or None."""
    host = host_of(url)
    if not host or '.' not in host:
        return None
    if site_domain and same_org(host, site_domain):
        path = urlsplit(url if '://' in url else f'https:{url}').path or '/'
        if API_PATH.search(path) or host.split('.')[0] in {'api', 'apis', 'gateway', 'gw', 'bff'}:
            signal = classify_route(path, source, context)
            if signal:
                signal['value'] = f'{host}{signal["value"]}'
            return signal
        return None
    return classify_partner(host, source, context)


def classify_partner(host: str, source: str, context: str) -> dict | None:
    """A third-party host that is not infrastructure is a possible partner integration."""
    host = host.lower().removeprefix('www.')
    if _host_matches(host, NOISE_PARTNER_HOSTS) or len(host) > 80:
        return None
    lowered = context.lower()
    score = BASE_SCORE['partner_integration']
    if any(w in lowered for w in ('callback', 'redirect', 'oauth', 'partner', 'integration', 'consent', 'webhook', 'allowed', 'whitelist', 'allowlist')):
        score += 15
    return _signal('partner_integration', registrable_domain(host), context, source, score, host=host)


def classify_literal(value: str, text: str, start: int, end: int, source: str, site_domain: str) -> dict | None:
    """Classify one string literal from a bundle into a signal, or None if it is noise."""
    value = value.strip()
    if len(value) < 3 or value.startswith('__') or is_css_module_name(value):
        return None

    # Full URLs and protocol-relative URLs
    if value.startswith(('http://', 'https://', '//')):
        return classify_url(value, source, context_at(text, start, end), site_domain)

    # Paths: app routes and API endpoints
    if value.startswith('/') and PATH.match(value):
        return classify_route(value, source, context_at(text, start, end))

    # Locales such as en-IN or hi_IN
    if LOCALE.match(value):
        return _signal('locale', value.replace('_', '-'), context_at(text, start, end, 40), source, BASE_SCORE['locale'])

    # snake_case or kebab-case names: feature flags or bare partner domains
    if SNAKE_OR_KEBAB.match(value):
        if DOMAIN_LITERAL.match(value) and not (site_domain and registrable_domain(value) == registrable_domain(site_domain)):
            return classify_partner(value, source, context_at(text, start, end))
        if _is_flag_literal(value):
            score = _flag_score(value, BASE_SCORE['feature_flag'])
            if score is not None:
                return _signal('feature_flag', value, context_at(text, start, end), source, score)
        return None

    # UPPER_SNAKE: mobile-app bridge commands, or flag names
    if UPPER_SNAKE.match(value):
        return classify_upper(value, text, start, end, source)

    # Human-readable copy that teases something new, and plan or pricing wording
    if ' ' in value:
        letters = sum(c.isalpha() or c == ' ' for c in value) / len(value)
        if letters < 0.8 or len(value.split()) < 2:
            return None
        if PLAN_OR_PRICING.search(value):
            tokens = split_tokens(value)
            return _signal('plan_or_pricing', value, context_at(text, start, end, 40), source, BASE_SCORE['plan_or_pricing'] + _teaser_boost(tokens))
        if UI_TEASER.search(value) and len(value.split()) >= 3:
            tokens = split_tokens(value)
            return _signal('ui_copy', value, context_at(text, start, end, 40), source, BASE_SCORE['ui_copy'] + _teaser_boost(tokens))
        return None

    # A single word that names a plan (gold_plan, premium-tier handled above)
    if PLAN_OR_PRICING.fullmatch(value):
        return _signal('plan_or_pricing', value, context_at(text, start, end, 40), source, BASE_SCORE['plan_or_pricing'])
    return None


def classify_upper(value: str, text: str, start: int, end: int, source: str) -> dict | None:
    """UPPER_SNAKE literals: native bridge commands when near bridge code, else flags or noise."""
    if value.endswith(REDUX_SUFFIXES) or value.startswith(('SET_', 'UPDATE_STATE', 'RESET_', 'FETCH_', 'LOAD_')):
        return None
    tokens = split_tokens(value)
    window = text[max(0, start - 600) : end + 600].lower()
    if any(marker in window for marker in BRIDGE_MARKERS):
        native = [t for t in tokens if t in NATIVE_TOKENS]
        if not native and not _is_flag_literal(value):
            return None
        meaningful = meaningful_tokens(value)
        if not meaningful:
            return None
        score = BASE_SCORE['native_capability'] + (15 if native else 0) + _teaser_boost(tokens)
        return _signal('native_capability', value, context_at(text, start, end), source, score)
    if _is_flag_literal(value):
        score = _flag_score(value, BASE_SCORE['feature_flag'] - 5)
        if score is not None:
            return _signal('feature_flag', value, context_at(text, start, end), source, score)
    return None


# --------------------------------------------------------------------------------------------
# Extraction over whole files
# --------------------------------------------------------------------------------------------


def extract_signals(text: str, source: str = 'inline', site_domain: str = '') -> list[dict]:
    """Find every product signal in one JavaScript file. Returns deduplicated, scored dicts."""
    found: list[dict] = []

    # 1. Flag enums: e.SOME_FLAG = "some_flag_enabled". The strongest flag evidence there is.
    for match in [*ENUM_ASSIGNMENT.finditer(text), *OBJECT_ENUM.finditer(text)]:
        key, value = match.group(1), match.group(2)
        if is_css_module_name(value):
            continue
        flaggy = _is_flag_literal(value) or _is_flag_literal(key)
        if not flaggy:
            # An enum member counts as a flag when its neighbours are flags (GrowthBook enums)
            window = text[max(0, match.start() - 500) : match.end() + 500]
            neighbours = sum(1 for p in (ENUM_ASSIGNMENT, OBJECT_ENUM) for m in p.finditer(window) if _is_flag_literal(m.group(2)))
            if neighbours < 2 or split_tokens(key) != split_tokens(value):
                continue
        score = _flag_score(value, BASE_SCORE['feature_flag'] + 10)
        if score is None:
            continue
        found.append(_signal('feature_flag', value, context_at(text, match.start(), match.end()), source, score, key=key))

    # 2. camelCase flag properties: isUSSEnabled, isGoldEnabled
    for match in CAMEL_FLAG.finditer(text):
        name = match.group(1)
        score = _flag_score(name, BASE_SCORE['feature_flag'] + 10)
        if score is None:
            continue
        found.append(_signal('feature_flag', name, context_at(text, match.start(), match.end()), source, score))

    # 3. Every string literal, classified on its own
    for match in STRING_LITERAL.finditer(text):
        value = match.group(1) if match.group(1) is not None else match.group(2) if match.group(2) is not None else match.group(3)
        if not value or len(value) > 300:
            continue
        if match.group(3) is not None:
            value = TEMPLATE_PART.sub('{id}', value)  # `/api/user/${id}` -> /api/user/{id}
        signal = classify_literal(value, text, match.start(), match.end(), source, site_domain)
        if signal:
            found.append(signal)

    return merge_signals(found)


def extract_flag_config(json_text: str, source: str) -> list[dict]:
    """Read flag names from a feature-flag service response (GrowthBook, LaunchDarkly, ...)."""
    try:
        data = json.loads(json_text)
    except (ValueError, TypeError):
        return []
    found: list[dict] = []

    def add(name: object, state: object) -> None:
        if not isinstance(name, str) or not (2 < len(name) <= 120):
            return
        if re.fullmatch(r'[A-Za-z0-9+/=]{16,}', name) and not re.search(r'[_\-.]', name):
            return  # hashed names (Statsig) mean nothing to a reader
        score = _flag_score(name, BASE_SCORE['feature_flag'] + 10)
        if score is None:
            return
        off = state in (False, 0, 'false', 'off', 'OFF', None) or state == {}
        state_text = json.dumps(state, ensure_ascii=False)[:80] if state is not None else 'unknown'
        found.append(_signal('feature_flag', name, f'live flag config, state: {state_text}', source, score + (8 if off else 3), live=True, liveState=state_text))

    def state_of(entry: object) -> object:
        if isinstance(entry, dict):
            for key in ('value', 'defaultValue', 'enabled', 'on', 'feature_state_value'):
                if key in entry:
                    return entry[key]
            return None
        return entry

    def walk(node: object, depth: int) -> None:
        if depth > 4:
            return
        if isinstance(node, dict):
            # LaunchDarkly client SDK: {"flag-key": {"value": ..., "variation": 0}}
            if depth == 0 and node and all(isinstance(v, dict) and 'value' in v and ('variation' in v or 'version' in v) for v in node.values()):
                for name, entry in node.items():
                    add(name, entry.get('value'))
                return
            for key, value in node.items():
                if key in {'features', 'featureFlags', 'feature_flags', 'flags', 'feature_gates', 'dynamic_configs', 'entries', 'toggles', 'experiments', 'featureFlagPayloads'}:
                    if isinstance(value, dict):
                        for name, entry in value.items():
                            add(entry.get('name', name) if isinstance(entry, dict) else name, state_of(entry))
                    elif isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, dict):
                                feature = entry.get('feature') if isinstance(entry.get('feature'), dict) else {}
                                add(entry.get('key') or entry.get('name') or feature.get('name'), state_of(entry))
                else:
                    walk(value, depth + 1)
        elif isinstance(node, list):
            for entry in node[:500]:
                if isinstance(entry, dict) and isinstance(entry.get('feature'), dict):
                    add(entry['feature'].get('name'), entry.get('enabled'))  # Flagsmith
                else:
                    walk(entry, depth + 1)

    walk(data, 0)
    return merge_signals(found)


def extract_exposures(text: str, source: str = 'inline', site_domain: str = '') -> list[dict]:
    """Find internal hosts, source map references, and secret-like strings in one file."""
    found: dict[tuple[str, str], dict] = {}

    def add(kind: str, value: str, context: str, severity: str, **extra: object) -> None:
        key = (kind, value)
        if key in found:
            found[key]['occurrences'] += 1
            return
        found[key] = {
            'type': kind,
            'value': value,
            'context': context,
            'source': source,
            'severity': severity,
            'occurrences': 1,
            'fix': EXPOSURE_FIXES[kind],
            **extra,
        }

    # Secret-like strings: masked, never tested
    for name, pattern, severity in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            secret = match.group(1)
            if name == 'generic_secret' and not _looks_random(secret):
                continue  # placeholders, routes, enum values, and variable names, not secrets
            kind, level, note = name, severity, SECRET_NOTES.get(name, '')
            key_name = text[max(0, match.start() - 30) : match.start(1)]  # just the name this value is assigned to
            in_page_config = source.startswith(('window.', 'storage:'))  # config every visitor's browser gets
            if name == 'generic_secret' and (in_page_config or PUBLIC_KEY_HINT.search(key_name) or PUBLIC_KEY_HINT.search(source)):
                kind, level, note = 'public_client_key', 'low', SECRET_NOTES['public_client_key']
            add('secret_like', mask_secret(secret), context_at(text, match.start(), match.end(), 40), level, secret_kind=kind, note=note)

    # Internal hosts: staging, dev, and internal hostnames on the site's own domain, and private IPs
    own = registrable_domain(site_domain) if site_domain else ''
    for match in URL_IN_TEXT.finditer(text):
        host = match.group(1).lower()
        if not _looks_internal(host, own):
            continue
        add('internal_host', host, context_at(text, match.start(), match.end(), 50), 'medium')
    for match in PRIVATE_IP.finditer(text):
        add('internal_host', match.group(1), context_at(text, match.start(), match.end(), 50), 'medium')

    # Source map references. The collector checks if the map is really downloadable.
    for match in SOURCE_MAP_COMMENT.finditer(text):
        target = match.group(1)
        if target.startswith('data:'):
            continue
        add('source_map', target, f'sourceMappingURL={target[:120]}', 'low', verified=False)

    return list(found.values())


def _looks_random(value: str) -> bool:
    """True for key-like strings: mixed character classes, not words, not a path."""
    if value.startswith(('/', '.')) or len(set(value)) < 8:
        return False
    if re.fullmatch(r'[a-z]*(?:[A-Z][a-z]+)+|[A-Z0-9_]+|[a-z0-9_\-]*[a-z]{5,}[a-z0-9_\-]*', value) and not re.search(r'\d.*\d.*\d', value):
        return False  # camelCaseWords, UPPER_ENUM, or wordy-lowercase without several digits
    classes = sum(bool(re.search(p, value)) for p in (r'[a-z]', r'[A-Z]', r'\d'))
    return classes >= 2


PLATFORM_PLACEHOLDERS = re.compile(r'^(?:shopify|wix|squarespace|webflow|wordpress|magento|bigcommerce|vtex|example|localhost)\.(?:local|test|example)$')


def _looks_internal(host: str, own_domain: str) -> bool:
    if PLATFORM_PLACEHOLDERS.match(host):
        return False  # placeholders inside platform code, not real hosts
    if host.endswith(INTERNAL_TLDS):
        return True
    if own_domain and registrable_domain(host) != own_domain:
        return False
    labels = host.split('.')[:-2] if own_domain else host.split('.')[:-1]
    parts = {part for label in labels for part in label.split('-')} | set(labels)
    return bool(parts & INTERNAL_HOST_LABELS)


def merge_signals(signals: list[dict]) -> list[dict]:
    """Deduplicate signals by type and value. Repeats raise the score a little."""
    merged: dict[tuple[str, str], dict] = {}
    for signal in signals:
        key = (signal['type'], signal['value'].lower())
        if key not in merged:
            merged[key] = {**signal, 'sources': [signal['source']]}
            continue
        existing = merged[key]
        existing['occurrences'] += signal.get('occurrences', 1)
        if signal['source'] not in existing['sources']:
            existing['sources'].append(signal['source'])
        if signal['score'] > existing['score']:
            for field in ('score', 'context', 'key', 'live', 'liveState'):
                if field in signal:
                    existing[field] = signal[field]
    result = []
    for signal in merged.values():
        signal['score'] = _clip(signal['score'] + min(5, signal['occurrences'] - 1) + min(6, 3 * (len(signal['sources']) - 1)))
        result.append(signal)
    # A flag seen as both camelCase and snake_case is one clue; keep the stronger copy
    result.sort(key=lambda s: (-s['score'], s['type'], s['value']))
    return result


# --------------------------------------------------------------------------------------------
# Command line: python -m my_actor.extractor file.js [--domain groww.in]
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Print the signals and exposures found in local JavaScript or JSON files."""
    parser = argparse.ArgumentParser(description='Find hidden features and leaks in JavaScript bundles.')
    parser.add_argument('files', nargs='+', type=Path, help='JavaScript (.js) or flag-config (.json) files')
    parser.add_argument('--domain', default='', help='The site domain, for example groww.in, to tell first-party from third-party hosts')
    parser.add_argument('--top', type=int, default=40, help='How many signals to print')
    parser.add_argument('--min-score', type=int, default=0, help='Hide signals below this score')
    parser.add_argument('--json', action='store_true', help='Print JSON instead of a table')
    args = parser.parse_args(argv)

    signals: list[dict] = []
    exposures: list[dict] = []
    for path in args.files:
        text = path.read_text(encoding='utf-8', errors='replace')
        if path.suffix == '.json':
            signals += extract_flag_config(text, path.name)
        else:
            signals += extract_signals(text, path.name, args.domain)
        exposures += extract_exposures(text, path.name, args.domain)
    signals = [s for s in merge_signals(signals) if s['score'] >= args.min_score][: args.top]

    if args.json:
        json.dump({'signals': signals, 'exposures': exposures}, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write('\n')
        return 0
    print(f'{"score":>5}  {"type":<20} value')
    for s in signals:
        print(f'{s["score"]:>5}  {s["type"]:<20} {s["value"][:90]}')
    if exposures:
        print('\nExposures:')
        for e in exposures:
            print(f'  [{e["severity"]}] {e["type"]:<14} {e["value"][:90]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
