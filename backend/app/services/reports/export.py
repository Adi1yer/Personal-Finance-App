from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy.orm import Session

from app.services.reports.generator import (
    balance_sheet,
    cash_flow_statement,
    income_statement,
    quarter_date_range,
    quarterly_metrics,
)


def export_quarter_package(db: Session, year: int, quarter: int, fmt: str) -> tuple[str, str, bytes]:
    """Return (content_type, filename, body)."""
    start, end = quarter_date_range(year, quarter)
    bs = balance_sheet(db, end)
    inc = income_statement(db, start, end)
    cf = cash_flow_statement(db, start, end)
    metrics = quarterly_metrics(db, year, quarter)

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Quarterly Financial Package Q{quarter} {year}"])
        w.writerow([])
        w.writerow(["Balance Sheet", f"As of {bs.as_of}"])
        w.writerow(["Total Assets", str(bs.total_assets)])
        w.writerow(["Total Liabilities", str(bs.total_liabilities)])
        w.writerow(["Net Worth", str(bs.net_worth)])
        w.writerow([])
        w.writerow(["Income Statement", f"{inc.start} to {inc.end}"])
        w.writerow(["Total Income", str(inc.total_income)])
        w.writerow(["Total Expenses", str(inc.total_expenses)])
        w.writerow(["Net Income", str(inc.net_income)])
        for line in inc.expenses:
            w.writerow(["Expense", line.account_name, str(line.total)])
        w.writerow([])
        w.writerow(["Cash Flow Statement", f"{cf.start} to {cf.end}"])
        w.writerow(["Net Operating", str(cf.net_operating)])
        w.writerow(["Net Investing", str(cf.net_investing)])
        w.writerow(["Net Financing", str(cf.net_financing)])
        w.writerow(["Net Change", str(cf.net_change)])
        w.writerow([])
        w.writerow(["Spending by Category"])
        for row in metrics.spending_by_category:
            w.writerow([row["category"], row["amount"]])
        body = buf.getvalue().encode("utf-8")
        return "text/csv", f"financials_q{quarter}_{year}.csv", body

    # Plain-text PDF substitute (printable)
    lines = [
        f"QUARTERLY FINANCIAL PACKAGE — Q{quarter} {year}",
        "",
        f"BALANCE SHEET (as of {bs.as_of})",
        f"  Total assets:      {bs.total_assets}",
        f"  Total liabilities: {bs.total_liabilities}",
        f"  Net worth:         {bs.net_worth}",
        "",
        f"INCOME STATEMENT ({inc.start} to {inc.end})",
        f"  Total income:   {inc.total_income}",
        f"  Total expenses: {inc.total_expenses}",
        f"  Net income:     {inc.net_income}",
        "",
        f"CASH FLOW ({cf.start} to {cf.end})",
        f"  Operating: {cf.net_operating}",
        f"  Investing: {cf.net_investing}",
        f"  Financing: {cf.net_financing}",
        f"  Net change: {cf.net_change}",
    ]
    body = "\n".join(lines).encode("utf-8")
    return "text/plain", f"financials_q{quarter}_{year}.txt", body
