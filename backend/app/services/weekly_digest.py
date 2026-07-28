"""Weekly email digest with optional Ollama narrative."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.annual_goals import get_annual_goals_progress
from app.services.email_service import send_email
from app.services.net_worth_snapshots import list_snapshots
from app.services.ollama_client import OllamaError, chat, ollama_base_url, ollama_model
from app.services.profile_settings import get_all_settings
from app.services.sync_health import build_health_summary


def build_digest(db: Session) -> dict[str, Any]:
    health = build_health_summary(db)
    goals = get_annual_goals_progress(db)
    snapshots = list_snapshots(db, limit=14)
    nw_change = None
    if len(snapshots) >= 2:
        first = Decimal(snapshots[0]["total"])
        last = Decimal(snapshots[-1]["total"])
        nw_change = str((last - first).quantize(Decimal("0.01")))

    alerts: list[str] = []
    if health["suspected_duplicate_clusters"]:
        alerts.append(f"Duplicates: {health['suspected_duplicate_clusters']} clusters")
    if health["balance_mismatches"]:
        alerts.append(f"Balance mismatches: {len(health['balance_mismatches'])}")
    if not goals["investing"]["on_track"]:
        alerts.append("Investing goal off-track")

    return {
        "week_ending": date.today().isoformat(),
        "net_worth_change": nw_change,
        "goals": goals,
        "health": {
            "ok": health["ok"],
            "warnings": health["warnings"],
        },
        "alerts": alerts,
    }


def _narrative(settings: dict[str, Any], digest: dict[str, Any]) -> str:
    prompt = (
        "Write a brief weekly finance email (2 short paragraphs). "
        "Praise one positive and suggest 1-2 improvements. Use only these facts:\n"
        f"{digest}"
    )
    try:
        return chat(
            [{"role": "user", "content": prompt}],
            model=ollama_model(settings),
            base_url=ollama_base_url(settings),
        )
    except OllamaError:
        lines = ["Weekly personal finance digest", ""]
        if digest.get("net_worth_change"):
            lines.append(f"Net worth change (14d): ${digest['net_worth_change']}")
        if digest.get("alerts"):
            lines.append("Alerts: " + "; ".join(digest["alerts"]))
        return "\n".join(lines)


def send_weekly_digest(db: Session) -> dict[str, Any]:
    settings = get_all_settings(db)
    if not settings.get("digest_enabled", True):
        return {"status": "skipped", "reason": "disabled"}
    from app.services.email_service import smtp_configured

    if not smtp_configured(settings):
        return {"status": "skipped", "reason": "smtp_not_configured"}
    to_addr = settings.get("digest_email") or ""
    if not to_addr:
        return {"status": "skipped", "reason": "digest_email_missing"}
    digest = build_digest(db)
    narrative = _narrative(settings, digest)
    subject = f"Weekly finance digest — {digest['week_ending']}"
    alerts = digest.get("alerts") or ["No alerts"]
    body_text = narrative + "\n\n---\n" + "\n".join(alerts)
    body_html = (
        f"<html><body style='font-family:system-ui,sans-serif;line-height:1.5'>"
        f"<h2>Weekly finance digest</h2>"
        f"<p>{narrative.replace(chr(10), '<br/>')}</p>"
        f"<hr/><p><strong>Alerts</strong></p><ul>"
        + "".join(f"<li>{a}</li>" for a in alerts)
        + "</ul></body></html>"
    )
    send_email(
        settings,
        to_addr=to_addr,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    return {"status": "sent", "to": to_addr, "digest": digest}
