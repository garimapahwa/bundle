"""Overexposed fields: data an API sends to the browser that the page never shows.

For every JSON response a page loads, each leaf field is compared with what the page renders
(visible text and attribute values). A field the UI never shows was sent for no reason: it is
"overexposed". If it looks like personal data (PAN, Aadhaar, phone, email, date of birth,
account number, internal ID, risk score), it is high severity.

Values are used only for the comparison. They are never returned, stored, or logged: a finding
holds the field path, the kind of data, and the endpoint, nothing else.

This module is pure Python, so it can be tested without a browser.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_LEAVES_PER_RESPONSE = 4000
GRAPHQL_PLUMBING = {'__typename', 'extensions', 'cursor', 'pageInfo'}

# Personal data, recognized by the field name ...
PII_KEYS = (
    ('pan', re.compile(r'(?:^|_|\b)pan(?:_?(?:no|number|card))?$|pancard', re.IGNORECASE)),
    ('aadhaar', re.compile(r'aadh?aa?r|(?:^|_)uid(?:ai)?(?:_?no)?$', re.IGNORECASE)),
    ('phone', re.compile(r'^(?:phone|mobile|msisdn|whatsapp)(?:_?(?:no|num|number))?$|(?:phone|mobile)_?(?:no|num|number)$|contact_?(?:no|number)', re.IGNORECASE)),
    ('email', re.compile(r'e-?mail', re.IGNORECASE)),
    ('date_of_birth', re.compile(r'(?:^|_)dob$|date_?of_?birth|birth_?date|birthday', re.IGNORECASE)),
    ('account_number', re.compile(r'acc(?:oun)?t_?(?:no|num|number)|bank_?account|iban|ifsc|upi_?id|vpa|card_?(?:no|number)', re.IGNORECASE)),
    ('risk_score', re.compile(r'risk|fraud|credit_?score|cibil|kyc_?(?:status|level)|aml', re.IGNORECASE)),
    ('internal_id', re.compile(r'(?:user|customer|client|account|member|internal|employee|agent|lead)_?id$|uuid|guid', re.IGNORECASE)),
    ('address', re.compile(r'(?:^|_)(?:address|addr|pincode|zip_?code|postal)(?:_|$)', re.IGNORECASE)),
    ('name', re.compile(r'(?:full|first|last|father|mother|nominee)_?name', re.IGNORECASE)),
)
# ... or by the shape of the value
PII_VALUES = (
    ('pan', re.compile(r'^[A-Z]{5}\d{4}[A-Z]$')),
    ('aadhaar', re.compile(r'^\d{4}[ -]?\d{4}[ -]?\d{4}$')),
    ('phone', re.compile(r'^(?:\+?91[ -]?)?[6-9]\d{9}$')),
    ('email', re.compile(r'^[\w.+-]+@[\w-]+\.[\w.-]+$')),
)
PII_LABELS = {
    'pan': 'PAN number',
    'aadhaar': 'Aadhaar number',
    'phone': 'phone number',
    'email': 'email address',
    'date_of_birth': 'date of birth',
    'account_number': 'bank or card account number',
    'risk_score': 'risk or KYC score',
    'internal_id': 'internal user or customer ID',
    'address': 'postal address',
    'name': 'personal name',
}
# Personal data so sensitive that it is flagged even when the comparison is inconclusive
STRICT_PII = {'pan', 'aadhaar', 'phone', 'email', 'date_of_birth', 'account_number'}
DATE_LIKE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?$|^\d{10,13}$')
ASSET_LIKE = re.compile(r'\.(?:png|jpe?g|gif|svg|webp|avif|ico|mp4|webm|pdf)(?:\?|$)', re.IGNORECASE)


@dataclass
class Leaf:
    """One scalar value in a JSON response, with a normalized path such as data.items[].pan."""

    path: str
    key: str
    value: object


def flatten(node: object, path: str = '') -> list[Leaf]:
    """All scalar leaves of a JSON document. Array indices become [] so repeated items merge."""
    leaves: list[Leaf] = []
    stack: list[tuple[object, str, str]] = [(node, path, '')]
    while stack and len(leaves) < MAX_LEAVES_PER_RESPONSE:
        current, current_path, key = stack.pop()
        if isinstance(current, dict):
            as_map = _is_data_map(current)
            for k, v in current.items():
                if k in GRAPHQL_PLUMBING:
                    continue  # protocol metadata present in every response, not data
                segment = '{}' if as_map else str(k)
                child = f'{current_path}{segment}' if as_map else (f'{current_path}.{k}' if current_path else str(k))
                stack.append((v, child, key if as_map else str(k)))
        elif isinstance(current, list):
            for item in current[:200]:
                stack.append((item, f'{current_path}[]', key))
        else:
            leaves.append(Leaf(current_path, key, current))
    return leaves


def _is_data_map(node: dict) -> bool:
    """True for objects keyed by data (symbols, IDs, dates) rather than by field names.

    `{"NIFTY": {...}, "SENSEX": {...}, ...}` is one field repeated, not dozens of fields.
    """
    values = list(node.values())
    if len(node) >= 3 and all(isinstance(v, dict) and v for v in values):
        shared = set.intersection(*(set(v) for v in values))
        if len(shared) >= 0.6 * max(len(v) for v in values):
            return True  # several objects with the same shape: one entry per record
    if len(node) < 4:
        return False
    if sum(isinstance(v, dict | list) for v in values) >= 0.8 * len(values):
        return True
    data_like = sum(1 for k in node if re.fullmatch(r'[A-Z0-9_&.\- ]{2,}|\d+|[0-9a-f-]{8,}|\d{4}-\d{2}-\d{2}.*', str(k)))
    return data_like >= 0.8 * len(node)


# Responses that are not data APIs: static files, animations, analytics and logging beacons
NOT_AN_API = re.compile(
    r'/(?:_next/static|static|assets|media|fonts|lottie|animations?)/|\.lottie|'
    r'(?:^|[/.-])(?:pixel|beacon|collect|track(?:ing)?|events?|webevents[\w-]*|log(?:s|ging)?|metrics|telemetry|analytics|rum)(?:[/.?-]|$)',
    re.IGNORECASE,
)


def is_data_api(url: str) -> bool:
    """True for responses worth auditing: real data APIs, not static files or analytics beacons."""
    parts = urlsplit(url)
    return not NOT_AN_API.search(f'{parts.netloc}{parts.path}')


def normalize_text(text: str) -> str:
    """Lowercase, single-spaced text, for matching values against the page."""
    return re.sub(r'\s+', ' ', text).lower()


def _number_forms(number: float) -> set[str]:
    """The ways a page might print a number: 1234.5, 1,234.50, 12,34,567 (Indian grouping)."""
    forms = {str(number)}
    if float(number).is_integer():
        integer = int(number)
        forms |= {str(integer), f'{integer:,}', _indian(integer)}
    else:
        forms |= {f'{number:.2f}', f'{number:.1f}', f'{number:,.2f}', f'{round(number)}'}
        whole, _, frac = f'{number:.2f}'.partition('.')
        forms.add(f'{_indian(int(whole))}.{frac}')
    return forms


def _indian(integer: int) -> str:
    """12345678 -> 1,23,45,678."""
    sign, digits = ('-', str(-integer)) if integer < 0 else ('', str(integer))
    if len(digits) <= 3:
        return sign + digits
    head, tail = digits[:-3], digits[-3:]
    groups = [head[max(0, i - 2) : i] for i in range(len(head), 0, -2)][::-1]
    return sign + ','.join([*groups, tail])


def is_rendered(value: object, page_text: str) -> bool | None:
    """True if the page shows this value, False if not, None if it cannot be judged fairly."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if abs(value) < 100 and float(value).is_integer():
            return None  # small numbers (counts, flags, enums) appear everywhere or nowhere
        return any(form.lower() in page_text for form in _number_forms(value))
    text = str(value).strip()
    if re.search(r'<[a-zA-Z][^>]*>', text):
        return None  # HTML markup (for example Shopify section blocks) is never shown as raw text
    if len(text) < 4 or DATE_LIKE.match(text):
        return None  # too short to match, or a date the page formats its own way
    lowered = normalize_text(text)
    if lowered in page_text:
        return True
    if len(lowered) > 60:
        return lowered[:40] in page_text
    if ASSET_LIKE.search(text) or text.startswith(('http://', 'https://', '/')):
        return urlsplit(text).path.lower() in page_text
    return False


# A field named like personal data only counts if its value could be that data:
# `mobile_aspect_ratio: "16:9"` is layout, not a phone number.
PLAUSIBLE_VALUE = {
    'pan': re.compile(r'^[A-Za-z0-9*Xx]{10}$'),
    'aadhaar': re.compile(r'^[\dXx*]{4}[ -]?[\dXx*]{4}[ -]?[\dXx*]{4}$'),
    'phone': re.compile(r'^\+?(?:\d[ ()-]?){10,13}$|^\+?\d{2,4}[Xx*]{4,8}\d{2,4}$'),
    'email': re.compile(r'@'),
    'date_of_birth': re.compile(r'\d'),
    'account_number': re.compile(r'^[\dXx* -]{8,24}$|^[A-Za-z]{4}0[A-Za-z0-9]{6}$|@'),
    'risk_score': re.compile(r'^-?\d+(?:\.\d+)?$|^[A-Za-z_ -]{2,20}$'),
    'internal_id': re.compile(r'^[\w-]{4,64}$'),
    'address': re.compile(r'[A-Za-z].*\d|\d.*[A-Za-z]|^\d{6}$'),
    'name': re.compile(r'^[A-Za-z][A-Za-z .\'-]{1,60}$'),
}


def pii_kind(key: str, value: object) -> str | None:
    """The kind of personal data a field holds, judged from its value, or its name plus a plausible value."""
    if value is None or isinstance(value, bool | dict | list):
        return None
    text = str(value).strip()
    if not text:
        return None
    for kind, pattern in PII_VALUES:
        if pattern.match(text):
            return kind
    if re.fullmatch(r'\d+\s*[xX×]\s*\d+', text):
        return None  # a size such as 320x50, never personal data
    leaf = re.split(r'[.\[\]{}]+', key.strip('.[]{}'))[-1] if key else ''
    for kind, pattern in PII_KEYS:
        if pattern.search(leaf) and PLAUSIBLE_VALUE[kind].search(text):
            return kind
    return None


def endpoint_label(url: str) -> str:
    """The endpoint without its query string, with numeric and long IDs replaced: /api/user/{id}.

    GraphQL-style calls keep their operation name: api.example.com/api (getUserProfile).
    """
    parts = urlsplit(url)
    operation = parts.fragment if parts.fragment and not re.fullmatch(r'[0-9a-f]{10}', parts.fragment) else ''
    if operation:
        return f'{endpoint_label(url.split("#")[0])} ({operation})'
    path = re.sub(r'/(?:\d+|[0-9a-f]{16,}|[0-9a-f-]{36})(?=/|$)', '/{id}', parts.path, flags=re.IGNORECASE)
    return f'{parts.netloc}{path}'


def overexposed_fields(api_responses: dict[str, dict], dom_text: dict[str, str]) -> tuple[list[dict], dict]:
    """Compare every API response with the pages and return overexposed fields (no values).

    Returns the findings and the counts used for scoring and benchmarking.
    """
    all_text = normalize_text('\n'.join(dom_text.values()))
    findings: dict[tuple[str, str], dict] = {}
    checked = 0
    for url, response in api_responses.items():
        if not is_data_api(url):
            continue
        try:
            data = json.loads(response.get('body') or '')
        except ValueError:
            continue
        page_text = normalize_text(dom_text.get(response.get('page', ''), '')) or all_text
        endpoint = endpoint_label(url)
        for leaf in flatten(data):
            rendered = is_rendered(leaf.value, page_text)
            if rendered is False and page_text is not all_text:
                rendered = is_rendered(leaf.value, all_text)  # shown on another page counts as shown
            kind = pii_kind(leaf.key, leaf.value)
            if rendered is None:
                if kind not in STRICT_PII:
                    continue  # cannot be judged fairly, and not personal data
                rendered = normalize_text(str(leaf.value)) in all_text  # strict PII: only an exact match clears it
            checked += 1
            if rendered:
                continue
            key = (endpoint, leaf.path)
            if key in findings:
                findings[key]['occurrences'] += 1
                continue
            findings[key] = {
                'endpoint': endpoint,
                'field': leaf.path,
                'pii': kind,
                'piiLabel': PII_LABELS.get(kind or '', ''),
                'severity': 'high' if kind else 'low',
                'occurrences': 1,
                'page': response.get('page', ''),
            }
    items = sorted(findings.values(), key=lambda f: (f['severity'] != 'high', f['endpoint'], f['field']))
    stats = {
        'apiResponses': sum(1 for u in api_responses if is_data_api(u)),
        'fieldsChecked': checked,
        'overexposedFields': len(items),
        'piiFields': sum(1 for f in items if f['pii']),
    }
    return items, stats
