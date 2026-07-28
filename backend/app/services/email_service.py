"""SMTP email delivery (Gmail STARTTLS pattern from hedge-fund notifier)."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def smtp_configured(settings: dict[str, Any]) -> bool:
    host = (settings.get("smtp_host") or "").strip()
    user = (settings.get("smtp_user") or "").strip()
    password = (settings.get("smtp_password") or "").strip()
    return bool(host and user and password)


def check_smtp(settings: dict[str, Any]) -> dict[str, Any]:
    """STARTTLS + login only (no send) — mirrors hedge-fund preflight."""
    if not smtp_configured(settings):
        return {
            "ok": False,
            "error": "SMTP incomplete — need host, user, and password",
        }
    host = str(settings.get("smtp_host") or "").strip()
    port = int(settings.get("smtp_port") or 587)
    user = str(settings.get("smtp_user") or "").strip()
    password = str(settings.get("smtp_password") or "").strip()
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
        return {"ok": True, "host": host, "port": port}
    except Exception as e:
        return {"ok": False, "error": str(e), "host": host, "port": port}


def send_email(
    settings: dict[str, Any],
    *,
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> dict[str, str]:
    if not smtp_configured(settings):
        raise ValueError("SMTP not configured (need smtp_host, smtp_user, smtp_password)")
    host = str(settings.get("smtp_host") or "").strip()
    port = int(settings.get("smtp_port", 587))
    user = str(settings.get("smtp_user") or "").strip()
    password = str(settings.get("smtp_password") or "").strip()
    from_addr = str(settings.get("smtp_from") or user).strip() or user

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
    return {"status": "sent", "to": to_addr}
