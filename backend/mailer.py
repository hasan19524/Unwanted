"""Email sending via Gmail SMTP with app password."""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_DISPLAY_NAME = os.getenv("SMTP_DISPLAY_NAME", "Teacher")


def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str = None,
    display_name: str = None,
) -> tuple[bool, str]:
    """Send an email. Returns (success, error_message)."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False, "SMTP not configured. Set SMTP_EMAIL and SMTP_PASSWORD in .env"

    name = display_name or SMTP_DISPLAY_NAME
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{name} <{SMTP_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        # Reply-To is the same sender for now; can be customized
        msg["Reply-To"] = SMTP_EMAIL

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to, msg.as_string())

        return True, ""
    except Exception as e:
        return False, str(e)


def send_bulk(
    emails: list[dict],
    template: str,
    meet_url: str,
    base_url: str,
    display_name: str = None,
) -> dict:
    """Send emails to a list of recipients. Each dict has 'email' and 'token'.
    Returns summary dict."""
    results = {"sent": 0, "failed": 0, "errors": []}

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
        # Make link clickable in HTML
        html_body = html_body.replace(link, f'<a href="{link}">{link}</a>')

        success, error = send_email(
            to=email,
            subject="Class Link",
            body_text=body,
            body_html=html_body,
            display_name=display_name,
        )

        if success:
            results["sent"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(f"{email}: {error}")

    return results
