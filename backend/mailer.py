"""Email sending via Gmail SMTP with app password - multi-threaded."""

import smtplib
import os
import concurrent.futures
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_DISPLAY_NAME = os.getenv("SMTP_DISPLAY_NAME", "Teacher")

# Max parallel email threads - Gmail recommends keeping this modest
MAX_EMAIL_THREADS = 10


def send_single_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str = None,
    display_name: str = None,
) -> tuple[str, bool, str]:
    """Send a single email. Returns (email, success, error_message)."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return (
            to,
            False,
            "SMTP not configured. Set SMTP_EMAIL and SMTP_PASSWORD in .env",
        )

    name = display_name or SMTP_DISPLAY_NAME
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{name} <{SMTP_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg["Reply-To"] = SMTP_EMAIL

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to, msg.as_string())

        return to, True, ""
    except Exception as e:
        return to, False, str(e)


def send_bulk(
    emails: list[dict],
    template: str,
    meet_url: str,
    base_url: str,
    display_name: str = None,
) -> dict:
    """Send emails to a list of recipients using multiple threads.
    Each dict has 'email' and 'token'. Returns summary dict."""
    results = {"sent": 0, "failed": 0, "errors": []}

    # Prepare all email tasks
    tasks = []
    for item in emails:
        email = item["email"]
        token = item["token"]
        link = f"{base_url}/go/{token}"

        # Replace {{LINK}} placeholder
        if "{{LINK}}" in template:
            body = template.replace("{{LINK}}", link)
        else:
            body = template + "\n\n" + link

        # Build HTML version
        html_body = body.replace("\n", "<br>")
        html_body = html_body.replace(link, f'<a href="{link}">{link}</a>')

        tasks.append((email, body, html_body))

    # Send emails in parallel using thread pool
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(MAX_EMAIL_THREADS, len(tasks))
    ) as executor:
        futures = {
            executor.submit(
                send_single_email,
                to=email,
                subject="Class Link",
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
