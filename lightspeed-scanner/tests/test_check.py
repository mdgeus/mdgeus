import asyncio

import httpx

from lightspeed_scanner import check
from tests.test_fingerprints import LIGHTSPEED_HTML, SHOPIFY_HTML

PAGES = {"lightspeed.nl": LIGHTSPEED_HTML, "shopify.nl": SHOPIFY_HTML}


def handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "blocked.nl" and request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /")
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    if request.url.params.get("format") == "json":
        if host == "lightspeed.nl":
            return httpx.Response(200, json={"shop": {"id": 777}})
        return httpx.Response(404)
    if host in PAGES:
        return httpx.Response(200, text=PAGES[host], headers={"content-type": "text/html"})
    raise httpx.ConnectError("unreachable", request=request)


def run(domain, monkeypatch):
    async def no_dns(_):
        return []

    monkeypatch.setattr(check, "dns_targets", no_dns)
    monkeypatch.setattr(check, "PER_HOST_DELAY", 0)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await check.check_domain(c, domain)

    return asyncio.run(go())


def test_lightspeed_detected_with_shop_id(monkeypatch):
    row = run("lightspeed.nl", monkeypatch)
    assert row["is_lightspeed"] == 1 and row["score"] == 100 and row["shop_id"] == "777"


def test_non_lightspeed(monkeypatch):
    row = run("shopify.nl", monkeypatch)
    assert row["is_lightspeed"] == 0 and row["score"] == 0 and row["error"] is None


def test_robots_disallow_respected(monkeypatch):
    assert run("blocked.nl", monkeypatch)["error"] == "robots.txt disallow"


def test_unreachable_records_error(monkeypatch):
    assert "ConnectError" in run("offline.nl", monkeypatch)["error"]
