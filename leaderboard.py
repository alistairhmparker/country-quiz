# leaderboard.py
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "leaderboard.db"


@dataclass(frozen=True)
class LeaderboardEntry:
    name: str
    score: int
    played_at: str  # ISO string


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leaderboard (
                name TEXT PRIMARY KEY,
                score INTEGER NOT NULL,
                played_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def record_score(name: str, score: int) -> bool:
    """
    Record a score for a name.
    Returns True if the leaderboard was updated (insert or improved score), else False.
    Rule: only replace existing score if new score is higher.
    If replaced, played_at updates.
    """
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with _connect() as conn:
        row = conn.execute(
            "SELECT score FROM leaderboard WHERE name = ?",
            (name,),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO leaderboard (name, score, played_at) VALUES (?, ?, ?)",
                (name, int(score), now_iso),
            )
            conn.commit()
            return True

        old_score = int(row["score"])
        if int(score) > old_score:
            conn.execute(
                "UPDATE leaderboard SET score = ?, played_at = ? WHERE name = ?",
                (int(score), now_iso, name),
            )
            conn.commit()
            return True

        return False


def get_top_entries(limit: int = 20) -> List[LeaderboardEntry]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT name, score, played_at
            FROM leaderboard
            ORDER BY score DESC, played_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [LeaderboardEntry(name=r["name"], score=int(r["score"]), played_at=r["played_at"]) for r in rows]


def format_played_at(iso_str: str) -> str:
    """
    Convert ISO UTC time string -> friendly display.
    Example: 2026-02-23T00:40:12+00:00 -> 23 Feb 2026, 00:40 UTC
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        # ensure timezone-aware display
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%d %b %Y")
    except Exception:
        return iso_str