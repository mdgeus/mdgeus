from lightspeed_scanner.check import normalize_domain
from lightspeed_scanner.discover import parse_crtsh, shop_subdomains


def test_shop_subdomains_filters_infra_and_wildcards():
    hosts = ["mijnshop.webshopapp.com", "*.webshopapp.com", "cdn.webshopapp.com",
             "MijnShop.webshopapp.com.", "a.b.webshopapp.com", "voorbeeld.nl"]
    assert shop_subdomains(hosts) == {"mijnshop.webshopapp.com"}


def test_parse_crtsh_multiline_name_value():
    entries = [{"common_name": "shop1.webshopapp.com",
                "name_value": "shop1.webshopapp.com\nshop2.webshopapp.com"}]
    assert parse_crtsh(entries) == {"shop1.webshopapp.com", "shop2.webshopapp.com"}


def test_normalize_domain():
    assert normalize_domain("https://www.Voorbeeld.nl/pad?x=1") == "voorbeeld.nl"
    assert normalize_domain("voorbeeld.nl") == "voorbeeld.nl"
    assert normalize_domain("domain") is None
    assert normalize_domain("# commentaar") is None
