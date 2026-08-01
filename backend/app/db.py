"""SQLite persistence for users, subscriptions, and summary usage."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from .settings import DATABASE_PATH

_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    global _initialized
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                stripe_customer_id TEXT
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                stripe_subscription_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                current_period_end REAL NOT NULL DEFAULT 0,
                cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                UNIQUE(user_id)
            );

            CREATE TABLE IF NOT EXISTS stripe_events (
                event_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                processed_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS summary_usage (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            );

            CREATE INDEX IF NOT EXISTS idx_users_stripe_customer
                ON users(stripe_customer_id);
            """
        )
    _initialized = True


def create_user(email: str, password_hash: str) -> Dict[str, Any]:
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, now),
        )
        user_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_stripe_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?",
            (customer_id,),
        ).fetchone()
        return dict(row) if row else None


def set_stripe_customer_id(user_id: int, customer_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
            (customer_id, user_id),
        )


def get_subscription_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def upsert_subscription(
    user_id: int,
    stripe_subscription_id: str,
    status: str,
    current_period_end: float,
    cancel_at_period_end: bool,
) -> None:
    now = time.time()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE subscriptions
                SET stripe_subscription_id = ?, status = ?, current_period_end = ?,
                    cancel_at_period_end = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    stripe_subscription_id,
                    status,
                    current_period_end,
                    1 if cancel_at_period_end else 0,
                    now,
                    user_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO subscriptions (
                    user_id, stripe_subscription_id, status,
                    current_period_end, cancel_at_period_end, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    stripe_subscription_id,
                    status,
                    current_period_end,
                    1 if cancel_at_period_end else 0,
                    now,
                ),
            )


def mark_subscription_status(stripe_subscription_id: str, status: str) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET status = ?, updated_at = ?
            WHERE stripe_subscription_id = ?
            """,
            (status, now, stripe_subscription_id),
        )


def try_claim_stripe_event(event_id: str, event_type: str) -> bool:
    """Return True if this event should be processed (first time)."""
    now = time.time()
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO stripe_events (event_id, type, processed_at) VALUES (?, ?, ?)",
                (event_id, event_type, now),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_user_summary_count(user_id: int, day: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM summary_usage WHERE user_id = ? AND day = ?",
            (user_id, day),
        ).fetchone()
        return int(row["count"]) if row else 0


def set_user_summary_count(user_id: int, day: str, count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO summary_usage (user_id, day, count) VALUES (?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET count = excluded.count
            """,
            (user_id, day, count),
        )


def remaining_user_summaries(user_id: int, daily_limit: int) -> int:
    today = time.strftime("%Y-%m-%d")
    count = get_user_summary_count(user_id, today)
    return max(0, daily_limit - count)
