from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.register import CategoryRuleCreate, CategoryRuleRead, CategoryRuleUpdate
from app.services.categorization import (
    create_rule,
    delete_rule,
    list_rules,
    recategorize_last_days,
    update_rule,
)

router = APIRouter(prefix="/category-rules", tags=["category-rules"])


def _rule_read(rule, applied: int = 0) -> CategoryRuleRead:
    return CategoryRuleRead(
        id=rule.id,
        pattern=rule.pattern,
        category_id=rule.category_id,
        category_name=rule.category.name if rule.category else None,
        match_field=rule.match_field,
        priority=rule.priority,
        amount_direction=rule.amount_direction,
        transactions_updated=applied,
    )


@router.get("", response_model=list[CategoryRuleRead])
def get_category_rules(db: Session = Depends(get_db)) -> list:
    return [_rule_read(r) for r in list_rules(db)]


@router.post("", response_model=CategoryRuleRead, status_code=201)
def post_category_rule(body: CategoryRuleCreate, db: Session = Depends(get_db)):
    rule, applied = create_rule(
        db,
        pattern=body.pattern,
        category_id=body.category_id,
        match_field=body.match_field,
        priority=body.priority,
        amount_direction=body.amount_direction,
    )
    return _rule_read(rule, applied)


@router.patch("/{rule_id}", response_model=CategoryRuleRead)
def patch_category_rule(rule_id: int, body: CategoryRuleUpdate, db: Session = Depends(get_db)):
    try:
        rule = update_rule(
            db,
            rule_id,
            pattern=body.pattern,
            category_id=body.category_id,
            match_field=body.match_field,
            priority=body.priority,
            amount_direction=body.amount_direction,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _rule_read(rule)


@router.delete("/{rule_id}", status_code=204)
def remove_category_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    try:
        delete_rule(db, rule_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/reapply")
def reapply_rules(db: Session = Depends(get_db), days: int = 90) -> dict:
    return recategorize_last_days(db, days=days)

