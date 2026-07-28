from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.account import Account
from app.models.account_mark import AccountMark
from app.schemas.account import (
    AccountContributionCreate,
    AccountCreate,
    AccountMarkCreate,
    AccountMarkRead,
    AccountRead,
    AccountUpdate,
)
from app.services.investment_contributions import record_investment_contribution
from app.services.posting import PostingError
from app.services.ledger import account_balance
from app.services.seed import SYSTEM_ACCOUNT_SLUGS, default_tracking_start
from app.services.slug import unique_account_slug

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _account_read(db: Session, acc: Account) -> AccountRead:
    out = AccountRead.model_validate(acc)
    out.balance = account_balance(db, acc.id)
    return out


@router.get("", response_model=list[AccountRead])
def list_accounts(
    include_system: bool = False,
    db: Session = Depends(get_db),
) -> list[AccountRead]:
    q = db.query(Account).filter(Account.is_active.is_(True))
    accounts = q.order_by(Account.name).all()
    result = []
    for acc in accounts:
        if not include_system and acc.slug in SYSTEM_ACCOUNT_SLUGS:
            continue
        result.append(_account_read(db, acc))
    return result


@router.post("", response_model=AccountRead, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db)) -> AccountRead:
    slug = body.slug or unique_account_slug(db, body.name)
    if db.query(Account).filter(Account.slug == slug).first():
        raise HTTPException(400, "Account slug already exists")
    data = body.model_dump(exclude={"slug"})
    acc = Account(
        slug=slug,
        tracking_start_date=default_tracking_start(body.subtype),
        **data,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _account_read(db, acc)


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    body: AccountUpdate,
    db: Session = Depends(get_db),
) -> AccountRead:
    acc = db.get(Account, account_id)
    if not acc or not acc.is_active:
        raise HTTPException(404, "Account not found")
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and acc.slug not in SYSTEM_ACCOUNT_SLUGS:
        pass
    if "name" in updates:
        acc.name = updates["name"]
    if "account_type" in updates:
        acc.account_type = updates["account_type"]
    if "subtype" in updates:
        acc.subtype = updates["subtype"]
    if "institution_id" in updates:
        acc.institution_id = updates["institution_id"]
    if "sync_source" in updates:
        acc.sync_source = updates["sync_source"]
    if "tracking_start_date" in updates:
        acc.tracking_start_date = updates["tracking_start_date"]
    db.commit()
    db.refresh(acc)
    return _account_read(db, acc)


@router.delete("/{account_id}", status_code=204)
def archive_account(account_id: int, db: Session = Depends(get_db)) -> None:
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if acc.slug in SYSTEM_ACCOUNT_SLUGS:
        raise HTTPException(400, "Cannot archive a system account")
    acc.is_active = False
    db.commit()


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)) -> AccountRead:
    acc = db.get(Account, account_id)
    if not acc or not acc.is_active:
        raise HTTPException(404, "Account not found")
    return _account_read(db, acc)


@router.post("/marks", response_model=AccountMarkRead, status_code=201)
def create_account_mark(body: AccountMarkCreate, db: Session = Depends(get_db)) -> AccountMark:
    as_of = date.fromisoformat(body.as_of_date)
    existing = (
        db.query(AccountMark)
        .filter(AccountMark.account_id == body.account_id, AccountMark.as_of_date == as_of)
        .first()
    )
    if existing:
        existing.market_value = body.market_value
        existing.note = body.note
        mark = existing
    else:
        mark = AccountMark(
            account_id=body.account_id,
            as_of_date=as_of,
            market_value=body.market_value,
            note=body.note,
        )
        db.add(mark)
    db.commit()
    db.refresh(mark)

    if body.total_contributions is not None or body.contribution_amount is not None:
        total = body.total_contributions if body.total_contributions is not None else body.contribution_amount
        try:
            from app.services.investment_contributions import set_ytd_total_contributions

            set_ytd_total_contributions(
                db,
                account_id=body.account_id,
                total=total,
                as_of=as_of,
                memo=body.note,
            )
        except PostingError as e:
            raise HTTPException(400, str(e)) from e

    return AccountMarkRead(
        id=mark.id,
        account_id=mark.account_id,
        as_of_date=mark.as_of_date.isoformat(),
        market_value=mark.market_value,
        note=mark.note,
    )


@router.post("/contributions", status_code=201)
def create_account_contribution(
    body: AccountContributionCreate, db: Session = Depends(get_db)
) -> dict:
    try:
        return record_investment_contribution(
            db,
            account_id=body.account_id,
            amount=body.amount,
            txn_date=date.fromisoformat(body.txn_date),
            memo=body.memo,
        )
    except PostingError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{account_id}/fund-holdings")
def list_fund_holdings(account_id: int, db: Session = Depends(get_db)) -> list[dict]:
    from app.models.manual_fund_holding import ManualFundHolding

    rows = db.query(ManualFundHolding).filter(ManualFundHolding.account_id == account_id).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "allocation_pct": str(r.allocation_pct) if r.allocation_pct is not None else None,
            "quantity": str(r.quantity) if r.quantity is not None else None,
        }
        for r in rows
    ]


@router.post("/{account_id}/fund-holdings", status_code=201)
def create_fund_holding(
    account_id: int,
    body: dict,
    db: Session = Depends(get_db),
) -> dict:
    from decimal import Decimal

    from app.models.manual_fund_holding import ManualFundHolding

    row = ManualFundHolding(
        account_id=account_id,
        ticker=str(body["ticker"]).upper(),
        allocation_pct=Decimal(str(body["allocation_pct"])) if body.get("allocation_pct") else None,
        quantity=Decimal(str(body["quantity"])) if body.get("quantity") else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "ticker": row.ticker}


@router.delete("/fund-holdings/{holding_id}", status_code=204)
def delete_fund_holding(holding_id: int, db: Session = Depends(get_db)) -> None:
    from app.models.manual_fund_holding import ManualFundHolding

    row = db.get(ManualFundHolding, holding_id)
    if not row:
        raise HTTPException(404, "Holding not found")
    db.delete(row)
    db.commit()
