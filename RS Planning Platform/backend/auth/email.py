"""Password-reset email delivery via SMTP (stdlib smtplib — no new dependency).

Reads SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM from the same
.env the DB connection already loads (Tentative AOP Forecaster/.env — see
db/base.py's load_dotenv call, which every entrypoint that imports db.base
picks up for free). FRONTEND_BASE_URL is the origin the reset link points at
(e.g. https://planning.internal or http://localhost:7800)."""
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:7800")


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def build_reset_link(token: str) -> str:
    return f"{FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"


def send_reset_email(to_email: str, username: str, token: str) -> None:
    """Raises on any SMTP failure — the caller decides how to surface that
    (the route below turns it into a 500 rather than silently pretending the
    email went out)."""
    link = build_reset_link(token)
    body = (
        f"Hi {username},\n\n"
        f"A password reset was requested for your RS Planning Platform account.\n"
        f"Click the link below to set a new password (expires in 30 minutes):\n\n"
        f"{link}\n\n"
        f"If you didn't request this, you can ignore this email.\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = "RS Planning Platform — Password reset"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
