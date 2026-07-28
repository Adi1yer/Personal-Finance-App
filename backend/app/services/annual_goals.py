"""Annual % of income goals with monthly progress."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.investment_baseline import BASELINE_PREFIX
from app.services.investment_contribution_detect import looks_like_external_contribution
from app.services.ledger import account_balance
from app.services.profile_settings import get_all_settings
from app.services.reports.generator import income_statement
from app.services.seed import SYSTEM_ACCOUNT_SLUGS

# Plaid / ledger labels that mean new money into an investment account.
_CONTRIBUTION_SUBTYPES = frozenset({"contribution", "match", "deposit"})
_INVEST_SUBTYPES = (
    AccountSubtype.brokerage,
    AccountSubtype.retirement,
    AccountSubtype.hsa,
)


def _detect_annual_income(db: Session, year: int) -> Decimal:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    stmt = income_statement(db, start, end)
    return Decimal(str(stmt.total_income))


def _investment_account_map(db: Session) -> dict[int, Account]:
    return {
        a.id: a
        for a in db.query(Account).filter(Account.subtype.in_(_INVEST_SUBTYPES)).all()
    }


def _contribution_category_ids(db: Session) -> set[int]:
    rows = (
        db.query(Category.id)
        .filter(Category.slug.in_(["investment_contribution"]))
        .all()
    )
    return {r[0] for r in rows}


def _ytd_invested_breakdown(db: Session, year: int) -> tuple[Decimal, list[dict[str, Any]]]:
    """Sum true YTD contributions into brokerage / retirement / HSA.

    Counts:
      - investment_subtype contribution / match / deposit (positive on invest account)
      - transfers into an invest account from a non-invest account
      - invest-account credits categorized as investment_contribution

    Excludes buys, sells, dividends, interest, reinvests, and opening baselines.
    """
    start = date(year, 1, 1)
    end = date.today()
    invest_accounts = _investment_account_map(db)
    contrib_cats = _contribution_category_ids(db)
    per_account: dict[int, Decimal] = {aid: Decimal("0") for aid in invest_accounts}

    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
        )
        .all()
    )

    for txn in txns:
        if txn.external_id and str(txn.external_id).startswith(BASELINE_PREFIX):
            continue

        invest_entries = [e for e in txn.entries if e.account_id in invest_accounts]
        if not invest_entries:
            continue

        subtype = (txn.investment_subtype or "").strip().lower()
        is_transfer_in = bool(txn.is_transfer) and any(
            Decimal(str(e.amount)) > 0 for e in invest_entries
        ) and any(e.account_id not in invest_accounts for e in txn.entries)

        chase_style = looks_like_external_contribution(
            payee=txn.payee or "",
            memo=txn.memo,
            investment_subtype=txn.investment_subtype,
            amount=next(
                (Decimal(str(e.amount)) for e in invest_entries),
                None,
            ),
        )

        for entry in invest_entries:
            amt = Decimal(str(entry.amount))
            categorized = bool(entry.category_id and entry.category_id in contrib_cats)

            # Chase ACH → deposit-sweep often posts as a buy with a negative ledger amount.
            if chase_style or subtype in _CONTRIBUTION_SUBTYPES:
                per_account[entry.account_id] += abs(amt)
                continue

            if amt <= 0:
                continue
            if is_transfer_in or categorized:
                per_account[entry.account_id] += amt

    total = sum(per_account.values(), Decimal("0"))
    breakdown = [
        {
            "account_id": aid,
            "name": invest_accounts[aid].name,
            "subtype": invest_accounts[aid].subtype.value,
            "ytd_contributions": str(amount.quantize(Decimal("0.01"))),
        }
        for aid, amount in sorted(per_account.items(), key=lambda kv: invest_accounts[kv[0]].name.lower())
        if amount > 0 or invest_accounts[aid].subtype in (AccountSubtype.retirement, AccountSubtype.hsa)
    ]
    # Always show retirement/HSA rows (even $0) so missing contributions are visible.
    # Keep brokerage only when it has contributions.
    breakdown = [
        row
        for row in breakdown
        if Decimal(row["ytd_contributions"]) > 0
        or invest_accounts[row["account_id"]].subtype
        in (AccountSubtype.retirement, AccountSubtype.hsa)
    ]
    return total, breakdown


def _ytd_invested(db: Session, year: int) -> Decimal:
    total, _ = _ytd_invested_breakdown(db, year)
    return total


def get_annual_goals_progress(db: Session) -> dict[str, Any]:
    settings = get_all_settings(db)
    year = date.today().year
    month = date.today().month

    income_override = settings.get("annual_income_override")
    annual_income = Decimal(str(income_override)) if income_override else _detect_annual_income(db, year)
    investing_pct = Decimal(str(settings.get("investing_pct_of_income", 20)))
    safety_pct = Decimal(str(settings.get("safety_net_pct_of_income", 10)))

    investing_target = (annual_income * investing_pct / Decimal("100")).quantize(Decimal("0.01"))
    safety_target = (annual_income * safety_pct / Decimal("100")).quantize(Decimal("0.01"))
    ytd_invested, by_account = _ytd_invested_breakdown(db, year)

    safety_account_id = settings.get("safety_net_account_id")
    safety_balance = Decimal("0")
    if safety_account_id:
        safety_balance = account_balance(db, int(safety_account_id))
    else:
        for acc in db.query(Account).filter(Account.subtype == AccountSubtype.checking).all():
            if acc.slug in SYSTEM_ACCOUNT_SLUGS:
                continue
            safety_balance += account_balance(db, acc.id)

    months_elapsed = max(month, 1)
    investing_pace_target = investing_target * Decimal(months_elapsed) / Decimal("12")

    ytd_q = ytd_invested.quantize(Decimal("0.01"))
    pace_q = investing_pace_target.quantize(Decimal("0.01"))
    safety_q = safety_balance.quantize(Decimal("0.01"))
    shortfall_vs_pace = max(pace_q - ytd_q, Decimal("0")).quantize(Decimal("0.01"))
    ahead_of_pace = max(ytd_q - pace_q, Decimal("0")).quantize(Decimal("0.01"))
    remaining_to_annual = max(investing_target - ytd_q, Decimal("0")).quantize(Decimal("0.01"))
    safety_shortfall = max(safety_target - safety_q, Decimal("0")).quantize(Decimal("0.01"))

    return {
        "year": year,
        "month": month,
        "annual_income": str(annual_income),
        "income_source": "override" if income_override else "ledger",
        "investing": {
            "pct_of_income": float(investing_pct),
            "annual_target": str(investing_target),
            "ytd_actual": str(ytd_q),
            "pace_target": str(pace_q),
            "shortfall_vs_pace": str(shortfall_vs_pace),
            "ahead_of_pace": str(ahead_of_pace),
            "remaining_to_annual": str(remaining_to_annual),
            "on_track": ytd_invested >= investing_pace_target * Decimal("0.9"),
            "by_account": by_account,
        },
        "safety_net": {
            "pct_of_income": float(safety_pct),
            "target_balance": str(safety_target),
            "current_balance": str(safety_q),
            "shortfall_vs_target": str(safety_shortfall),
            "on_track": safety_balance >= safety_target * Decimal(str(months_elapsed)) / Decimal("12"),
        },
    }
