"""Discovery: kandidaat-shops vinden via publieke bronnen.

Elke C-Series-shop heeft een subdomein `<shop>.webshopapp.com`, dat doorverwijst
naar het eigen domein van de shop. We verzamelen die subdomeinen uit
Certificate Transparency (crt.sh) en de Common Crawl-index, en volgen daarna de
redirect om het echte (bijv. .nl-)domein te vinden.

Discovery levert kandidaten op; `check` bevestigt ze.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Iterable

import httpx

from .check import make_client, normalize_domain
from .fingerprints import is_webshopapp_host

# Infra-subdomeinen van Lightspeed zelf, geen shops
INFRA_LABELS = {
    "www", "cdn", "static", "assets", "api", "app", "admin", "seoshop", "mail",
    "images", "img", "media", "files", "status", "dev", "test", "staging",
}
RE_SUBDOMAIN = re.compile(r"^([a-z0-9-]+)\.webshopapp\.com$")


def shop_subdomains(hosts: Iterable[str]) -> set[str]:
    """Filter hostnamen tot echte shop-subdomeinen van webshopapp.com."""
    subs = set()
    for host in hosts:
        host = host.strip().lower().lstrip("*.").rstrip(".")
        m = RE_SUBDOMAIN.match(host)
        if m and m.group(1) not in INFRA_LABELS:
            subs.add(host)
    return subs


def parse_crtsh(entries: list[dict]) -> set[str]:
    hosts = []
    for e in entries:
        hosts += str(e.get("name_value", "")).splitlines()
        hosts.append(str(e.get("common_name", "")))
    return shop_subdomains(hosts)


async def from_crtsh(client: httpx.AsyncClient) -> set[str]:
    r = await client.get(
        "https://crt.sh/", params={"q": "%.webshopapp.com", "output": "json"}, timeout=120
    )
    r.raise_for_status()
    return parse_crtsh(r.json())


async def from_commoncrawl(client: httpx.AsyncClient, max_pages: int = 5) -> set[str]:
    info = (await client.get("https://index.commoncrawl.org/collinfo.json")).json()
    api = info[0]["cdx-api"]  # meest recente crawl
    base = {"url": "*.webshopapp.com", "output": "json", "fl": "url", "collapse": "urlkey"}
    pages = (await client.get(api, params={**base, "showNumPages": "true"}, timeout=60)).json()
    hosts: list[str] = []
    for page in range(min(int(pages.get("pages", 1)), max_pages)):
        r = await client.get(api, params={**base, "page": page}, timeout=120)
        if r.status_code != 200:
            break
        for line in r.text.splitlines():
            try:
                url = json.loads(line)["url"]
            except (ValueError, KeyError):
                continue
            hosts.append(httpx.URL(url).host)
    return shop_subdomains(hosts)


async def resolve_custom_domain(client: httpx.AsyncClient, sub: str) -> str | None:
    """Volg de redirect van <shop>.webshopapp.com naar het eigen domein."""
    try:
        r = await client.get(f"https://{sub}/")
    except httpx.HTTPError:
        return None
    host = r.url.host
    if is_webshopapp_host(host):
        return None  # geen eigen domein gekoppeld (of shop offline)
    return normalize_domain(host)


async def discover(
    sources: list[str], tld: str | None = "nl", concurrency: int = 10, cc_pages: int = 5
) -> list[tuple[str, str, str]]:
    """Retourneert rijen (domain, source, found_via) voor de candidates-tabel."""
    async with make_client() as client:
        subs: dict[str, str] = {}
        fetchers = {"crtsh": lambda: from_crtsh(client),
                    "commoncrawl": lambda: from_commoncrawl(client, cc_pages)}
        for name in sources:
            try:
                found = await fetchers[name]()
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                print(f"waarschuwing: bron {name} faalde: {exc}", file=sys.stderr)
                continue
            print(f"{name}: {len(found)} shop-subdomeinen", file=sys.stderr)
            for s in found:
                subs.setdefault(s, name)

        sem = asyncio.Semaphore(concurrency)

        async def resolve(sub: str):
            async with sem:
                return sub, await resolve_custom_domain(client, sub)

        rows = []
        for sub, domain in await asyncio.gather(*(resolve(s) for s in subs)):
            if domain and (tld is None or domain.endswith(f".{tld}")):
                rows.append((domain, subs[sub], sub))
        return rows
