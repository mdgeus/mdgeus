"""Signaaldefinities en scoring voor Lightspeed eCom C-Series.

Alle functies hier zijn puur (geen netwerk), zodat ze met fixtures te testen zijn.
Gewichten zijn startwaarden: kalibreer ze met `check` op een set bekende shops.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

DEFAULT_THRESHOLD = 50

# Assets van C-Series-shops komen van het Lightspeed-CDN (voorheen SEOshop).
RE_WEBSHOPAPP_ASSET = re.compile(
    r"(?:https?:)?//(?:cdn|static|assets)\.webshopapp\.com/", re.I
)
# Templates zijn geschreven in Lightspeeds "Rain"-taal; de render laat
# HTML-comments achter zoals: <!-- [START] 'blocks/head.rain' -->
RE_RAIN_TEMPLATE = re.compile(r"\[(?:START|END)\]\s*'[^']+\.rain'", re.I)
RE_POWERED_BY = re.compile(
    r"powered\s+by\s*(?:<[^>]+>\s*)*(?:lightspeed|seoshop)", re.I
)

WEIGHTS = {
    "webshopapp_assets": 40,
    "rain_template": 30,
    "format_json": 40,
    "webshopapp_host": 40,
    "dns_webshopapp": 30,
    "powered_by": 10,
}


@dataclass
class Result:
    score: int = 0
    evidence: list[str] = field(default_factory=list)
    shop_id: str | None = None

    def add(self, signal: str, detail: str) -> None:
        self.score = min(100, self.score + WEIGHTS[signal])
        self.evidence.append(f"{signal}: {detail}")


def html_signals(html: str) -> list[tuple[str, str]]:
    """Signalen uit de HTML van een pagina."""
    found = []
    m = RE_WEBSHOPAPP_ASSET.search(html)
    if m:
        found.append(("webshopapp_assets", m.group(0)))
    m = RE_RAIN_TEMPLATE.search(html)
    if m:
        found.append(("rain_template", m.group(0)))
    m = RE_POWERED_BY.search(html)
    if m:
        found.append(("powered_by", re.sub(r"<[^>]+>", "", m.group(0)).strip()))
    return found


def parse_format_json(data: object) -> tuple[bool, str | None]:
    """C-Series geeft bij `?format=json` de template-variabelen als JSON terug.

    Herkenbaar aan een top-level `shop`-object met daarin een `id`.
    Retourneert (is_lightspeed, shop_id).
    """
    if not isinstance(data, dict):
        return False, None
    shop = data.get("shop")
    if isinstance(shop, dict) and "id" in shop:
        return True, str(shop["id"])
    return False, None


def is_webshopapp_host(url_or_host: str) -> bool:
    host = urlparse(url_or_host).hostname if "//" in url_or_host else url_or_host
    host = (host or "").lower().rstrip(".")
    return host == "webshopapp.com" or host.endswith(".webshopapp.com")


def score(
    html: str = "",
    final_url: str = "",
    json_data: object = None,
    dns_targets: list[str] | None = None,
) -> Result:
    """Combineer alle signalen tot één score (0-100) plus bewijs."""
    r = Result()
    for signal, detail in html_signals(html):
        r.add(signal, detail)
    if final_url and is_webshopapp_host(final_url):
        r.add("webshopapp_host", final_url)
    ok, shop_id = parse_format_json(json_data)
    if ok:
        r.shop_id = shop_id
        r.add("format_json", f"shop.id={shop_id}")
    for target in dns_targets or []:
        if is_webshopapp_host(target):
            r.add("dns_webshopapp", target)
            break
    return r
