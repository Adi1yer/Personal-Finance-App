from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.services.payee_normalization import (
    AmountDirection,
    detect_provider,
    infer_direction,
)

# Plaid personal_finance_category.detailed -> category slug
PFC_TO_SLUG: dict[str, str] = {
    "FOOD_AND_DRINK_GROCERIES": "groceries",
    "FOOD_AND_DRINK_RESTAURANT": "dining",
    "FOOD_AND_DRINK_COFFEE": "dining",
    "FOOD_AND_DRINK_FAST_FOOD": "dining",
    "FOOD_AND_DRINK_VENDING_MACHINES": "dining",
    "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": "dining",
    "TRANSPORTATION_GAS": "transportation",
    "TRANSPORTATION_PARKING": "transportation",
    "TRANSPORTATION_PUBLIC_TRANSIT": "transportation",
    "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": "transportation",
    "TRANSPORTATION_TOLLS": "transportation",
    "TRANSPORTATION_OTHER_TRANSPORTATION": "transportation",
    "RENT_AND_UTILITIES_RENT": "housing",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "utilities",
    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "utilities",
    "RENT_AND_UTILITIES_TELEPHONE": "utilities",
    "RENT_AND_UTILITIES_WATER": "utilities",
    "RENT_AND_UTILITIES_OTHER_UTILITIES": "utilities",
    "MEDICAL_PRIMARY_CARE": "healthcare",
    "MEDICAL_DENTAL_CARE": "healthcare",
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": "healthcare",
    "MEDICAL_OTHER_MEDICAL": "healthcare",
    "INCOME_WAGES": "salary",
    "INCOME_INTEREST_EARNED": "interest_dividends",
    "INCOME_DIVIDENDS": "interest_dividends",
    "INCOME_OTHER_INCOME": "other_income",
    "TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS": "investment_contribution",
    "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS": "investment_contribution",
}

INVESTMENT_SUBTYPE_TO_SLUG: dict[str, str] = {
    "dividend": "interest_dividends",
    "interest": "interest_dividends",
    "contribution": "investment_contribution",
    "match": "investment_contribution",
    "withdrawal": "investment_contribution",
}


@dataclass(frozen=True)
class CategorySuggestion:
    category_id: int
    category_name: str
    rule_id: int | None = None
    label: str | None = None


def _category_by_slug(db: Session, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug).first()


def _rule_matches_haystack(rule: CategoryRule, haystack: str, normalized: str) -> bool:
    pattern = rule.pattern.lower()
    return pattern in haystack.lower() or pattern in normalized.lower()


def _direction_compatible(rule: CategoryRule, direction: AmountDirection) -> bool:
    if rule.amount_direction == "any" or direction == "none":
        return True
    return rule.amount_direction == direction


def matching_rules(
    db: Session,
    *,
    payee: str,
    memo: str,
    direction: AmountDirection,
    account_subtype: str | None = None,
) -> list[CategoryRule]:
    from app.services.transaction_recognition import recognize_transaction

    normalized = recognize_transaction(
        payee=payee,
        memo=memo or None,
        account_subtype=account_subtype,
    ).canonical_key
    matched: list[CategoryRule] = []
    rules = (
        db.query(CategoryRule)
        .order_by(CategoryRule.priority.desc(), CategoryRule.id.desc())
        .all()
    )
    for rule in rules:
        haystack = payee if rule.match_field == "payee" else memo
        if not _rule_matches_haystack(rule, haystack, normalized):
            continue
        if not _direction_compatible(rule, direction):
            continue
        matched.append(rule)
    return matched


def resolve_category_id(
    db: Session,
    *,
    payee: str,
    memo: str | None = None,
    raw_json: str | None = None,
    investment_subtype: str | None = None,
    investment_type: str | None = None,
    security_name: str | None = None,
    amount: Decimal | None = None,
    account_subtype: str | None = None,
    is_transfer: bool = False,
) -> int | None:
    """Priority: user rule > built-in recognition > Plaid PFC > investment subtype > uncategorized."""
    from app.services.transaction_recognition import recognize_transaction

    direction = infer_direction(payee, memo, amount=amount)
    rules = matching_rules(
        db, payee=payee, memo=memo or "", direction=direction, account_subtype=account_subtype
    )
    distinct_categories = {rule.category_id for rule in rules}
    if len(distinct_categories) == 1:
        return next(iter(distinct_categories))

    recognized = recognize_transaction(
        payee=payee,
        memo=memo,
        amount=amount,
        account_subtype=account_subtype,
        raw_json=raw_json,
        investment_type=investment_type,
        investment_subtype=investment_subtype,
        security_name=security_name,
        is_transfer=is_transfer,
    )
    if recognized.is_internal_transfer:
        uncategorized = _category_by_slug(db, "uncategorized")
        return uncategorized.id if uncategorized else None

    if recognized.suggested_category_slug:
        slug = recognized.suggested_category_slug
        if recognized.family == "reinvest":
            drip = db.query(Category).filter(Category.slug.ilike("drip")).first()
            if drip:
                return drip.id
        cat = _category_by_slug(db, slug)
        if cat:
            return cat.id

    if raw_json:
        data = parse_plaid_raw(raw_json)
        pfc = data.get("personal_finance_category") or {}
        detailed = pfc.get("detailed") or pfc.get("primary")
        if detailed:
            slug = PFC_TO_SLUG.get(str(detailed))
            if slug:
                cat = _category_by_slug(db, slug)
                if cat:
                    return cat.id

    if investment_subtype:
        slug = INVESTMENT_SUBTYPE_TO_SLUG.get(investment_subtype.lower())
        if slug:
            cat = _category_by_slug(db, slug)
            if cat:
                return cat.id

    uncategorized = _category_by_slug(db, "uncategorized")
    return uncategorized.id if uncategorized else None


def category_suggestions(
    db: Session,
    *,
    payee: str,
    memo: str | None,
    charge: Decimal | None,
    payment: Decimal | None,
    account_subtype: str | None = None,
) -> list[CategorySuggestion]:
    direction = infer_direction(payee, memo, charge=charge, payment=payment)
    rules = matching_rules(
        db,
        payee=payee,
        memo=memo or "",
        direction=direction,
        account_subtype=account_subtype,
    )

    suggestions: list[CategorySuggestion] = []
    seen_category_ids: set[int] = set()
    for rule in rules:
        if rule.category_id in seen_category_ids:
            continue
        cat = db.get(Category, rule.category_id)
        if not cat:
            continue
        seen_category_ids.add(rule.category_id)
        suggestions.append(
            CategorySuggestion(
                category_id=rule.category_id,
                category_name=cat.name,
                rule_id=rule.id,
                label=rule.pattern,
            )
        )

    if suggestions:
        return suggestions

    provider = detect_provider(payee, memo)
    if not provider or direction == "none":
        return []

    cat_type = "expense" if direction == "outflow" else "income"
    for rule in db.query(CategoryRule).order_by(CategoryRule.priority.desc()).all():
        if provider not in rule.pattern.lower():
            continue
        if not _direction_compatible(rule, direction):
            continue
        cat = db.get(Category, rule.category_id)
        if not cat or cat.category_type != cat_type:
            continue
        if rule.category_id in seen_category_ids:
            continue
        seen_category_ids.add(rule.category_id)
        suggestions.append(
            CategorySuggestion(
                category_id=rule.category_id,
                category_name=cat.name,
                rule_id=rule.id,
                label=rule.pattern,
            )
        )
    return suggestions


def create_rule(
    db: Session,
    *,
    pattern: str,
    category_id: int,
    match_field: str = "payee",
    priority: int = 10,
    amount_direction: str = "any",
    apply_to_existing: bool = True,
) -> tuple[CategoryRule, int]:
    rule = CategoryRule(
        match_field=match_field,
        pattern=pattern.strip(),
        category_id=category_id,
        priority=priority,
        amount_direction=amount_direction,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    applied = 0
    if apply_to_existing:
        from app.services.category_assignment import apply_category_rule_to_matching

        applied = apply_category_rule_to_matching(db, rule)
    return rule, applied


def list_rules(db: Session) -> list[CategoryRule]:
    return (
        db.query(CategoryRule)
        .options(joinedload(CategoryRule.category))
        .order_by(CategoryRule.priority.desc())
        .all()
    )


def update_rule(
    db: Session,
    rule_id: int,
    *,
    pattern: str | None = None,
    category_id: int | None = None,
    match_field: str | None = None,
    priority: int | None = None,
    amount_direction: str | None = None,
) -> CategoryRule:
    rule = db.get(CategoryRule, rule_id)
    if not rule:
        raise ValueError("Rule not found")
    if pattern is not None:
        rule.pattern = pattern.strip()
    if category_id is not None:
        rule.category_id = category_id
    if match_field is not None:
        rule.match_field = match_field
    if priority is not None:
        rule.priority = priority
    if amount_direction is not None:
        rule.amount_direction = amount_direction
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = db.get(CategoryRule, rule_id)
    if not rule:
        raise ValueError("Rule not found")
    db.delete(rule)
    db.commit()


def recategorize_last_days(db: Session, days: int = 90) -> dict[str, int]:
    from datetime import date, timedelta

    from app.models.transaction import Transaction
    from app.services.recategorize import recategorize_transactions

    cutoff = date.today() - timedelta(days=days)
    before = recategorize_transactions(db, from_staging=True)
    touched = (
        db.query(Transaction)
        .filter(Transaction.voided_at.is_(None), Transaction.txn_date >= cutoff)
        .count()
    )
    return {"updated": before.get("updated", 0), "transactions_in_window": touched}


def normalize_rule_patterns(db: Session) -> int:
    """Rewrite rules to canonical recognition keys."""
    from app.services.transaction_recognition import recognize_transaction

    updated = 0
    for rule in db.query(CategoryRule).all():
        canonical = recognize_transaction(payee=rule.pattern, memo=None).canonical_key
        if canonical != rule.pattern.strip():
            rule.pattern = canonical
            updated += 1
    if updated:
        db.commit()
    return updated


def _literal_eval_plaid_repr(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned.startswith("{"):
        return {}
    cleaned = re.sub(
        r"datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)",
        lambda m: repr(f"{int(m.group(1))}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        cleaned,
    )
    cleaned = re.sub(r"datetime\.datetime\([^)]*\)", "None", cleaned)
    cleaned = re.sub(r"datetime\.timezone\.utc", "None", cleaned)
    cleaned = re.sub(r"tzutc\(\)", "None", cleaned)
    cleaned = re.sub(r"<[^>]+>", "None", cleaned)
    try:
        val = ast.literal_eval(cleaned)
        return val if isinstance(val, dict) else {}
    except (SyntaxError, ValueError):
        amount_match = re.search(r"['\"]amount['\"]:\s*(-?\d+(?:\.\d+)?)", text)
        if amount_match:
            return {"amount": float(amount_match.group(1))}
        return {}


def parse_plaid_raw(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                nested = json.loads(data)
                if isinstance(nested, dict):
                    return nested
            except json.JSONDecodeError:
                pass
            return _literal_eval_plaid_repr(data)
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def is_investment_bank_txn(raw: dict[str, Any]) -> bool:
    pfc = raw.get("personal_finance_category") or {}
    primary = str(pfc.get("primary") or "")
    detailed = str(pfc.get("detailed") or "")
    return primary.startswith("INVESTMENT") or detailed.startswith("INVESTMENT")


_PAYMENT_NAME_MARKERS = (
    "PAYMENT THANK YOU",
    "PAYMENT RECEIVED",
    "AUTOMATIC PAYMENT",
    "MOBILE PAYMENT",
    "ONLINE PAYMENT",
    "AUTOPAY",
    "AUTO-PAY",
)


def is_card_payment(raw: dict[str, Any], amount: float, *, payee: str = "") -> bool:
    """True when a credit card transaction is a payment from checking, not a purchase or credit."""
    pfc = raw.get("personal_finance_category") or {}
    detailed = str(pfc.get("detailed") or "")
    if "LOAN_PAYMENTS_CREDIT_CARD" in detailed:
        return True
    label = str(raw.get("name") or raw.get("merchant_name") or payee or "").upper()
    if any(marker in label for marker in _PAYMENT_NAME_MARKERS):
        return True
    if "PAYMENT TO" in label and "CARD" in label:
        return True
    return False
