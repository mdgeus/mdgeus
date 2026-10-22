# Lightspeed C-Series scanner

Vindt (Nederlandse) webshops en stelt vast of ze op **Lightspeed eCom C-Series** (voorheen SEOshop) draaien, met een score van 0 tot 100 en het bewijs per shop.

## Installatie

```bash
cd lightspeed-scanner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Gebruik

```bash
# 1. Kandidaten ontdekken (crt.sh + Common Crawl), gefilterd op .nl
python -m lightspeed_scanner discover

# 1b. En/of een eigen lijst toevoegen (CSV/TXT, eerste kolom = domein of URL)
python -m lightspeed_scanner import mijn_lijst.csv

# 2. Alle kandidaten checken (herstartbaar: al gecheckte domeinen worden overgeslagen)
python -m lightspeed_scanner check --concurrency 10

# 3. Exporteren (';'-gescheiden, opent direct goed in NL-Excel)
python -m lightspeed_scanner export -o lightspeed.csv --only-lightspeed
```

Je kunt ook direct een bestand checken: `python -m lightspeed_scanner check lijst.csv`. Alles komt in `results.db` (SQLite), dus je kunt de resultaten ook met SQL bevragen:

```sql
SELECT c.domain, c.source, r.score, r.shop_id
FROM candidates c JOIN results r USING (domain)
WHERE r.is_lightspeed = 1 ORDER BY r.score DESC;
```

## Hoe de detectie werkt

| Signaal | Punten |
|---|---|
| Assets van `cdn/static/assets.webshopapp.com` in de HTML | 40 |
| `?format=json` geeft een `shop`-object met `id` (levert ook `shop_id`) | 40 |
| De pagina eindigt op `*.webshopapp.com` | 40 |
| Rain-template-comments (`[START] 'blocks/head.rain'`) | 30 |
| DNS-CNAME naar `*.webshopapp.com` | 30 |
| "Powered by Lightspeed/SEOshop" | 10 |

De score is maximaal 100. Vanaf 50 (`--threshold`) geldt een shop als Lightspeed. De `?format=json`-check wordt alleen gedaan als de homepage al een signaal gaf, zodat het per domein bij 2–3 requests blijft. Tussen requests zit een pauze en robots.txt wordt gerespecteerd (`--ignore-robots` om dat uit te zetten).

**Discovery:** elke C-Series-shop heeft een subdomein `<shop>.webshopapp.com` dat doorverwijst naar het eigen domein. De tool haalt die subdomeinen uit certificaatlogs (crt.sh) en de Common Crawl-index, volgt de redirect en houdt de `.nl`-domeinen over (`--tld ""` voor alle TLD's). Een shop zonder zo'n subdomein in die bronnen vind je zo niet. Vul aan met `import`.

## Kalibreren

De signalen en gewichten zijn startwaarden en nog niet getest op live shops. Draai `check` eerst op een handvol bekende Lightspeed-shops en een paar Shopify/WooCommerce-shops, kijk naar de kolom `evidence` en pas zo nodig `WEIGHTS` / `DEFAULT_THRESHOLD` aan in `lightspeed_scanner/fingerprints.py`.

## Tests

```bash
python -m pytest -q
```

Gebruik dit verantwoord: alleen publieke pagina's, geen persoonsgegevens (AVG).
