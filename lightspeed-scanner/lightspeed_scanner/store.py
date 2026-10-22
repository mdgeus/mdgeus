"""SQLite-opslag, zodat runs herstartbaar zijn en resultaten met SQL te bevragen."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    domain      TEXT PRIMARY KEY,
    source      TEXT,
    found_via   TEXT,
    added_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS results (
    domain        TEXT PRIMARY KEY,
    final_url     TEXT,
    is_lightspeed INTEGER,
    score         INTEGER,
    evidence      TEXT,
    shop_id       TEXT,
    http_status   INTEGER,
    error         TEXT,
    checked_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

RESULT_COLUMNS = [
    "domain", "final_url", "is_lightspeed", "score", "evidence",
    "shop_id", "http_status", "error", "checked_at",
]


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def add_candidates(con: sqlite3.Connection, rows: list[tuple[str, str, str]]) -> int:
    """rows: (domain, source, found_via). Retourneert het aantal nieuwe domeinen."""
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO candidates (domain, source, found_via) VALUES (?, ?, ?)",
        rows,
    )
    con.commit()
    return con.total_changes - before


def checked_domains(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT domain FROM results WHERE error IS NULL")}


def save_result(con: sqlite3.Connection, row: dict) -> None:
    con.execute(
        """INSERT OR REPLACE INTO results
           (domain, final_url, is_lightspeed, score, evidence, shop_id, http_status, error)
           VALUES (:domain, :final_url, :is_lightspeed, :score, :evidence, :shop_id,
                   :http_status, :error)""",
        row,
    )
    con.commit()


def export_csv(con: sqlite3.Connection, path: str | Path, only_lightspeed: bool) -> int:
    sql = f"SELECT {', '.join(RESULT_COLUMNS)} FROM results"
    if only_lightspeed:
        sql += " WHERE is_lightspeed = 1"
    sql += " ORDER BY score DESC, domain"
    rows = con.execute(sql).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")  # ';' opent direct goed in NL-Excel
        w.writerow(RESULT_COLUMNS)
        w.writerows(rows)
    return len(rows)
