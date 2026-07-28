from datetime import date

import typer

from app.db.session import SessionLocal
from app.services.reports import (
    balance_sheet,
    cash_flow_statement,
    income_statement,
    quarter_date_range,
    quarterly_metrics,
)
from app.db.registry import get_registry_session_factory, init_registry_database
from app.services.auth import admin_reset_password
from app.services.seed import seed_chart_of_accounts

app = typer.Typer(help="Personal finance CLI")


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Run Alembic migrations."""
    from alembic import command
    from alembic.config import Config

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "backend" / "alembic"))
    command.upgrade(cfg, "head")
    typer.echo("Database upgraded.")


@app.command("seed-accounts")
def seed_accounts() -> None:
    """Seed institutions, accounts, and categories."""
    db = SessionLocal()
    try:
        seed_chart_of_accounts(db)
        typer.echo("Chart of accounts seeded.")
    finally:
        db.close()


@app.command("reports")
def reports(
    year: int = typer.Option(..., help="Year e.g. 2026"),
    quarter: int = typer.Option(..., help="Quarter 1-4"),
) -> None:
    """Print quarterly financial statements."""
    db = SessionLocal()
    try:
        start, end = quarter_date_range(year, quarter)
        typer.echo(f"\n=== Q{quarter} {year} ({start} to {end}) ===\n")
        bs = balance_sheet(db, end)
        typer.echo(f"Balance Sheet as of {bs.as_of}")
        typer.echo(f"  Total assets:      {bs.total_assets}")
        typer.echo(f"  Total liabilities: {bs.total_liabilities}")
        typer.echo(f"  Net worth:         {bs.net_worth}")
        inc = income_statement(db, start, end)
        typer.echo(f"\nIncome Statement")
        typer.echo(f"  Total income:   {inc.total_income}")
        typer.echo(f"  Total expenses: {inc.total_expenses}")
        typer.echo(f"  Net income:     {inc.net_income}")
        cf = cash_flow_statement(db, start, end)
        typer.echo(f"\nCash Flow")
        typer.echo(f"  Operating: {cf.net_operating}")
        typer.echo(f"  Investing: {cf.net_investing}")
        typer.echo(f"  Financing: {cf.net_financing}")
        typer.echo(f"  Net change: {cf.net_change}")
        m = quarterly_metrics(db, year, quarter)
        typer.echo(f"\nMetrics")
        typer.echo(f"  Savings rate: {m.savings_rate}")
        typer.echo(f"  Net worth change: {m.net_worth_change}")
    finally:
        db.close()


@app.command("reset-password")
def reset_password_cmd(
    email: str = typer.Argument(..., help="Profile email"),
    password: str = typer.Option(
        ...,
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="New password (8+ characters)",
    ),
) -> None:
    """Reset password locally (no recovery code needed). Issues a new recovery code."""
    init_registry_database()
    db = get_registry_session_factory()()
    try:
        _, recovery_code = admin_reset_password(db, email, password)
        typer.echo(f"Password updated for {email}")
        typer.echo(f"New recovery code (save this): {recovery_code}")
    except (LookupError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        db.close()


@app.command("repair-ledger")
def repair_ledger_cmd(
    email: str = typer.Argument(..., help="Profile email"),
) -> None:
    """Fix a profile whose ledger database is empty or missing tables."""
    from app.models.profile import Profile
    from app.db.profile_db import init_profile_ledger

    init_registry_database()
    db = get_registry_session_factory()()
    try:
        profile = db.query(Profile).filter(Profile.email == email.strip().lower()).first()
        if not profile:
            raise typer.Exit("Profile not found. Run: finance list-profiles")
        init_profile_ledger(profile.id)
        typer.echo(f"Ledger repaired for {profile.email}")
    finally:
        db.close()


@app.command("list-profiles")
def list_profiles_cmd() -> None:
    """Show registered profile emails (local registry)."""
    from app.models.profile import Profile

    init_registry_database()
    db = get_registry_session_factory()()
    try:
        rows = db.query(Profile).order_by(Profile.email).all()
        if not rows:
            typer.echo("No profiles registered.")
            return
        for p in rows:
            typer.echo(f"{p.email}  ({p.display_name})")
    finally:
        db.close()


@app.command("reset-plaid")
def reset_plaid_cmd(
    email: str = typer.Argument(..., help="Profile email"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
) -> None:
    """Remove Plaid bank links and sandbox/imported transactions. Keeps your accounts."""
    from app.models.profile import Profile
    from app.db.profile_db import get_profile_session_factory
    from app.services.plaid_cleanup import reset_plaid_data

    init_registry_database()
    registry = get_registry_session_factory()()
    try:
        profile = registry.query(Profile).filter(Profile.email == email.strip().lower()).first()
        if not profile:
            raise typer.Exit("Profile not found. Run: finance list-profiles")
        if not yes and not typer.confirm(
            f"Remove all Plaid connections and imported transactions for {profile.email}?"
        ):
            raise typer.Exit("Cancelled.")
        db = get_profile_session_factory(profile.id)()
        try:
            result = reset_plaid_data(db)
            typer.echo(f"Plaid reset: {result}")
        finally:
            db.close()
    finally:
        registry.close()


@app.command("sync-all-profiles")
def sync_all_profiles_cmd(force: bool = typer.Option(False, "--force")) -> None:
    """Run Plaid sync for every registered profile (cloud scheduler uses this)."""
    from app.services.plaid_scheduler import sync_all_profiles

    results = sync_all_profiles(force=force)
    if not results:
        typer.echo("No profiles or Plaid not configured.")
        return
    for row in results:
        typer.echo(row)


@app.command("import-plaid")
def import_plaid() -> None:
    """Sync transactions from Plaid."""
    from app.services.plaid_sync import sync_all

    db = SessionLocal()
    try:
        result = sync_all(db, force=True)
        typer.echo(f"Plaid sync: {result}")
    finally:
        db.close()


@app.command("recategorize")
def recategorize_cmd(
    from_staging: bool = typer.Option(True, help="Use ImportStaging raw_json for Plaid PFC"),
) -> None:
    """Apply category rules and Plaid PFC mapping to existing transactions."""
    from app.services.recategorize import recategorize_transactions

    db = SessionLocal()
    try:
        result = recategorize_transactions(db, from_staging=from_staging)
        typer.echo(f"Recategorize: {result}")
    finally:
        db.close()


@app.command("repair-transaction-recognition")
def repair_transaction_recognition_cmd() -> None:
    """Normalize category rules to canonical keys and re-categorize transactions."""
    from app.services.recategorize import repair_transaction_recognition

    db = SessionLocal()
    try:
        result = repair_transaction_recognition(db)
        typer.echo(f"Transaction recognition repair: {result}")
    finally:
        db.close()


@app.command("repair-category-rules")
def repair_category_rules_cmd() -> None:
    """Normalize Zelle rule patterns and clear ambiguous auto-categorizations."""
    from app.services.recategorize import repair_category_rules

    db = SessionLocal()
    try:
        result = repair_category_rules(db)
        typer.echo(f"Repair category rules: {result}")
    finally:
        db.close()


@app.command("reset-tracking-start")
def reset_tracking_start_cmd() -> None:
    """Void pre-cutoff transactions, set tracking to 6/22/2026, and reseed balances."""
    from app.services.tracking_reset import reset_tracking_start

    db = SessionLocal()
    try:
        result = reset_tracking_start(db)
        typer.echo(f"Tracking reset: {result}")
    finally:
        db.close()


@app.command("seed-investment-baseline")
def seed_investment_baseline_cmd() -> None:
    """Seed day-zero opening positions for Chase brokerage and Roth IRA."""
    from app.services.investment_baseline import seed_investment_baseline

    db = SessionLocal()
    try:
        result = seed_investment_baseline(db)
        typer.echo(f"Investment baseline: {result}")
    finally:
        db.close()


@app.command("seed-opening-balances")
def seed_opening_balances_cmd() -> None:
    """Create or update opening balance entries from Plaid balances."""
    from app.services.opening_balances import seed_opening_balances

    db = SessionLocal()
    try:
        result = seed_opening_balances(db)
        typer.echo(f"Opening balances: {result}")
    finally:
        db.close()


@app.command("repair-opening-balances")
def repair_opening_balances_cmd() -> None:
    """Recompute opening:* entries so ledger balances match Plaid."""
    from app.services.opening_balances import repair_opening_balances

    db = SessionLocal()
    try:
        result = repair_opening_balances(db)
        typer.echo(f"Opening balances repaired: {result}")
    finally:
        db.close()


@app.command("repair-card-postings")
def repair_card_postings_cmd() -> None:
    """Void mis-posted card txns and duplicate checking-side card payments."""
    from app.db.profile_db import get_profile_session_factory
    from app.db.registry import get_registry_session_factory, init_registry_database
    from app.models.profile import Profile
    from app.services.card_payments import repair_duplicate_card_payments
    from app.services.plaid_dedup import repair_duplicate_plaid_transactions
    from app.services.posting_repair import repair_card_cross_posted_transactions

    init_registry_database()
    registry = get_registry_session_factory()()
    try:
        profiles = registry.query(Profile).order_by(Profile.email).all()
        if not profiles:
            db = SessionLocal()
            try:
                cross = repair_card_cross_posted_transactions(db)
                dup = repair_duplicate_card_payments(db)
                plaid_dup = repair_duplicate_plaid_transactions(db)
                typer.echo(f"Card posting repair: {cross}, duplicates={dup}, plaid_dup={plaid_dup}")
            finally:
                db.close()
            return
        for profile in profiles:
            db = get_profile_session_factory(profile.id)()
            try:
                cross = repair_card_cross_posted_transactions(db)
                dup = repair_duplicate_card_payments(db)
                plaid_dup = repair_duplicate_plaid_transactions(db)
                from app.services.opening_balances import repair_opening_balances

                opening = repair_opening_balances(db)
                typer.echo(
                    f"{profile.email}: cross={cross}, duplicates={dup}, "
                    f"plaid_dup={plaid_dup}, opening={opening}"
                )
            finally:
                db.close()
    finally:
        registry.close()


@app.command("sync")
def sync_cmd(force: bool = typer.Option(True, "--force/--no-force")) -> None:
    """Sync Plaid transactions and holdings for the active profile."""
    from app.services.plaid_sync import sync_all

    db = SessionLocal()
    try:
        result = sync_all(db, force=force)
        typer.echo(f"Plaid sync: {result}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
