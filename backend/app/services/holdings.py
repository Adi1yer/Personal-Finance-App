from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype
from app.models.account_mark import AccountMark
from app.models.entry import Entry
from app.models.holding import Holding
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction


@dataclass(frozen=True)
class HoldingSummary:
    ticker: str
    security_name: str
    quantity: Decimal
    cost_basis_total: Decimal
    market_value: Decimal
    gain: Decimal


from app.services.transaction_recognition import extract_ticker


def _ticker_from_txn(txn: Transaction) -> str | None:
    return extract_ticker(
        payee=txn.payee or "",
        security_name=txn.security_name,
        memo=txn.memo,
    )


def _get_or_create_holding(
    db: Session, account_id: int, ticker: str, security_name: str = ""
) -> Holding:
    holding = (
        db.query(Holding)
        .filter(Holding.account_id == account_id, Holding.ticker == ticker.upper())
        .first()
    )
    if holding:
        return holding
    holding = Holding(
        account_id=account_id,
        ticker=ticker.upper(),
        security_name=security_name or ticker.upper(),
        quantity=Decimal("0"),
        cost_basis_total=Decimal("0"),
    )
    db.add(holding)
    db.flush()
    return holding


def apply_investment_txn(db: Session, txn: Transaction, account_id: int) -> None:
    if not txn.investment_type and not txn.investment_subtype:
        return

    subtype = (txn.investment_subtype or txn.investment_type or "").lower()
    ticker = _ticker_from_txn(txn)
    if not ticker:
        return

    qty = Decimal(str(txn.quantity)) if txn.quantity is not None else Decimal("0")
    price = Decimal(str(txn.price)) if txn.price is not None else None
    holding = _get_or_create_holding(
        db, account_id, ticker, txn.security_name or ticker
    )
    if txn.security_name:
        holding.security_name = txn.security_name
    if price is not None and price > 0:
        holding.market_price = price
    holding.as_of_date = txn.txn_date

    entry_amt = Decimal("0")
    for entry in txn.entries:
        if entry.account_id == account_id:
            entry_amt = Decimal(str(entry.amount))
            break

    cash_out = abs(entry_amt) if entry_amt < 0 else Decimal("0")

    if subtype in ("buy", "fee") or (qty > 0 and entry_amt < 0):
        if qty <= 0:
            return
        cost_add = cash_out if cash_out > 0 else qty * (price or Decimal("0"))
        holding.quantity += qty
        holding.cost_basis_total += cost_add
    elif subtype == "sell" or (qty > 0 and entry_amt > 0):
        if qty <= 0:
            return
        if holding.quantity > 0:
            ratio = min(qty / holding.quantity, Decimal("1"))
            holding.cost_basis_total -= holding.cost_basis_total * ratio
            holding.quantity -= qty
            if holding.quantity < 0:
                holding.quantity = Decimal("0")
            if holding.cost_basis_total < 0:
                holding.cost_basis_total = Decimal("0")
    db.flush()


def set_holding_position(
    db: Session,
    account_id: int,
    *,
    ticker: str,
    security_name: str,
    quantity: Decimal,
    cost_basis_total: Decimal,
    market_price: Decimal | None = None,
    as_of_date: date | None = None,
) -> Holding:
    holding = _get_or_create_holding(db, account_id, ticker, security_name)
    holding.security_name = security_name
    holding.quantity = quantity
    holding.cost_basis_total = cost_basis_total
    if market_price is not None:
        holding.market_price = market_price
    holding.as_of_date = as_of_date or date.today()
    db.flush()
    return holding


def cash_ledger_balance(db: Session, account_id: int) -> Decimal:
    raw = db.scalar(
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Transaction, Entry.transaction_id == Transaction.id)
        .where(
            Entry.account_id == account_id,
            Transaction.voided_at.is_(None),
        )
    )
    return Decimal(str(raw or 0))


def _holding_market_value(holding: Holding) -> Decimal:
    if holding.quantity <= 0:
        return Decimal("0")
    if holding.market_price and holding.market_price > 0:
        return holding.quantity * holding.market_price
    if holding.cost_basis_total > 0:
        return holding.cost_basis_total
    return Decimal("0")


def list_holdings(db: Session, account_id: int) -> list[HoldingSummary]:
    holdings = (
        db.query(Holding)
        .filter(Holding.account_id == account_id, Holding.quantity > 0)
        .order_by(Holding.ticker)
        .all()
    )
    result: list[HoldingSummary] = []
    for h in holdings:
        mv = _holding_market_value(h)
        cost = Decimal(str(h.cost_basis_total))
        result.append(
            HoldingSummary(
                ticker=h.ticker,
                security_name=h.security_name,
                quantity=Decimal(str(h.quantity)),
                cost_basis_total=cost,
                market_value=mv,
                gain=mv - cost,
            )
        )
    return result


def plaid_live_balance(db: Session, account_id: int) -> Decimal | None:
    """Latest balance from Plaid accounts API for a linked ledger account."""
    pa = db.query(PlaidAccount).filter(PlaidAccount.account_id == account_id).first()
    if pa and pa.balance_current is not None:
        return Decimal(str(pa.balance_current))
    return None


_CASH_SWEEP_TICKER_PREFIXES = ("QACDS", "QDERQ", "SWEEP", "CASH")


def _is_cash_sweep_ticker(ticker: str) -> bool:
    upper = ticker.upper()
    return any(upper.startswith(prefix) for prefix in _CASH_SWEEP_TICKER_PREFIXES)


def _holdings_portfolio_total(db: Session, account_id: int) -> Decimal:
    return sum((h.market_value for h in list_holdings(db, account_id)), Decimal("0"))


def _cash_from_holdings(db: Session, account_id: int) -> Decimal:
    return sum(
        (
            h.market_value
            for h in list_holdings(db, account_id)
            if _is_cash_sweep_ticker(h.ticker)
        ),
        Decimal("0"),
    )


def _has_institution_priced_holdings(db: Session, account_id: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(Holding)
        .where(
            Holding.account_id == account_id,
            Holding.quantity > 0,
            Holding.market_price.isnot(None),
            Holding.market_price > 0,
        )
    )
    return bool(count)


def _portfolio_value_from_holdings(db: Session, account_id: int) -> tuple[Decimal, Decimal]:
    """Cash plus holdings; uses institution prices when holdings exist, else AccountMark."""
    if _has_institution_priced_holdings(db, account_id):
        total = _holdings_portfolio_total(db, account_id)
        cash = _cash_from_holdings(db, account_id)
        if cash == 0:
            ledger_cash = cash_ledger_balance(db, account_id)
            if ledger_cash > 0:
                cash = ledger_cash
                total += ledger_cash
        return cash, total

    cash = cash_ledger_balance(db, account_id)
    holdings_mv = _holdings_portfolio_total(db, account_id)
    computed = cash + holdings_mv

    mark = db.scalar(
        select(AccountMark.market_value)
        .where(AccountMark.account_id == account_id)
        .order_by(AccountMark.as_of_date.desc())
        .limit(1)
    )
    if mark is not None:
        return cash, Decimal(str(mark))
    return cash, computed


def portfolio_value(db: Session, account_id: int) -> tuple[Decimal, Decimal]:
    """Return (cash_balance, portfolio_value). Prefers Plaid total, then priced holdings."""
    plaid_bal = plaid_live_balance(db, account_id)
    if plaid_bal is not None:
        cash = _cash_from_holdings(db, account_id)
        if cash == 0:
            cash = cash_ledger_balance(db, account_id)
            if cash < 0:
                cash = Decimal("0")
        return cash, abs(plaid_bal)
    if _has_institution_priced_holdings(db, account_id):
        return _portfolio_value_from_holdings(db, account_id)
    cash = cash_ledger_balance(db, account_id)
    return _portfolio_value_from_holdings(db, account_id)


def investment_account_value(
    db: Session, account_id: int, as_of: date | None = None
) -> Decimal:
    """Best available market value for brokerage, retirement, or HSA accounts."""
    if as_of and as_of < date.today():
        mark = db.scalar(
            select(AccountMark.market_value)
            .where(
                AccountMark.account_id == account_id,
                AccountMark.as_of_date <= as_of,
            )
            .order_by(AccountMark.as_of_date.desc())
            .limit(1)
        )
        if mark is not None:
            return Decimal(str(mark))
        return cash_ledger_balance(db, account_id)

    plaid_bal = plaid_live_balance(db, account_id)
    if plaid_bal is not None:
        return abs(plaid_bal)

    if _has_institution_priced_holdings(db, account_id):
        total = _holdings_portfolio_total(db, account_id)
        cash = _cash_from_holdings(db, account_id)
        if cash == 0:
            ledger_cash = cash_ledger_balance(db, account_id)
            if ledger_cash > 0:
                total += ledger_cash
        return total
    _, computed = _portfolio_value_from_holdings(db, account_id)
    return computed


_INVESTMENT_SUBTYPES = frozenset(
    {AccountSubtype.brokerage, AccountSubtype.retirement, AccountSubtype.hsa}
)


def refresh_live_investment_values(db: Session) -> dict[str, int]:
    """
    Re-price linked investment holdings from live market quotes and update account totals.
    Quantities come from the latest Plaid holdings sync; prices are refreshed here.
    """
    from app.config import get_settings
    from app.services.market_quotes import fetch_live_quotes

    settings = get_settings()
    if not getattr(settings, "live_market_quotes_enabled", True):
        return {"quotes_fetched": 0, "prices_updated": 0, "accounts_updated": 0}

    accounts = (
        db.query(Account)
        .filter(
            Account.is_active.is_(True),
            Account.subtype.in_(_INVESTMENT_SUBTYPES),
        )
        .all()
    )
    if not accounts:
        return {"quotes_fetched": 0, "prices_updated": 0, "accounts_updated": 0}

    holdings = (
        db.query(Holding)
        .filter(
            Holding.account_id.in_([a.id for a in accounts]),
            Holding.quantity > 0,
        )
        .all()
    )
    if not holdings:
        return {"quotes_fetched": 0, "prices_updated": 0, "accounts_updated": 0}

    tickers = [h.ticker for h in holdings if not _is_cash_sweep_ticker(h.ticker)]
    quotes = fetch_live_quotes(tickers)
    as_of = date.today()
    prices_updated = 0

    for holding in holdings:
        if _is_cash_sweep_ticker(holding.ticker):
            holding.market_price = Decimal("1")
            holding.as_of_date = as_of
            continue
        price = quotes.get(holding.ticker.upper())
        if price is not None:
            holding.market_price = price
            holding.as_of_date = as_of
            prices_updated += 1

    accounts_updated = 0
    for account in accounts:
        account_holdings = [h for h in holdings if h.account_id == account.id]
        if not account_holdings:
            continue
        has_fresh_quote = any(
            h.as_of_date == as_of
            and h.market_price is not None
            and h.market_price > 0
            and (
                _is_cash_sweep_ticker(h.ticker)
                or h.ticker.upper() in quotes
            )
            for h in account_holdings
        )
        if not has_fresh_quote:
            continue
        total = sum((_holding_market_value(h) for h in account_holdings), Decimal("0"))
        from app.services.plaid_sync import _upsert_account_mark

        _upsert_account_mark(
            db,
            account.id,
            as_of,
            total,
            note="Live market quotes",
        )
        plaid_acct = (
            db.query(PlaidAccount).filter(PlaidAccount.account_id == account.id).first()
        )
        if plaid_acct:
            plaid_acct.balance_current = total
        accounts_updated += 1

    if prices_updated or accounts_updated:
        db.commit()

    return {
        "quotes_fetched": len(quotes),
        "prices_updated": prices_updated,
        "accounts_updated": accounts_updated,
    }


def rebuild_holdings_from_transactions(db: Session, account_id: int) -> None:
    db.query(Holding).filter(Holding.account_id == account_id).delete()
    db.flush()
    txns = (
        db.query(Transaction)
        .join(Transaction.entries)
        .filter(
            Entry.account_id == account_id,
            Transaction.voided_at.is_(None),
        )
        .order_by(Transaction.txn_date.asc(), Transaction.id.asc())
        .all()
    )
    for txn in txns:
        apply_investment_txn(db, txn, account_id)
    db.commit()
