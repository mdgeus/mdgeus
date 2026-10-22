"""Command line: discover -> check -> export."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys

from . import store
from .check import check_many, normalize_domain
from .discover import discover
from .fingerprints import DEFAULT_THRESHOLD


def read_domains(path: str) -> list[str]:
    """Eerste kolom van een CSV/TXT (',' of ';'), header-regel wordt vanzelf weggefilterd."""
    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        domains = [normalize_domain(row[0]) for row in csv.reader(f, delimiter=delim) if row]
    return list(dict.fromkeys(d for d in domains if d))


def cmd_discover(args, con) -> None:
    rows = asyncio.run(
        discover(args.sources.split(","), tld=args.tld or None,
                 concurrency=args.concurrency, cc_pages=args.cc_pages)
    )
    new = store.add_candidates(con, rows)
    print(f"{len(rows)} kandidaten gevonden, {new} nieuw opgeslagen.")


def cmd_import(args, con) -> None:
    domains = read_domains(args.file)
    new = store.add_candidates(con, [(d, "import", args.file) for d in domains])
    print(f"{len(domains)} domeinen gelezen, {new} nieuw opgeslagen.")


def cmd_check(args, con) -> None:
    if args.file:
        domains = read_domains(args.file)
    else:
        domains = [r[0] for r in con.execute("SELECT domain FROM candidates ORDER BY domain")]
    if not args.recheck:
        done = store.checked_domains(con)
        domains = [d for d in domains if d not in done]
    print(f"{len(domains)} domeinen te checken...", file=sys.stderr)

    hits = 0

    def on_result(row: dict) -> None:
        nonlocal hits
        store.save_result(con, row)
        hits += row["is_lightspeed"]
        mark = "LIGHTSPEED" if row["is_lightspeed"] else (row["error"] or "-")
        print(f"{row['score']:>3}  {row['domain']:<40} {mark}")

    asyncio.run(
        check_many(domains, on_result, concurrency=args.concurrency,
                   threshold=args.threshold, respect_robots=not args.ignore_robots)
    )
    print(f"Klaar: {hits} van {len(domains)} op Lightspeed C-Series.", file=sys.stderr)


def cmd_export(args, con) -> None:
    n = store.export_csv(con, args.output, only_lightspeed=args.only_lightspeed)
    print(f"{n} rijen geschreven naar {args.output}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lightspeed_scanner", description=__doc__)
    p.add_argument("--db", default="results.db", help="SQLite-bestand (default: results.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="kandidaten zoeken via crt.sh / Common Crawl")
    d.add_argument("--sources", default="crtsh,commoncrawl")
    d.add_argument("--tld", default="nl", help="filter op TLD; leeg = alles")
    d.add_argument("--cc-pages", type=int, default=5, help="max Common Crawl-indexpagina's")
    d.add_argument("--concurrency", type=int, default=10)
    d.set_defaults(func=cmd_discover)

    i = sub.add_parser("import", help="eigen lijst met domeinen toevoegen aan kandidaten")
    i.add_argument("file")
    i.set_defaults(func=cmd_import)

    c = sub.add_parser("check", help="domeinen checken (bestand, of anders alle kandidaten)")
    c.add_argument("file", nargs="?")
    c.add_argument("--concurrency", type=int, default=10)
    c.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    c.add_argument("--recheck", action="store_true", help="ook al gecheckte domeinen")
    c.add_argument("--ignore-robots", action="store_true")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("export", help="resultaten naar CSV (';'-gescheiden)")
    e.add_argument("-o", "--output", default="results.csv")
    e.add_argument("--only-lightspeed", action="store_true")
    e.set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    con = store.connect(args.db)
    try:
        args.func(args, con)
    finally:
        con.close()
    return 0
