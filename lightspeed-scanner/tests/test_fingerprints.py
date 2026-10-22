from lightspeed_scanner.fingerprints import DEFAULT_THRESHOLD, parse_format_json, score

LIGHTSPEED_HTML = """<html><head>
<!-- [START] 'blocks/head.rain' -->
<link rel="stylesheet" href="https://cdn.webshopapp.com/shops/12345/themes/1/assets/style.css">
<!-- [END] 'blocks/head.rain' -->
</head><body><footer>Powered by <a href="https://www.lightspeedhq.nl">Lightspeed</a></footer></body></html>"""

SHOPIFY_HTML = """<html><head><script src="https://cdn.shopify.com/s/files/1/theme.js"></script>
</head><body>Wij verkopen ook Lightspeed kassasystemen.</body></html>"""


def test_lightspeed_html_scores_above_threshold():
    r = score(html=LIGHTSPEED_HTML)
    assert r.score >= DEFAULT_THRESHOLD
    names = {e.split(":")[0] for e in r.evidence}
    assert names == {"webshopapp_assets", "rain_template", "powered_by"}


def test_other_platform_scores_zero():
    r = score(html=SHOPIFY_HTML, final_url="https://voorbeeld.nl/")
    assert r.score == 0 and r.evidence == []


def test_format_json_confirms_and_extracts_shop_id():
    r = score(json_data={"shop": {"id": 12345, "title": "Test"}, "page": {}})
    assert r.shop_id == "12345" and r.score == 40


def test_format_json_rejects_other_json():
    assert parse_format_json({"products": []}) == (False, None)
    assert parse_format_json([1, 2]) == (False, None)
    assert parse_format_json({"shop": "naam"}) == (False, None)


def test_dns_and_host_signals():
    r = score(final_url="https://mijnshop.webshopapp.com/", dns_targets=["shops.webshopapp.com"])
    assert r.score == 70


def test_score_capped_at_100():
    r = score(html=LIGHTSPEED_HTML, json_data={"shop": {"id": 1}},
              dns_targets=["x.webshopapp.com"])
    assert r.score == 100


def test_lookalike_host_not_matched():
    assert score(final_url="https://webshopapp.com.evil.nl/").score == 0
