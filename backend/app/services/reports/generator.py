from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.cash_flow_mapping import CashFlowCategory, CashFlowMapping
from app.models.category import Category, CategoryType
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.schemas.reports import (
    BalanceSheetLine,
    BalanceSheetReport,
    CashFlowLine,
    CashFlowReport,
    IncomeStatementLine,
    IncomeStatementReport,
    MonthlyMetrics,
    NetWorthHistoryPoint,
    NetWorthHistoryReport,
    QuarterlyMetrics,
)
from app.services.ledger import account_balance, all_account_balances


def quarter_date_range(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1-4")
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    m, d = starts[quarter]
    start = date(year, m, d)
    em, ed = ends[quarter]
    end = date(year, em, ed)
    return start, end


def month_date_range(year: int, month: int) -> tuple[date, date]:
    if month not in range(1, 13):
        raise ValueError("month must be 1-12")
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


MANUAL_MARK_SUBTYPES = frozenset({AccountSubtype.retirement, AccountSubtype.hsa})
FRESHNESS_DAYS = 7


def _entry_base_filters(start: date, end: date):
    return (
        Entry.entry_date >= start,
        Entry.entry_date <= end,
        Transaction.is_transfer.is_(False),
        Transaction.voided_at.is_(None),
    )


def _tracking_ok(acc: Account | None, entry_date: date) -> bool:
    if not acc or not acc.tracking_start_date:
        return True
    return entry_date >= acc.tracking_start_date


def reports_readiness(db: Session, as_of: date | None = None) -> dict:
    """Require manual 401(k)/HSA marks covering the report date, saved recently."""
    report_date = as_of or date.today()
    today = date.today()
    stale: list[dict] = []
    for acc in db.scalars(
        select(Account).where(
            Account.sync_source == SyncSource.manual,
            Account.subtype.in_(MANUAL_MARK_SUBTYPES),
            Account.is_active.is_(True),
        )
    ).all():
        mark = (
            db.query(AccountMark)
            .filter(
                AccountMark.account_id == acc.id,
                AccountMark.as_of_date <= report_date,
            )
            .order_by(AccountMark.as_of_date.desc())
            .first()
        )
        if not mark:
            stale.append({"account_id": acc.id, "account_name": acc.name, "reason": "no mark"})
            continue
        saved_on = mark.updated_at.date() if mark.updated_at else mark.as_of_date
        if (today - saved_on).days > FRESHNESS_DAYS:
            stale.append(
                {
                    "account_id": acc.id,
                    "account_name": acc.name,
                    "reason": "stale",
                    "last_updated": saved_on.isoformat(),
                    "value_as_of": mark.as_of_date.isoformat(),
                }
            )
    return {"ready": len(stale) == 0, "stale_accounts": stale}


def balance_sheet(db: Session, as_of: date) -> BalanceSheetReport:
    balances = all_account_balances(db, as_of)
    accounts = {a.id: a for a in db.scalars(select(Account)).all()}

    def lines_for(types: tuple[AccountType, ...]) -> list[BalanceSheetLine]:
        result = []
        for aid, bal in balances.items():
            acc = accounts.get(aid)
            if acc and acc.account_type in types and bal != 0:
                result.append(
                    BalanceSheetLine(
                        account_id=aid,
                        account_name=acc.name,
                        account_type=acc.account_type.value,
                        balance=bal,
                    )
                )
        return sorted(result, key=lambda x: x.account_name)

    assets = lines_for((AccountType.asset,))
    liabilities = lines_for((AccountType.liability,))
    equity = lines_for((AccountType.equity,))

    total_assets = sum((a.balance for a in assets), Decimal("0"))
    total_liabilities = sum((l.balance for l in liabilities), Decimal("0"))
    total_equity = sum((e.balance for e in equity), Decimal("0"))
    net_worth = total_assets - total_liabilities

    return BalanceSheetReport(
        as_of=as_of.isoformat(),
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        net_worth=net_worth,
    )


def income_statement(db: Session, start: date, end: date) -> IncomeStatementReport:
    base = _entry_base_filters(start, end)

    income_q = (
        select(Category.name, Category.id, func.sum(Entry.amount))
        .join(Entry, Entry.category_id == Category.id)
        .join(Transaction)
        .join(Account, Entry.account_id == Account.id)
        .where(*base, Category.category_type == CategoryType.income)
        .group_by(Category.id)
    )
    expense_q = (
        select(Category.name, Category.id, func.sum(Entry.amount))
        .join(Entry, Entry.category_id == Category.id)
        .join(Transaction)
        .join(Account, Entry.account_id == Account.id)
        .where(*base, Category.category_type == CategoryType.expense)
        .group_by(Category.id)
    )

    income_lines: list[IncomeStatementLine] = []
    expense_lines: list[IncomeStatementLine] = []

    for name, cat_id, total in db.execute(income_q).all():
        amt = -Decimal(str(total))
        if amt != 0:
            income_lines.append(
                IncomeStatementLine(
                    account_id=cat_id,
                    account_name=name,
                    account_type="income",
                    total=amt,
                )
            )

    for name, cat_id, total in db.execute(expense_q).all():
        amt = Decimal(str(total))
        if amt != 0:
            expense_lines.append(
                IncomeStatementLine(
                    account_id=cat_id,
                    account_name=name,
                    account_type="expense",
                    total=amt,
                )
            )

    # Fallback: uncategorized expense/income accounts without category_id
    accounts = {
        a.id: a
        for a in db.scalars(
            select(Account).where(
                Account.account_type.in_([AccountType.income, AccountType.expense])
            )
        ).all()
    }
    q = (
        select(Entry.account_id, func.sum(Entry.amount))
        .join(Transaction)
        .join(Account, Entry.account_id == Account.id)
        .where(*base, Entry.category_id.is_(None), Entry.account_id.in_(accounts.keys()))
        .group_by(Entry.account_id)
    )
    for account_id, total in db.execute(q).all():
        acc = accounts[account_id]
        amt = Decimal(str(total))
        if acc.account_type == AccountType.income:
            income_lines.append(
                IncomeStatementLine(
                    account_id=account_id,
                    account_name=acc.name,
                    account_type="income",
                    total=-amt,
                )
            )
        else:
            expense_lines.append(
                IncomeStatementLine(
                    account_id=account_id,
                    account_name=acc.name,
                    account_type="expense",
                    total=amt,
                )
            )

    total_income = sum((i.total for i in income_lines), Decimal("0"))
    total_expenses = sum((e.total for e in expense_lines), Decimal("0"))

    return IncomeStatementReport(
        start=start.isoformat(),
        end=end.isoformat(),
        income=sorted(income_lines, key=lambda x: x.account_name),
        expenses=sorted(expense_lines, key=lambda x: x.account_name),
        total_income=total_income,
        total_expenses=total_expenses,
        net_income=total_income - total_expenses,
    )


def _cf_type_for_entry(db: Session, entry: Entry) -> CashFlowCategory:
    if entry.category_id:
        mapping = (
            db.query(CashFlowMapping)
            .filter(CashFlowMapping.category_id == entry.category_id)
            .first()
        )
        if mapping:
            return mapping.cash_flow_type
    acc = db.get(Account, entry.account_id)
    if acc and acc.account_type.value == "liability" and acc.subtype.value == "credit_card":
        return CashFlowCategory.financing
    return CashFlowCategory.operating


def cash_flow_statement(db: Session, start: date, end: date) -> CashFlowReport:
    entries = (
        db.query(Entry)
        .join(Transaction)
        .filter(*_entry_base_filters(start, end))
        .all()
    )

    buckets: dict[CashFlowCategory, dict[str, Decimal]] = {
        CashFlowCategory.operating: {},
        CashFlowCategory.investing: {},
        CashFlowCategory.financing: {},
    }

    for entry in entries:
        acc = db.get(Account, entry.account_id)
        if not acc or acc.account_type not in (AccountType.asset, AccountType.liability):
            continue
        if acc.subtype in MANUAL_MARK_SUBTYPES:
            continue
        if acc.subtype.value not in ("checking", "credit_card"):
            continue
        if not _tracking_ok(acc, entry.entry_date):
            continue
        cf = _cf_type_for_entry(db, entry)
        label = entry.transaction.payee or acc.name
        buckets[cf][label] = buckets[cf].get(label, Decimal("0")) + Decimal(str(entry.amount))

    def to_lines(d: dict[str, Decimal]) -> list[CashFlowLine]:
        return [CashFlowLine(label=k, amount=v) for k, v in sorted(d.items())]

    net_op = sum(buckets[CashFlowCategory.operating].values(), Decimal("0"))
    net_inv = sum(buckets[CashFlowCategory.investing].values(), Decimal("0"))
    net_fin = sum(buckets[CashFlowCategory.financing].values(), Decimal("0"))

    return CashFlowReport(
        start=start.isoformat(),
        end=end.isoformat(),
        operating=to_lines(buckets[CashFlowCategory.operating]),
        investing=to_lines(buckets[CashFlowCategory.investing]),
        financing=to_lines(buckets[CashFlowCategory.financing]),
        net_operating=net_op,
        net_investing=net_inv,
        net_financing=net_fin,
        net_change=net_op + net_inv + net_fin,
    )


def quarterly_metrics(db: Session, year: int, quarter: int) -> QuarterlyMetrics:
    start, end = quarter_date_range(year, quarter)
    is_report = income_statement(db, start, end)
    bs = balance_sheet(db, end)

    prior_q = quarter - 1
    prior_year = year
    if prior_q < 1:
        prior_q = 4
        prior_year -= 1
    _, prior_end = quarter_date_range(prior_year, prior_q)
    prior_bs = balance_sheet(db, prior_end)

    savings = None
    if is_report.total_income > 0:
        savings = (is_report.total_income - is_report.total_expenses) / is_report.total_income

    spend_q = (
        select(Category.name, func.sum(Entry.amount))
        .join(Entry, Entry.category_id == Category.id)
        .join(Transaction)
        .join(Account, Entry.account_id == Account.id)
        .where(
            *_entry_base_filters(start, end),
            Category.category_type == CategoryType.expense,
        )
        .group_by(Category.id)
    )
    spending = [
        {"category": name, "amount": str(Decimal(str(total)))}
        for name, total in db.execute(spend_q).all()
    ]

    nw_change = bs.net_worth - prior_bs.net_worth

    return QuarterlyMetrics(
        year=year,
        quarter=quarter,
        start=start.isoformat(),
        end=end.isoformat(),
        net_worth=bs.net_worth,
        prior_net_worth=prior_bs.net_worth,
        net_worth_change=nw_change,
        total_income=is_report.total_income,
        total_expenses=is_report.total_expenses,
        net_income=is_report.net_income,
        savings_rate=savings,
        spending_by_category=spending,
    )


def _spending_by_category(db: Session, start: date, end: date) -> list[dict]:
    spend_q = (
        select(Category.name, func.sum(Entry.amount))
        .join(Entry, Entry.category_id == Category.id)
        .join(Transaction)
        .join(Account, Entry.account_id == Account.id)
        .where(
            *_entry_base_filters(start, end),
            Category.category_type == CategoryType.expense,
        )
        .group_by(Category.id)
    )
    return [
        {"category": name, "amount": str(abs(Decimal(str(total))))}
        for name, total in db.execute(spend_q).all()
    ]


def monthly_metrics(db: Session, year: int, month: int) -> MonthlyMetrics:
    start, end = month_date_range(year, month)
    is_report = income_statement(db, start, end)

    prior_month = month - 1
    prior_year = year
    if prior_month < 1:
        prior_month = 12
        prior_year -= 1
    prior_start, prior_end = month_date_range(prior_year, prior_month)
    prior_is = income_statement(db, prior_start, prior_end)

    spending = _spending_by_category(db, start, end)

    return MonthlyMetrics(
        year=year,
        month=month,
        start=start.isoformat(),
        end=end.isoformat(),
        total_income=is_report.total_income,
        total_expenses=is_report.total_expenses,
        net_income=is_report.net_income,
        prior_total_income=prior_is.total_income,
        prior_total_expenses=prior_is.total_expenses,
        prior_net_income=prior_is.net_income,
        spending_by_category=spending,
    )


def _history_start_date(db: Session) -> date:
    txn_min = db.scalar(
        select(func.min(Transaction.txn_date)).where(Transaction.voided_at.is_(None))
    )
    mark_min = db.scalar(select(func.min(AccountMark.as_of_date)))
    candidates = [d for d in (txn_min, mark_min) if d is not None]
    if not candidates:
        today = date.today()
        return date(today.year, today.month, 1)
    earliest = min(candidates)
    return date(earliest.year, earliest.month, 1)


def net_worth_history(db: Session) -> NetWorthHistoryReport:
    """Monthly reconstruction, with daily sync snapshots overriding same-day points."""
    from decimal import Decimal

    from app.services.net_worth_snapshots import list_snapshots

    start_month = _history_start_date(db)
    end = date.today()
    points_by_date: dict[str, NetWorthHistoryPoint] = {}

    cur = start_month
    while cur <= end:
        _, month_end = month_date_range(cur.year, cur.month)
        as_of = min(month_end, end)
        bs = balance_sheet(db, as_of)
        key = as_of.isoformat()
        points_by_date[key] = NetWorthHistoryPoint(
            date=key,
            net_worth=bs.net_worth,
            total_assets=bs.total_assets,
            total_liabilities=bs.total_liabilities,
        )
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    for snap in list_snapshots(db):
        key = snap["snapshot_date"]
        points_by_date[key] = NetWorthHistoryPoint(
            date=key,
            net_worth=Decimal(str(snap["total"])),
            total_assets=Decimal(str(snap.get("total_assets") or snap["total"])),
            total_liabilities=Decimal(str(snap.get("total_liabilities") or "0")),
        )

    points = [points_by_date[k] for k in sorted(points_by_date)]
    return NetWorthHistoryReport(
        start=points[0].date if points else end.isoformat(),
        end=end.isoformat(),
        points=points,
    )
