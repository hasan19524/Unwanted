"""Email sending via Brevo API - multi-threaded. Free tier: 300 emails/day."""

import os
import httpx
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Teacher")
MAX_EMAIL_THREADS = 10


def send_single_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str = None,
    display_name: str = None,
) -> tuple[str, bool, str]:
    """Send a single email via Brevo API. Returns (email, success, error_message)."""
    if not BREVO_API_KEY:
        return to, False, "BREVO_API_KEY not configured"

    sender_email = BREVO_SENDER_EMAIL
    sender_name = display_name or BREVO_SENDER_NAME

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body_text,
    }
    if body_html:
        payload["htmlContent"] = body_html

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": BREVO_API_KEY,
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                json=payload,
            )
        if resp.status_code in (200, 201):
            return to, True, ""
        else:
            return to, False, f"Brevo API error {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return to, False, str(e)


def send_bulk(
    emails: list[dict],
    template: str,
    meet_url: str,
    base_url: str,
    display_name: str = None,
    subject: str = "Class Link",
) -> dict:
    """Send emails to a list of recipients using multiple threads.
    Each dict has 'email' and 'token'. Returns summary dict."""
    results = {"sent": 0, "failed": 0, "errors": []}

    tasks = []
    for item in emails:
        email = item["email"]
        token = item["token"]
        link = f"{base_url}/go/{token}"

        if "{{LINK}}" in template:
            body = template.replace("{{LINK}}", link)
        else:
            body = template + "\n\n" + link

        html_body = body.replace("\n", "<br>")
        html_body = html_body.replace(link, f'<a href="{link}">{link}</a>')

        tasks.append((email, body, html_body))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(MAX_EMAIL_THREADS, len(tasks))
    ) as executor:
        futures = {
            executor.submit(
                send_single_email,
                to=email,
                subject=subject,
                body_text=body,
                body_html=html_body,
                display_name=display_name,
            ): email
            for email, body, html_body in tasks
        }

        for future in concurrent.futures.as_completed(futures):
            email, success, error = future.result()
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{email}: {error}")

    return results
