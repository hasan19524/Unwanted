"""Email sending via Resend HTTPS API - multi-threaded."""

import os
import concurrent.futures
import httpx
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
MAX_EMAIL_THREADS = 10


def send_single_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str = None,
    display_name: str = None,
) -> tuple[str, bool, str]:
    """Send a single email via Resend API. Returns (email, success, error_message)."""
    if not RESEND_API_KEY:
        return to, False, "RESEND_API_KEY not configured"

    from_field = EMAIL_FROM
    if display_name:
        from_field = f"{display_name} <{EMAIL_FROM}>"

    payload = {
        "from": from_field,
        "to": [to],
        "subject": subject,
        "text": body_text,
    }
    if body_html:
        payload["html"] = body_html

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code == 200:
            return to, True, ""
        else:
            return to, False, f"Resend API error {resp.status_code}: {resp.text[:200]}"
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
