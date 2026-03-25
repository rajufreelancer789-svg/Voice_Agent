from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from os import getenv
from pathlib import Path
from typing import Generator


def _db_file_from_env() -> Path:
    database_url = getenv("DATABASE_URL", "sqlite:///./loan_recovery.db")
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite DATABASE_URL is supported in this project")

    raw_path = database_url.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db_conn() -> Generator[sqlite3.Connection, None, None]:
    db_path = _db_file_from_env()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone_number TEXT NOT NULL UNIQUE,
                preferred_language TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                loan_number TEXT NOT NULL UNIQUE,
                loan_amount REAL NOT NULL,
                emi_amount REAL NOT NULL,
                emi_status TEXT NOT NULL,
                due_date TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                room_name TEXT,
                dispatch_id TEXT,
                sip_participant_id TEXT,
                status TEXT NOT NULL,
                provider_code TEXT,
                provider_message TEXT,
                promised_payment_date TEXT,
                transcript_summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(loan_id) REFERENCES loans(id)
            );
            """
        )


def seed_sample_data() -> None:
    with db_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM customers").fetchone()["count"]
        if count > 0:
            return

        created_at = now_utc_iso()
        updated_at = created_at

        customers = [
            ("Ravi", "+917416608494", "te", created_at),
            ("Suresh", "+919900000001", "en", created_at),
            ("Anita", "+919900000002", "hi", created_at),
        ]

        conn.executemany(
            "INSERT INTO customers(name, phone_number, preferred_language, created_at) VALUES(?, ?, ?, ?)",
            customers,
        )

        customer_rows = conn.execute("SELECT id, name FROM customers ORDER BY id").fetchall()
        customer_map = {row["name"]: row["id"] for row in customer_rows}

        loans = [
            (customer_map["Ravi"], "LN-2026-001", 120000.0, 4500.0, "pending", "2026-03-28", updated_at),
            (customer_map["Suresh"], "LN-2026-002", 98000.0, 3900.0, "paid", "2026-03-20", updated_at),
            (customer_map["Anita"], "LN-2026-003", 150000.0, 5200.0, "pending", "2026-03-27", updated_at),
        ]

        conn.executemany(
            """
            INSERT INTO loans(customer_id, loan_number, loan_amount, emi_amount, emi_status, due_date, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            loans,
        )
