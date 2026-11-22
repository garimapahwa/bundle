"""Tests for the overexposed-field check. Run from bundle/: python -m pytest -q tests"""

from __future__ import annotations

import json

from my_actor.exposure import endpoint_label, is_rendered, normalize_text, overexposed_fields, pii_kind

PAGE = 'https://shop.example.in/account'
DOM = normalize_text('Hello Priya Sharma\nPortfolio value ₹12,34,567.50\nPlan: Gold\nSupport: help@example.in')

RESPONSE = {
    'data': {
        'displayName': 'Priya Sharma',
        'portfolioValue': 1234567.5,
        'plan': 'Gold',
        'pan': 'ABCDE1234F',
        'mobile': '9876543210',
        'email': 'priya.sharma@gmail.com',
        'dob': '1990-04-12',
        'riskScore': 742,
        'customerId': 'CUST-88812345',
        'internalNotes': 'escalated twice',
        'isActive': True,
        'count': 3,
        'orders': [{'orderId': 'ORD-1', 'status': 'Delivered'}, {'orderId': 'ORD-2', 'status': 'Delivered'}],
    },
    'support': 'help@example.in',
}


def run() -> tuple[list[dict], dict]:
    responses = {'https://api.example.in/v1/user/12345?token=abc': {'page': PAGE, 'body': json.dumps(RESPONSE)}}
    return overexposed_fields(responses, {PAGE: DOM})


def test_rendered_fields_are_not_flagged() -> None:
    fields = {f['field'] for f in run()[0]}
    assert 'data.displayName' not in fields
    assert 'data.portfolioValue' not in fields  # printed with Indian grouping
    assert 'data.plan' not in fields
    assert 'support' not in fields  # an email the page shows on purpose


def test_hidden_pii_is_high_severity() -> None:
    by_field = {f['field']: f for f in run()[0]}
    for field, kind in [
        ('data.pan', 'pan'),
        ('data.mobile', 'phone'),
        ('data.email', 'email'),
        ('data.dob', 'date_of_birth'),
        ('data.riskScore', 'risk_score'),
        ('data.customerId', 'internal_id'),
    ]:
        assert by_field[field]['pii'] == kind, field
        assert by_field[field]['severity'] == 'high'


def test_hidden_non_pii_is_low_and_noise_is_skipped() -> None:
    by_field = {f['field']: f for f in run()[0]}
    assert by_field['data.internalNotes']['severity'] == 'low'
    assert 'data.isActive' not in by_field  # booleans cannot be judged
    assert 'data.count' not in by_field  # small numbers cannot be judged
    assert by_field['data.orders[].orderId']['occurrences'] == 2  # array items merge


def test_values_never_leave_the_check() -> None:
    blob = json.dumps(run())
    for secret in ('ABCDE1234F', '9876543210', 'priya.sharma@gmail.com', '1990-04-12', 'CUST-88812345', 'token=abc'):
        assert secret not in blob


def test_helpers() -> None:
    assert endpoint_label('https://api.example.in/v1/user/12345/orders?x=1') == 'api.example.in/v1/user/{id}/orders'
    assert pii_kind('contact', 'ABCDE1234F') == 'pan'
    assert pii_kind('aadhaarNo', 'XXXX XXXX 1234') == 'aadhaar'
    assert pii_kind('title', 'Hello') is None
    assert is_rendered(True, DOM) is None
    assert is_rendered('Priya Sharma', DOM) is True


def test_data_keyed_maps_collapse_and_beacons_are_skipped() -> None:
    market = {'indexMap': {s: {'close': 100.5 + i, 'yearHigh': 999.25 + i} for i, s in enumerate(['NIFTY', 'SENSEX', 'BANKNIFTY', 'FINNIFTY', 'NIFTYIT'])}}
    responses = {
        'https://api.example.in/v1/indices': {'page': PAGE, 'body': json.dumps(market)},
        'https://pixel.example.in/webevents-batch': {'page': PAGE, 'body': json.dumps({'status': 'accepted-123'})},
        'https://example.in/_next/static/media/city.json': {'page': PAGE, 'body': json.dumps({'nm': 'layer-one'})},
    }
    items, stats = overexposed_fields(responses, {PAGE: DOM})
    assert {i['field'] for i in items} == {'indexMap{}.close', 'indexMap{}.yearHigh'}
    assert stats['apiResponses'] == 1


def test_layout_fields_named_mobile_are_not_phone_numbers() -> None:
    assert pii_kind('mobile_aspect_ratio', '16:9') is None
    assert pii_kind('mobile', '320x50') is None
    assert pii_kind('image_label_mobile', 'Shop now') is None
    assert pii_kind('mobile', '9876543210') == 'phone'
    assert pii_kind('mobileNumber', '+91 98765 43210') == 'phone'


def test_sizes_are_not_phone_numbers() -> None:
    assert pii_kind('mobile', '320 x 50') is None
    assert pii_kind('mobile', '1080x1920') is None
    assert pii_kind('mobile', '98XXXXXX10') == 'phone'


def test_html_blocks_are_not_judged() -> None:
    assert is_rendered('<div class="section"><p>Shop now</p></div>', DOM) is None
