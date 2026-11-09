"""PostgreSQL database for persistent session storage (free via Neon/Supabase)."""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    teacher_name TEXT NOT NULL,
                    meet_url TEXT NOT NULL,
                    email_template TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invites (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
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
                    is_crawler INTEGER DEFAULT 0
                )
            """)
            # Add user_email column if missing (for existing databases)
            cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_email TEXT")
            cur.execute("UPDATE sessions SET user_email = '' WHERE user_email IS NULL")
            cur.execute("ALTER TABLE sessions ALTER COLUMN user_email SET NOT NULL")
            # Remove the legacy teacher_email column from the abandoned
            # teacher-login design: it is NOT NULL but no longer written,
            # so every INSERT fails with NotNullViolation.
            cur.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS teacher_email")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_email ON sessions(user_email)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_invites_session ON invites(session_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_visits_session ON visits(session_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_token ON visits(token)")
        conn.commit()
    finally:
        conn.close()


# Initialize DB on import
init_db()


# ---------- Users ----------


def create_user(email: str, password_hash: str) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (%s,%s,%s) RETURNING id",
                (email, password_hash, created_at),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"id": row[0], "email": email}


def get_user(email: str) -> Optional[dict]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return dict(row)


# ---------- Session CRUD ----------


def create_session(
    teacher_name: str,
    user_email: str,
    meet_url: str,
    email_template: str,
    emails: list[str],
) -> dict:
    import secrets

    session_id = secrets.token_urlsafe(16)
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, teacher_name, user_email, meet_url, email_template, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    session_id,
                    teacher_name,
                    user_email,
                    meet_url,
                    email_template,
                    created_at,
                ),
            )
            invites = []
            for email in emails:
                email = email.strip().lower()
                if not email or "@" not in email:
                    continue
                token = secrets.token_urlsafe(12)
                cur.execute(
                    "INSERT INTO invites (session_id, email, token) VALUES (%s,%s,%s)",
                    (session_id, email, token),
                )
                invites.append({"email": email, "token": token})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "id": session_id,
        "teacher_name": teacher_name,
        "user_email": user_email,
        "meet_url": meet_url,
        "email_template": email_template,
        "invites": invites,
        "created_at": created_at,
    }


def get_session(session_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "SELECT email, token FROM invites WHERE session_id = %s", (session_id,)
            )
            invites = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT * FROM visits WHERE session_id = %s ORDER BY timestamp",
                (session_id,),
            )
            visits = [dict(r) for r in cur.fetchall()]
            for v in visits:
                v["is_crawler"] = bool(v["is_crawler"])
    finally:
        conn.close()
    return {
        "id": row["id"],
        "teacher_name": row["teacher_name"],
        "user_email": row["user_email"],
        "meet_url": row["meet_url"],
        "email_template": row["email_template"],
        "created_at": row["created_at"],
        "invites": invites,
        "visits": visits,
    }


def list_sessions(user_email: str) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT s.*, "
                "(SELECT COUNT(*) FROM invites WHERE session_id = s.id) as student_count, "
                "(SELECT COUNT(*) FROM visits WHERE session_id = s.id) as visit_count "
                "FROM sessions s WHERE s.user_email = %s ORDER BY created_at DESC",
                (user_email,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
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
    return result


def delete_session(session_id: str) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return deleted


def add_visit(session_id: str, visit: dict):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO visits (id, session_id, token, timestamp, ip, city, country, region,
                   device, os, browser, user_agent, referrer, referrer_app, is_crawler)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_session_by_token(token: str) -> Optional[tuple[str, dict]]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT session_id FROM invites WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return None
            session_id = row["session_id"]
            session = get_session(session_id)
            if session:
                return session_id, session
            return None
    finally:
        conn.close()
