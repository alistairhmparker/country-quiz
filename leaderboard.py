# leaderboard.py
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import re
_WS_RE = re.compile(r"\s+")

# Postgres (Neon)
DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None  # allows local SQLite without psycopg installed

# SQLite fallback (local dev)
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "leaderboard.db"


# =========================
# Models
# =========================

@dataclass(frozen=True)
class LeaderboardEntry:
    name: str
    score: int
    played_at: str  # ISO string


# =========================
# Connection helpers
# =========================

def _use_postgres() -> bool:
    return bool(DATABASE_URL and psycopg is not None)


def _connect_sqlite() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_postgres():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# =========================
# Init DB
# =========================

def init_db() -> None:
    if _use_postgres():
        with _connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    name TEXT NOT NULL,
                    name_key TEXT PRIMARY KEY,
                    score INTEGER NOT NULL,
                    played_at TEXT NOT NULL
                )
                    """
                )
            conn.commit()
    else:
        with _connect_sqlite() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    name TEXT NOT NULL,
                    name_key TEXT PRIMARY KEY,
                    score INTEGER NOT NULL,
                    played_at TEXT NOT NULL
                )
                """
            )
            conn.commit()


# =========================
# Record score
# =========================

def record_score(name: str, score: int) -> bool:
    """
    Record a score for a name.

    Returns True if leaderboard updated (insert or improved score).

    Rule: only replace existing score if new score is higher.
    """

    init_db()

    name = _clean_name(name)
    if not name:
        return False

    name_key = name.casefold()
    score_i = int(score)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # -------- Postgres path --------
    if _use_postgres():
        with _connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leaderboard (name, name_key, score, played_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name_key)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        score = EXCLUDED.score,
                        played_at = EXCLUDED.played_at
                    WHERE EXCLUDED.score > leaderboard.score
                    """,
                    (name, name_key, score_i, now_iso)
                )
                changed = cur.rowcount == 1
            conn.commit()
            return changed

    # -------- SQLite fallback --------
    with _connect_sqlite() as conn:
        row = conn.execute(
            "SELECT score FROM leaderboard WHERE name_key = ?",
            (name_key,),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO leaderboard (name, name_key, score, played_at) VALUES (?, ?, ?, ?)",
                (name, name_key, score_i, now_iso),
            )
            conn.commit()
            return True

        old_score = int(row["score"])
        if score_i > old_score:
            conn.execute(
                "UPDATE leaderboard SET score = ?, played_at = ? WHERE name_key = ?",
                (score_i, now_iso, name_key),
            )
            conn.commit()
            return True

        return False


# =========================
# Read leaderboard
# =========================

def get_top_entries(limit: int = 20) -> List[LeaderboardEntry]:
    init_db()

    # -------- Postgres --------
    if _use_postgres():
        with _connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, score, played_at
                    FROM leaderboard
                    ORDER BY score DESC, played_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
                rows = cur.fetchall()

        return [
            LeaderboardEntry(
                name=r["name"],
                score=int(r["score"]),
                played_at=r["played_at"],
            )
            for r in rows
        ]

    # -------- SQLite fallback --------
    with _connect_sqlite() as conn:
        rows = conn.execute(
            """
            SELECT name, score, played_at
            FROM leaderboard
            ORDER BY score DESC, played_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        LeaderboardEntry(
            name=r["name"],
            score=int(r["score"]),
            played_at=r["played_at"],
        )
        for r in rows
    ]


# =========================
# Formatting helper (unchanged)
# =========================


def _clean_name(name: str) -> str:
    """Strip ends and collapse internal whitespace to single spaces."""
    return _WS_RE.sub(" ", (name or "").strip())

def _name_key(name: str) -> str:
    """Case-insensitive key based on cleaned name."""
    return _clean_name(name).casefold()


def format_played_at(iso_str: str) -> str:
    """
    Convert ISO UTC time string -> friendly display.
    Example: 2026-02-23T00:40:12+00:00 -> 23 Feb 2026
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%d %b %Y")
    except Exception:
        return iso_str