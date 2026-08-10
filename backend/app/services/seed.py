from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.cash_flow_mapping import CashFlowCategory, CashFlowMapping
from app.models.category import Category, CategoryType


# Only system accounts — user-named Chase / Empower / etc. are created in the UI.
SYSTEM_ACCOUNT_SLUGS = frozenset(
    {
        "uncategorized_expense",
        "salary_income",
        "other_income",
        "opening_equity",
    }
)

PROTECTED_CATEGORY_SLUGS = frozenset(
    {
        "groceries",
        "dining",
        "housing",
        "transportation",
        "utilities",
        "healthcare",
        "investment_contribution",
        "salary",
        "interest_dividends",
        "uncategorized",
    }
)

# Used when an account explicitly stores a tracking start (tests / legacy).
# New accounts default to None (track from first sync / activity).
DEFAULT_TRACKING_START = date(2026, 6, 22)


def default_tracking_start(subtype: AccountSubtype) -> date | None:
    """New accounts have no hard-coded cutoff — sync from available history."""
    return None


def seed_chart_of_accounts(db: Session) -> None:
    """Seed categories and required system ledger accounts only."""
    system_accounts = [
        ("Uncategorized Expense", "uncategorized_expense", AccountType.expense, AccountSubtype.other),
        ("Salary Income", "salary_income", AccountType.income, AccountSubtype.other),
        ("Other Income", "other_income", AccountType.income, AccountSubtype.other),
        ("Opening Equity", "opening_equity", AccountType.equity, AccountSubtype.other),
    ]

    for name, slug, atype, subtype in system_accounts:
        if db.query(Account).filter(Account.slug == slug).first():
            continue
        db.add(
            Account(
                name=name,
                slug=slug,
                account_type=atype,
                subtype=subtype,
                sync_source=SyncSource.manual,
            )
        )

    categories = [
        ("Groceries", "groceries", CategoryType.expense),
        ("Dining", "dining", CategoryType.expense),
        ("Housing", "housing", CategoryType.expense),
        ("Transportation", "transportation", CategoryType.expense),
        ("Utilities", "utilities", CategoryType.expense),
        ("Healthcare", "healthcare", CategoryType.expense),
        ("Investment Contribution", "investment_contribution", CategoryType.expense),
        ("Salary", "salary", CategoryType.income),
        ("Interest & Dividends", "interest_dividends", CategoryType.income),
        ("Other Income", "other_income", CategoryType.income),
        ("Uncategorized", "uncategorized", CategoryType.expense),
    ]

    cat_map: dict[str, Category] = {}
    for name, slug, ctype in categories:
        cat = db.query(Category).filter(Category.slug == slug).first()
        if not cat:
            cat = Category(name=name, slug=slug, category_type=ctype)
            db.add(cat)
            db.flush()
        cat_map[slug] = cat

    if not db.query(CashFlowMapping).first():
        mappings = [
            (cat_map["salary"], CashFlowCategory.operating),
            (cat_map["groceries"], CashFlowCategory.operating),
            (cat_map["dining"], CashFlowCategory.operating),
            (cat_map["housing"], CashFlowCategory.operating),
            (cat_map["investment_contribution"], CashFlowCategory.investing),
        ]
        for cat, cf_type in mappings:
            db.add(CashFlowMapping(category_id=cat.id, cash_flow_type=cf_type, label=cat.name))

    db.commit()
