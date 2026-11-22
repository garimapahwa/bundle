"""Tests for the pure extractor. Run from bundle/: python -m pytest -q tests"""

from __future__ import annotations

from pathlib import Path

import pytest

from my_actor.extractor import (
    extract_exposures,
    extract_flag_config,
    extract_signals,
    is_css_module_name,
    is_third_party_script,
    mask_secret,
    registrable_domain,
)

FIXTURES = Path(__file__).parent / 'fixtures'
GROWW_CHUNK = FIXTURES / 'groww_chunk.js'

CSS_MODULE_EXAMPLES = ['styles_card__aB3x9', 'name_part__aB3x9', 'css-1x2y3z4', 'sc-bdVaJa']


def values(signals: list[dict], kind: str | None = None) -> set[str]:
    return {s['value'] for s in signals if kind is None or s['type'] == kind}


@pytest.fixture(scope='module')
def sample() -> list[dict]:
    text = (FIXTURES / 'sample_chunk.js').read_text()
    return extract_signals(text, 'sample_chunk.js', 'groww.in')


def test_finds_growthbook_style_flags(sample: list[dict]) -> None:
    flags = values(sample, 'feature_flag')
    assert {'groww_api_enabled', 'inr_wallet_re_arch_enabled', 'mtf_pledge_enabled'} <= flags
    assert {'isUSSEnabled', 'isGoldEnabled'} <= flags


def test_drops_generic_and_library_words(sample: list[dict]) -> None:
    everything = values(sample)
    for noise in ('enabled', 'toggle_switch', 'TOGGLE_SWITCH', 'isDebugEnabled', 'FETCH_USER_SUCCESS'):
        assert noise not in everything


def test_never_returns_css_module_names(sample: list[dict]) -> None:
    everything = values(sample)
    for name in CSS_MODULE_EXAMPLES:
        assert name not in everything
        assert is_css_module_name(name)


def test_finds_endpoints_partners_routes(sample: list[dict]) -> None:
    assert '/v1/api/apex/oauth2/v1/consent/page' in values(sample, 'api_endpoint')
    partners = values(sample, 'partner_integration')
    assert {'quantman.in', 'algotest.xyz'} <= partners
    assert 'googletagmanager.com' not in partners
    routes = values(sample, 'hidden_route')
    assert '/stocks/us-stocks/waitlist' in routes
    assert not any(r.startswith(('/_next', '/static')) for r in routes)


def test_finds_native_bridge_commands(sample: list[dict]) -> None:
    native = values(sample, 'native_capability')
    assert {'GET_INSTALLED_APPS', 'IS_INAPP_UPI_ENABLED', 'QUIZ_PROGRESS_UPDATE'} <= native


def test_product_signals_outrank_noise(sample: list[dict]) -> None:
    score = {s['value']: s['score'] for s in sample}
    assert score['inr_wallet_re_arch_enabled'] > score['/login']
    assert score['groww_api_enabled'] > score['en-IN']
    assert all(0 <= s['score'] <= 100 for s in sample)


def test_signals_are_deduplicated() -> None:
    text = 'a.isUSSEnabled;b.isUSSEnabled;c={isUSSEnabled:1}'
    signals = extract_signals(text, 'x.js')
    assert [s['value'] for s in signals].count('isUSSEnabled') == 1
    assert signals[0]['occurrences'] == 3


def test_exposures_are_masked() -> None:
    text = (FIXTURES / 'sample_chunk.js').read_text()
    exposures = extract_exposures(text, 'sample_chunk.js', 'groww.in')
    kinds = {e['type'] for e in exposures}
    assert {'secret_like', 'internal_host', 'source_map'} <= kinds
    assert 'api-staging.groww.in' in {e['value'] for e in exposures}
    blob = repr(exposures) + repr(extract_signals(text, 'sample_chunk.js', 'groww.in'))
    assert 'AKIAIOSFODNN7EXAMPLE' not in blob
    assert 'AIzaSyA-1234567890abcdefghijklmnopqrstuv' not in blob
    assert mask_secret('AKIAIOSFODNN7EXAMPLE').startswith('AKIA')


def test_flag_config_json() -> None:
    growthbook = '{"status":200,"features":{"us-stocks-v2":{"defaultValue":true},"gold_sip_enabled":{"defaultValue":false}}}'
    assert {'us-stocks-v2', 'gold_sip_enabled'} <= values(extract_flag_config(growthbook, 'gb.json'))
    launchdarkly = '{"credit-line-beta":{"value":true,"variation":0,"version":3}}'
    assert 'credit-line-beta' in values(extract_flag_config(launchdarkly, 'ld.json'))
    assert extract_flag_config('not json', 'x.json') == []


def test_helpers() -> None:
    assert registrable_domain('assets-netstorage.groww.in') == 'groww.in'
    assert registrable_domain('www.flipkart.co.in') == 'flipkart.co.in'
    assert is_third_party_script('https://js-agent.newrelic.com/nr-spa.min.js', 'swiggy.com')
    assert not is_third_party_script('https://assets.groww.in/_next/static/chunks/1.js', 'groww.in')


@pytest.mark.skipif(not GROWW_CHUNK.exists(), reason='add tests/fixtures/groww_chunk.js to run the real-bundle test')
def test_real_groww_chunk() -> None:
    signals = extract_signals(GROWW_CHUNK.read_text(encoding='utf-8', errors='replace'), 'groww_chunk.js', 'groww.in')
    everything = {v.lower() for v in values(signals)}
    for expected in ('isUSSEnabled', 'isGoldEnabled', 'groww_api_enabled', 'inr_wallet_re_arch_enabled'):
        assert expected.lower() in everything, expected
    assert any('/oauth2/v1/consent/page' in v for v in values(signals, 'api_endpoint'))
    partners = values(signals, 'partner_integration')
    assert {'quantman.in', 'algotest.xyz'} <= partners
    assert not [v for v in values(signals) if is_css_module_name(v)]


def test_platform_and_public_keys_are_not_secrets() -> None:
    from my_actor.extractor import is_platform_file

    text = (
        'e={STOREFRONT_ACCESS_TOKEN:"storefrontAccessToken"};'
        'fetch(u,{headers:{"Bugsnag-Api-Key":"bcbc1234ab56cd78ef90ab12cd34ef56"}});'
        'n=new URL("https://shopify.local/");'
        'k={apiKey:"9f8e7d6c5b4a39281706f5e4d3c2b1a0"}'
    )
    exposures = extract_exposures(text, 'x.js', 'mamaearth.in')
    secrets = {e['value']: e for e in exposures if e['type'] == 'secret_like'}
    assert not any(v.startswith('stor') for v in secrets)  # a variable name, not a value
    assert secrets[mask_secret('bcbc1234ab56cd78ef90ab12cd34ef56')]['severity'] == 'low'
    assert secrets[mask_secret('9f8e7d6c5b4a39281706f5e4d3c2b1a0')]['severity'] == 'medium'
    assert not any(e['type'] == 'internal_host' for e in exposures)
    assert is_platform_file('https://mamaearth.in/cdn/shopifycloud/storefront/assets/storefront/webmcp-f2c7e115.js')
    assert not is_platform_file('https://mamaearth.in/cdn/shop/t/148/assets/custom.js')


def test_keys_in_page_config_are_client_keys() -> None:
    exposures = extract_exposures('{"api_key":"ak_7f3e9c2b1a8d4e6f5c3b2a1908d7e6f5"}', 'window.nector', 'mamaearth.in')
    assert exposures[0]['severity'] == 'low'
    assert exposures[0]['secret_kind'] == 'public_client_key'
    real = extract_exposures('{"k":"AKIAIOSFODNN7EXAMPLE"}', 'window.cfg', 'mamaearth.in')
    assert real[0]['severity'] == 'high'
