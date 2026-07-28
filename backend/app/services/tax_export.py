"""CPA-ready tax export when fiscal year is complete."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction
from app.services.reports.generator import income_statement
from app.services.transaction_recognition import recognize_transaction


def tax_year_available(year: int) -> bool:
    today = date.today()
    return today.year > year or (today.year == year and today.month == 12 and today.day == 31)


def build_tax_export(db: Session, year: int) -> dict[str, Any]:
    if not tax_year_available(year):
        return {"available": False, "year": year, "message": "Available after Dec 31"}

    start = date(year, 1, 1)
    end = date(year, 12, 31)
    stmt = income_statement(db, start, end)

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

    dividend_total = Decimal("0")
    interest_total = Decimal("0")
    for txn in txns:
        rec = recognize_transaction(
            payee=txn.payee,
            memo=txn.memo,
            investment_subtype=txn.investment_subtype,
        )
        amt = sum(abs(Decimal(str(e.amount))) for e in txn.entries)
        if rec.family == "dividend":
            dividend_total += amt
        elif rec.family == "interest":
            interest_total += amt

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["txn_date", "payee", "amount", "category"])
    for txn in txns:
        amt = sum(Decimal(str(e.amount)) for e in txn.entries)
        w.writerow([txn.txn_date.isoformat(), txn.payee, str(amt), ""])

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"transactions_{year}.csv", buf.getvalue())
        summary = (
            f"Tax year {year}\n"
            f"Total income: {stmt.total_income}\n"
            f"Dividends: {dividend_total}\n"
            f"Interest: {interest_total}\n"
        )
        zf.writestr(f"summary_{year}.txt", summary)

    return {
        "available": True,
        "year": year,
        "total_income": str(stmt.total_income),
        "dividends": str(dividend_total),
        "interest": str(interest_total),
        "zip_base64": zip_buf.getvalue().hex(),
    }
