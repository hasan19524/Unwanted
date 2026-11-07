"""FastAPI backend for the class link tracker - secured and cleaned."""

import os
import re
import uuid
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

import database as db
from mailer import send_bulk
from tracker import parse_user_agent, is_crawler, detect_referrer_app, geo_lookup

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
DB_PATH = os.getenv("DB_PATH", "./data/tracker.db")


def validate_config():
    """Validate required configuration on startup. Never prints secrets."""
    errors = []

    required = {
        "APP_BASE_URL": APP_BASE_URL,
        "CORS_ORIGINS": CORS_ORIGINS,
        "ADMIN_KEY": ADMIN_KEY,
        "RESEND_API_KEY": RESEND_API_KEY,
        "EMAIL_FROM": EMAIL_FROM,
    }
    for name, value in required.items():
        if not value:
            errors.append(f"Missing required environment variable: {name}")

    if APP_BASE_URL and not APP_BASE_URL.startswith(("http://", "https://")):
        errors.append("APP_BASE_URL must start with http:// or https://")

    if errors:
        raise RuntimeError("Configuration validation failed:\n" + "\n".join(errors))


# Validate configuration at import time
validate_config()

app = FastAPI(title="Class Link Tracker", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


# ---------- Security Middleware ----------


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    now = time.time()
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(429, "Too many requests. Please try again later.")
    rate_limit_store[client_ip].append(now)

    # Security headers
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ---------- Dependency ----------


def verify_admin_key(request: Request):
    """Verify admin key for destructive operations."""
    if not ADMIN_KEY:
        return True
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key")
    if key != ADMIN_KEY:
        raise HTTPException(403, "Invalid or missing admin key")
    return True


# ---------- Models ----------


class StartSessionRequest(BaseModel):
    teacher_name: str
    meet_url: str
    email_template: str
    subject: str
    emails: list[str]


# ---------- Helpers ----------

rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW = 60

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "0.0.0.0"


def validate_session_id(session_id: str) -> None:
    if not session_id or not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(400, "Invalid session ID format")


def validate_meet_url(url: str) -> None:
    if not url.startswith(("https://meet.google.com/", "http://meet.google.com/")):
        raise HTTPException(400, "Meet URL must be a valid Google Meet link")


def validate_email_list(emails: list[str]) -> list[str]:
    clean = []
    email_regex = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    for e in emails:
        e = e.strip().lower()
        if e and email_regex.match(e):
            clean.append(e)
    return clean


def compute_sharers(session: dict) -> list:
    """Compute list of students whose links show multiple device/IP patterns.

    Does NOT assume the first visitor is the owner. Excludes crawler visits
    from sharing calculations. Flags tokens with visits from multiple
    (ip, device) combinations as potentially shared — but does not claim
    that IP/device differences prove someone's identity.
    """
    invites_map = {inv["token"]: inv["email"] for inv in session["invites"]}
    by_token: dict = {}

    for v in session["visits"]:
        # Exclude crawlers from sharing calculations
        if bool(v.get("is_crawler", False)):
            continue
        by_token.setdefault(v["token"], []).append(v)

    sharers = []
    for token, visits in by_token.items():
        # Group by (ip, device) combo
        combos: dict = {}
        for v in visits:
            combo_key = (v["ip"], v["device"])
            combos.setdefault(combo_key, []).append(v)

        if len(combos) <= 1:
            continue

        # Multiple combos detected — potential additional visitors
        all_combo_keys = list(combos.keys())
        additional_visits = []
        for combo_key in all_combo_keys[1:]:
            additional_visits.extend(combos[combo_key])

        if additional_visits:
            sharers.append(
                {
                    "student_email": invites_map.get(token, "Unknown"),
                    "token": token,
                    "outsider_count": len(additional_visits),
                    "unique_combos": len(all_combo_keys),
                    "outsiders": [
                        {
                            "ip": v["ip"],
                            "city": v["city"],
                            "country": v["country"],
                            "device": v["device"],
                            "os": v["os"],
                            "referrer_app": v["referrer_app"],
                            "time": v["timestamp"],
                            "is_crawler": bool(v.get("is_crawler", False)),
                        }
                        for v in additional_visits
                    ],
                }
            )

    return sharers


# ---------- Routes ----------


@app.get("/health")
async def health_root():
    """Lightweight health endpoint for Cloudflare keep-alive pings."""
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/sessions")
async def list_sessions():
    """List all sessions for the sidebar history."""
    sessions = db.list_sessions()
    return {"sessions": sessions}


@app.post("/api/session/start")
async def start_session(request: Request, req: StartSessionRequest):
    verify_admin_key(request)

    if not req.teacher_name or not req.teacher_name.strip():
        raise HTTPException(400, "Teacher name is required")
    if len(req.teacher_name) > 100:
        raise HTTPException(400, "Teacher name too long")

    if not req.meet_url or not req.meet_url.strip():
        raise HTTPException(400, "Meet URL is required")
    validate_meet_url(req.meet_url.strip())

    if not req.emails:
        raise HTTPException(400, "At least one student email is required")
    if len(req.emails) > 200:
        raise HTTPException(400, "Too many emails (max 200)")

    clean_emails = validate_email_list(req.emails)
    if not clean_emails:
        raise HTTPException(400, "No valid emails found")

    if "{{LINK}}" not in (req.email_template or ""):
        raise HTTPException(400, "Email template must contain {{LINK}} placeholder")
    if not req.subject or not req.subject.strip():
        raise HTTPException(400, "Email subject is required")

    session = db.create_session(
        teacher_name=req.teacher_name.strip(),
        meet_url=req.meet_url.strip(),
        email_template=req.email_template or "Join class here: {{LINK}}",
        emails=clean_emails,
    )

    base_url = APP_BASE_URL.rstrip("/")
    send_results = send_bulk(
        emails=session["invites"],
        template=session["email_template"],
        meet_url=session["meet_url"],
        base_url=base_url,
        display_name=req.teacher_name.strip(),
        subject=req.subject.strip(),
    )

    dashboard_url = f"{base_url}/dashboard?session={session['id']}"

    return {
        "session_id": session["id"],
        "dashboard_url": dashboard_url,
        "sent": send_results["sent"],
        "failed": send_results["failed"],
        "errors": send_results["errors"],
        "student_count": len(session["invites"]),
    }


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    validate_session_id(session_id)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    sharers = compute_sharers(session)
    return {
        "session_id": session["id"],
        "teacher_name": session["teacher_name"],
        "meet_url": session["meet_url"],
        "email_template": session["email_template"],
        "created_at": session["created_at"],
        "student_count": len(session["invites"]),
        "visit_count": len(session["visits"]),
        "sharers": sharers,
    }


@app.get("/api/session/{session_id}/visits")
async def get_visits(session_id: str):
    validate_session_id(session_id)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    invites_map = {inv["token"]: inv["email"] for inv in session["invites"]}
    visits = []
    for v in session["visits"]:
        visits.append(
            {
                "id": v["id"],
                "token": v["token"],
                "student_email": invites_map.get(v["token"], "Unknown"),
                "timestamp": v["timestamp"],
                "ip": v["ip"],
                "city": v["city"],
                "country": v["country"],
                "device": v["device"],
                "os": v["os"],
                "browser": v["browser"],
                "referrer_app": v["referrer_app"],
                "is_crawler": bool(v["is_crawler"]),
            }
        )
    sharers = compute_sharers(session)
    return {"visits": visits, "sharers": sharers, "total": len(visits)}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str, request: Request):
    verify_admin_key(request)
    validate_session_id(session_id)
    success = db.delete_session(session_id)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "deleted", "message": "Session and all data removed"}


@app.get("/go/{token}")
async def track_and_redirect(token: str, request: Request):
    if not token or not TOKEN_PATTERN.match(token):
        raise HTTPException(404, "Invalid link token")
    result = db.find_session_by_token(token)
    if not result:
        raise HTTPException(404, "Link not found or expired")
    session_id, session = result

    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "") or request.headers.get("referrer", "")
    geo = await geo_lookup(ip)
    ua_info = parse_user_agent(ua)
    crawler = is_crawler(ua)
    ref_app = detect_referrer_app(referrer, ua)

    visit = {
        "id": uuid.uuid4().hex[:12],
        "token": token,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip": ip,
        "city": geo["city"],
        "country": geo["country"],
        "region": geo["region"],
        "user_agent": ua,
        "device": ua_info["device"],
        "os": ua_info["os"],
        "browser": ua_info["browser"],
        "referrer": referrer,
        "referrer_app": ref_app,
        "is_crawler": crawler,
    }

    db.add_visit(session_id, visit)

    meet_url = session["meet_url"]
    return RedirectResponse(url=meet_url, status_code=302)


@app.post("/api/upload-emails")
async def upload_emails(file: UploadFile = File(...)):
    filename = file.filename.lower()
    content = await file.read()
    emails = []

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10MB)")

    if filename.endswith(".csv"):
        import csv, io

        text = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            for cell in row:
                cell = cell.strip()
                if "@" in cell:
                    emails.append(cell.lower())

    elif filename.endswith((".xlsx", ".xls")):
        import openpyxl, io

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str) and "@" in cell.value:
                        emails.append(cell.value.strip().lower())

    else:
        raise HTTPException(400, "Unsupported file type. Use CSV or Excel.")

    emails = list(dict.fromkeys(emails))[:200]
    return {"emails": emails, "count": len(emails)}


# ---------- Serve frontend ----------

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(404, "Frontend not built")
