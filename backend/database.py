"""SQLite database for persistent session storage."""

import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "data", "tracker.db")
)


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            teacher_name TEXT NOT NULL,
            meet_url TEXT NOT NULL,
            email_template TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            email TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS visits (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            token TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            ip TEXT,
            city TEXT,
            country TEXT,
            region TEXT,
            device TEXT,
            os TEXT,
            browser TEXT,
            user_agent TEXT,
            referrer TEXT,
            referrer_app TEXT,
            is_crawler INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_invites_session ON invites(session_id);
        CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);
        CREATE INDEX IF NOT EXISTS idx_visits_session ON visits(session_id);
        CREATE INDEX IF NOT EXISTS idx_visits_token ON visits(token);
    """)
    conn.commit()
    conn.close()


# ---------- Session CRUD ----------


def create_session(
    teacher_name: str, meet_url: str, email_template: str, emails: list[str]
) -> dict:
    import secrets

    session_id = secrets.token_urlsafe(16)
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, teacher_name, meet_url, email_template, created_at) VALUES (?,?,?,?,?)",
        (session_id, teacher_name, meet_url, email_template, created_at),
    )
    invites = []
    for email in emails:
        email = email.strip().lower()
        if not email or "@" not in email:
            continue
        token = secrets.token_urlsafe(12)
        conn.execute(
            "INSERT INTO invites (session_id, email, token) VALUES (?,?,?)",
            (session_id, email, token),
        )
        invites.append({"email": email, "token": token})
    conn.commit()
    conn.close()
    return {
        "id": session_id,
        "teacher_name": teacher_name,
        "meet_url": meet_url,
        "email_template": email_template,
        "invites": invites,
        "created_at": created_at,
    }


def get_session(session_id: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return None
    invites = [
        dict(r)
        for r in conn.execute(
            "SELECT email, token FROM invites WHERE session_id = ?", (session_id,)
        ).fetchall()
    ]
    visits = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM visits WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    ]
    # Convert is_crawler to bool
    for v in visits:
        v["is_crawler"] = bool(v["is_crawler"])
    conn.close()
    return {
        "id": row["id"],
        "teacher_name": row["teacher_name"],
        "meet_url": row["meet_url"],
        "email_template": row["email_template"],
        "created_at": row["created_at"],
        "invites": invites,
        "visits": visits,
    }


def list_sessions() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM invites WHERE session_id = s.id) as student_count, "
        "(SELECT COUNT(*) FROM visits WHERE session_id = s.id) as visit_count "
        "FROM sessions s ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "teacher_name": r["teacher_name"],
                "meet_url": r["meet_url"],
                "created_at": r["created_at"],
                "student_count": r["student_count"],
                "visit_count": r["visit_count"],
            }
        )
    conn.close()
    return result


def delete_session(session_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def add_visit(session_id: str, visit: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO visits (id, session_id, token, timestamp, ip, city, country, region,
           device, os, browser, user_agent, referrer, referrer_app, is_crawler)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            visit["id"],
            session_id,
            visit["token"],
            visit["timestamp"],
            visit["ip"],
            visit["city"],
            visit["country"],
            visit["region"],
            visit["device"],
            visit["os"],
            visit["browser"],
            visit["user_agent"],
            visit["referrer"],
            visit["referrer_app"],
            1 if visit["is_crawler"] else 0,
        ),
    )
    conn.commit()
    conn.close()


def find_session_by_token(token: str) -> Optional[tuple[str, dict]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT session_id FROM invites WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    session_id = row["session_id"]
    conn.close()
    session = get_session(session_id)
    if session:
        return session_id, session
    return None


def get_invites(session_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT email, token FROM invites WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Initialize DB on import
init_db()
