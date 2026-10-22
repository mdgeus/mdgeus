"""Checker: haalt per domein de homepage op en scoort de Lightspeed-signalen."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import dns.asyncresolver
import dns.exception
import httpx

from . import USER_AGENT
from .fingerprints import DEFAULT_THRESHOLD, score

MAX_HTML_CHARS = 2_000_000
PER_HOST_DELAY = 0.5  # seconden tussen requests naar hetzelfde domein


def normalize_domain(raw: str) -> str | None:
    raw = raw.strip().lower()
    if not raw or raw.startswith("#"):
        return None
    if "//" not in raw:
        raw = "//" + raw
    host = (urlparse(raw).hostname or "").rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) else None


async def dns_targets(domain: str) -> list[str]:
    """CNAME-doelen van het domein en www-variant (C-Series wijst vaak naar webshopapp)."""
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 5
    targets = []
    for name in (domain, f"www.{domain}"):
        try:
            answer = await resolver.resolve(name, "CNAME")
            targets += [r.target.to_text().rstrip(".") for r in answer]
        except (dns.exception.DNSException, OSError):
            pass
    return targets


async def robots_allows(client: httpx.AsyncClient, base: str) -> bool:
    try:
        r = await client.get(f"{base}/robots.txt")
    except httpx.HTTPError:
        return True
    if r.status_code >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, f"{base}/")


async def fetch_homepage(client: httpx.AsyncClient, domain: str) -> tuple[httpx.Response, str]:
    last_exc: Exception | None = None
    for base in (f"https://{domain}", f"http://{domain}"):
        try:
            return await client.get(f"{base}/"), base
        except httpx.HTTPError as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]


async def check_domain(
    client: httpx.AsyncClient,
    domain: str,
    threshold: int = DEFAULT_THRESHOLD,
    respect_robots: bool = True,
) -> dict:
    row = {
        "domain": domain, "final_url": None, "is_lightspeed": 0, "score": 0,
        "evidence": "", "shop_id": None, "http_status": None, "error": None,
    }
    dns_task = asyncio.create_task(dns_targets(domain))
    try:
        if respect_robots and not await robots_allows(client, f"https://{domain}"):
            dns_task.cancel()
            row["error"] = "robots.txt disallow"
            return row
        await asyncio.sleep(PER_HOST_DELAY)
        resp, _ = await fetch_homepage(client, domain)
        row["http_status"] = resp.status_code
        row["final_url"] = str(resp.url)
        html = resp.text[:MAX_HTML_CHARS]

        json_data = None
        pre = score(html=html, final_url=row["final_url"])
        if pre.score > 0:
            # Alleen bij een eerste hit: bevestigen en shop-id ophalen via ?format=json
            await asyncio.sleep(PER_HOST_DELAY)
            try:
                jr = await client.get(row["final_url"], params={"format": "json"})
                if "json" in jr.headers.get("content-type", ""):
                    json_data = jr.json()
            except (httpx.HTTPError, json.JSONDecodeError, ValueError):
                pass

        result = score(
            html=html, final_url=row["final_url"], json_data=json_data,
            dns_targets=await dns_task,
        )
        row.update(
            score=result.score,
            is_lightspeed=int(result.score >= threshold),
            evidence=" | ".join(result.evidence),
            shop_id=result.shop_id,
        )
    except httpx.HTTPError as exc:
        dns_task.cancel()
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return row


def make_client(timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9"},
        follow_redirects=True,
        timeout=timeout,
        limits=httpx.Limits(max_connections=50),
    )


async def check_many(domains, on_result, concurrency: int = 10, **kwargs) -> None:
    sem = asyncio.Semaphore(concurrency)
    async with make_client() as client:

        async def worker(d: str) -> None:
            async with sem:
                on_result(await check_domain(client, d, **kwargs))

        await asyncio.gather(*(worker(d) for d in domains))
