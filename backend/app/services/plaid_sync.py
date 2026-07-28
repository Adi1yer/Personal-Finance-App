from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.holding import Holding
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.card_payments import (
    CARD_PAYMENT_DATE_TOLERANCE_DAYS,
    find_card_payment_txn,
    repair_duplicate_card_payments,
    resolve_card_account_from_payment,
)
from app.services.categorization import (
    is_card_payment,
    is_investment_bank_txn,
    parse_plaid_raw,
    resolve_category_id,
)
from app.services.encryption import decrypt_value
from app.services.posting import create_transaction
from app.services.seed import default_tracking_start

INVESTMENT_SUBTYPES = frozenset({"brokerage", "retirement"})
INVESTMENT_SYNC_LOOKBACK_DAYS = 365 * 10


def _plaid_client():
    settings = get_settings()
    import plaid
    from plaid.api import plaid_api

    host = (
        plaid.Environment.Sandbox
        if settings.plaid_env == "sandbox"
        else plaid.Environment.Production
    )
    configuration = plaid.Configuration(
        host=host,
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def sync_due(last_at: datetime | None, interval_days: int) -> bool:
    if last_at is None:
        return True
    normalized = _as_utc(last_at)
    if normalized is None:
        return True
    elapsed = _utc_now() - normalized
    return elapsed >= timedelta(days=interval_days)


def effective_redirect_uri(override: str | None = None) -> str | None:
    settings = get_settings()
    uri = (override or settings.plaid_redirect_uri or "").strip()
    if uri:
        return uri
    host = settings.api_host or "127.0.0.1"
    port = settings.api_port or 8000
    path = "/oauth/plaid.html"
    if settings.plaid_env == "production":
        return f"https://{host}:{port}{path}"
    return f"http://{host}:{port}{path}"


def create_link_token(
    redirect_uri: str | None = None,
    *,
    client_user_id: str = "local-user",
) -> str:
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products

    client = _plaid_client()
    uri = effective_redirect_uri(redirect_uri)
    kwargs: dict = {
        "products": [Products("transactions"), Products("investments")],
        "client_name": "Personal Finance",
        "country_codes": [CountryCode("US")],
        "language": "en",
        "user": LinkTokenCreateRequestUser(client_user_id=str(client_user_id)[:256]),
    }
    if uri:
        kwargs["redirect_uri"] = uri
    request = LinkTokenCreateRequest(**kwargs)
    response = client.link_token_create(request)
    return response["link_token"]


def _plaid_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    inner = getattr(value, "value", None)
    if inner is not None:
        return str(inner)
    return str(value)


def _plaid_to_dict(obj: object) -> dict:
    """Plaid SDK models are not dicts; normalize for staging and JSON."""
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Cannot convert {type(obj).__name__} to dict")


def _plaid_field(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _plaid_balance(acct: dict) -> Decimal | None:
    balances = acct.get("balances") or {}
    plaid_type = str(acct.get("type") or "").lower()
    if plaid_type == "depository":
        raw = balances.get("available")
        if raw is None:
            raw = balances.get("current")
    else:
        raw = balances.get("current")
        if raw is None:
            raw = balances.get("available")
    if raw is None:
        return None
    return Decimal(str(raw))


def _apply_plaid_account_fields(target: PlaidAccount, acct: dict) -> None:
    target.name = acct.get("name", target.name)
    target.official_name = _plaid_str(acct.get("official_name"))
    target.mask = _plaid_str(acct.get("mask"))
    target.plaid_type = _plaid_str(acct.get("type"))
    target.plaid_subtype = _plaid_str(acct.get("subtype"))
    target.balance_current = _plaid_balance(acct)


def _before_tracking_start(db: Session, ledger_id: int, txn_date: date) -> bool:
    acc = db.get(Account, ledger_id)
    if not acc or not acc.tracking_start_date:
        return False
    return txn_date < acc.tracking_start_date


def exchange_public_token(db: Session, public_token: str) -> PlaidItem:
    from plaid.model.item_public_token_exchange_request import (
        ItemPublicTokenExchangeRequest,
    )

    from app.services.encryption import encrypt_value

    client = _plaid_client()
    exchange = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token = exchange["access_token"]
    item_id = exchange["item_id"]

    existing = db.query(PlaidItem).filter(PlaidItem.item_id == item_id).first()
    if existing:
        existing.access_token_encrypted = encrypt_value(access_token)
        db.commit()
        _sync_accounts_for_item(db, existing)
        return existing

    item = PlaidItem(
        item_id=item_id,
        access_token_encrypted=encrypt_value(access_token),
        institution_name="Linked institution",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _sync_accounts_for_item(db, item)
    return item


def _sync_accounts_for_item(db: Session, item: PlaidItem) -> None:
    from plaid.model.accounts_get_request import AccountsGetRequest

    client = _plaid_client()
    token = decrypt_value(item.access_token_encrypted)
    response = client.accounts_get(AccountsGetRequest(access_token=token))
    for acct in response["accounts"]:
        plaid_id = acct["account_id"]
        existing = (
            db.query(PlaidAccount).filter(PlaidAccount.plaid_account_id == plaid_id).first()
        )
        if existing:
            _apply_plaid_account_fields(existing, acct)
        else:
            pa = PlaidAccount(
                plaid_item_id=item.id,
                plaid_account_id=plaid_id,
                name=acct.get("name", "Account"),
            )
            _apply_plaid_account_fields(pa, acct)
            db.add(pa)
    db.commit()


def _stage_txn(
    db: Session,
    *,
    external_id: str,
    plaid_acct: PlaidAccount | None,
    txn_date: date,
    amount: Decimal,
    payee: str,
    raw_json: str,
) -> str:
    """Stage a transaction. Returns 'staged', 'skipped', or 'before_cutoff'."""
    if plaid_acct and plaid_acct.account_id:
        if _before_tracking_start(db, plaid_acct.account_id, txn_date):
            return "before_cutoff"
    existing = (
        db.query(ImportStaging)
        .filter(ImportStaging.external_id == external_id)
        .first()
    )
    if existing:
        return "skipped"
    already_posted = (
        db.query(Transaction)
        .filter(
            Transaction.external_id == external_id,
            Transaction.voided_at.is_(None),
        )
        .first()
    )
    if already_posted:
        return "skipped"
    from app.services.plaid_dedup import find_plaid_activity_duplicate

    if plaid_acct and plaid_acct.account_id:
        duplicate = find_plaid_activity_duplicate(
            db,
            plaid_acct.account_id,
            payee,
            amount,
            txn_date,
            exclude_external_id=external_id,
            include_voided_recorded=True,
        )
        if duplicate:
            return "skipped"
    row = ImportStaging(
        plaid_account_id=plaid_acct.id if plaid_acct else None,
        external_id=external_id,
        txn_date=txn_date,
        amount=amount,
        payee=payee,
        raw_json=raw_json,
        status=StagingStatus.pending,
    )
    db.add(row)
    return "staged"


def sync_transactions(db: Session, plaid_item_id: int | None = None) -> dict[str, int]:
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    client = _plaid_client()
    items = db.query(PlaidItem).all()
    if plaid_item_id:
        items = [i for i in items if i.id == plaid_item_id]

    staged = posted = skipped = cutoff_skipped = 0
    for item in items:
        token = decrypt_value(item.access_token_encrypted)
        cursor = item.transactions_cursor
        has_more = True
        while has_more:
            req_kwargs = {"access_token": token}
            if cursor:
                req_kwargs["cursor"] = cursor
            req = TransactionsSyncRequest(**req_kwargs)
            resp = client.transactions_sync(req)

            for txn in resp.get("added", []):
                plaid_acct = (
                    db.query(PlaidAccount)
                    .filter(PlaidAccount.plaid_account_id == txn["account_id"])
                    .first()
                )
                if plaid_acct and plaid_acct.account_id:
                    ledger = db.get(Account, plaid_acct.account_id)
                    if ledger and ledger.subtype.value in INVESTMENT_SUBTYPES:
                        raw = parse_plaid_raw(json.dumps(txn, default=str))
                        if is_investment_bank_txn(raw):
                            skipped += 1
                            continue

                result = _stage_txn(
                    db,
                    external_id=txn["transaction_id"],
                    plaid_acct=plaid_acct,
                    txn_date=date.fromisoformat(str(txn["date"])),
                    amount=Decimal(str(txn["amount"])) * -1,
                    payee=txn.get("merchant_name") or txn.get("name", ""),
                    raw_json=json.dumps(txn, default=str),
                )
                if result == "staged":
                    staged += 1
                elif result == "before_cutoff":
                    cutoff_skipped += 1
                else:
                    skipped += 1

            for txn in resp.get("modified", []):
                _handle_modified_txn(db, txn)

            for txn in resp.get("removed", []):
                _handle_removed_txn(db, txn)

            cursor = resp.get("next_cursor")
            has_more = resp.get("has_more", False)

        item.transactions_cursor = cursor
        item.last_synced_at = _utc_now()
        db.commit()
        posted += _post_staged_for_item(db, item)

    return {
        "staged": staged,
        "posted": posted,
        "skipped": skipped,
        "cutoff_skipped": cutoff_skipped,
    }


def _handle_modified_txn(db: Session, txn: dict) -> None:
    external_id = txn["transaction_id"]
    existing_txn = (
        db.query(Transaction)
        .filter(Transaction.external_id == external_id)
        .first()
    )
    if not existing_txn:
        from app.services.plaid_dedup import find_semantic_duplicate

        plaid_acct = (
            db.query(PlaidAccount)
            .filter(PlaidAccount.plaid_account_id == str(txn["account_id"]))
            .first()
        )
        if plaid_acct and plaid_acct.account_id:
            payee = txn.get("merchant_name") or txn.get("name", "")
            amt = Decimal(str(txn["amount"])) * -1
            txn_date = date.fromisoformat(str(txn["date"]))
            existing_txn = find_semantic_duplicate(
                db,
                plaid_acct.account_id,
                payee,
                amt,
                txn_date,
            )
            if existing_txn:
                existing_txn.external_id = external_id
    if not existing_txn:
        return
    existing_txn.txn_date = date.fromisoformat(str(txn["date"]))
    existing_txn.payee = txn.get("merchant_name") or txn.get("name", "")
    amt = Decimal(str(txn["amount"])) * -1
    for entry in existing_txn.entries:
        if entry.amount > 0:
            entry.amount = amt if amt > 0 else entry.amount
        else:
            entry.amount = amt if amt < 0 else entry.amount
    db.commit()


def _handle_removed_txn(db: Session, txn: dict) -> None:
    external_id = txn.get("transaction_id")
    if not external_id:
        return
    existing_txn = (
        db.query(Transaction)
        .filter(Transaction.external_id == external_id)
        .first()
    )
    if existing_txn and existing_txn.voided_at is None:
        existing_txn.voided_at = _utc_now()
        existing_txn.external_id = None
        db.commit()


def sync_investment_transactions(
    db: Session, plaid_item_id: int | None = None
) -> dict[str, int]:
    from plaid.model.investments_transactions_get_request import (
        InvestmentsTransactionsGetRequest,
    )
    from plaid.model.investments_transactions_get_request_options import (
        InvestmentsTransactionsGetRequestOptions,
    )

    client = _plaid_client()
    items = db.query(PlaidItem).all()
    if plaid_item_id:
        items = [i for i in items if i.id == plaid_item_id]

    staged = posted = skipped = 0
    end = date.today()

    for item in items:
        if item.last_investment_sync_at:
            start = item.last_investment_sync_at.date() - timedelta(days=7)
        else:
            start = end - timedelta(days=INVESTMENT_SYNC_LOOKBACK_DAYS)

        token = decrypt_value(item.access_token_encrypted)
        offset = 0
        total = None
        while total is None or offset < total:
            try:
                resp = client.investments_transactions_get(
                    InvestmentsTransactionsGetRequest(
                        access_token=token,
                        start_date=start,
                        end_date=end,
                        options=InvestmentsTransactionsGetRequestOptions(
                            count=100,
                            offset=offset,
                        ),
                    )
                )
            except Exception:
                break

            securities = {
                _plaid_to_dict(s)["security_id"]: _plaid_to_dict(s)
                for s in resp.get("securities", [])
            }

            for txn in resp.get("investment_transactions", []):
                txn_dict = _plaid_to_dict(txn)
                external_id = f"inv:{txn_dict['investment_transaction_id']}"
                plaid_acct = (
                    db.query(PlaidAccount)
                    .filter(PlaidAccount.plaid_account_id == txn_dict["account_id"])
                    .first()
                )
                if not plaid_acct or not plaid_acct.account_id:
                    skipped += 1
                    continue
                ledger = db.get(Account, plaid_acct.account_id)
                if not ledger or ledger.subtype.value not in INVESTMENT_SUBTYPES:
                    skipped += 1
                    continue

                result = _stage_txn(
                    db,
                    external_id=external_id,
                    plaid_acct=plaid_acct,
                    txn_date=date.fromisoformat(str(txn_dict["date"])),
                    amount=Decimal(str(txn_dict["amount"])) * -1,
                    payee=txn_dict.get("name", "Investment transaction"),
                    raw_json=json.dumps(
                        {**txn_dict, "_securities": securities}, default=str
                    ),
                )
                if result == "staged":
                    staged += 1
                else:
                    skipped += 1

            total = resp.get("total_investment_transactions", 0)
            offset += len(resp.get("investment_transactions", []))
            if not resp.get("investment_transactions"):
                break

        item.last_investment_sync_at = _utc_now()
        db.commit()
        posted += _post_staged_for_item(db, item)

    return {
        "investment_staged": staged,
        "investment_posted": posted,
        "investment_skipped": skipped,
    }


def _upsert_account_mark(
    db: Session,
    account_id: int,
    as_of: date,
    market_value: Decimal,
    note: str,
) -> None:
    existing = (
        db.query(AccountMark)
        .filter(AccountMark.account_id == account_id, AccountMark.as_of_date == as_of)
        .first()
    )
    if existing:
        existing.market_value = market_value
        existing.note = note
    else:
        db.add(
            AccountMark(
                account_id=account_id,
                as_of_date=as_of,
                market_value=market_value,
                note=note,
            )
        )


def sync_investment_holdings(db: Session, plaid_item_id: int | None = None) -> dict[str, int]:
    from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest

    from app.services.holdings import set_holding_position

    client = _plaid_client()
    items = db.query(PlaidItem).all()
    if plaid_item_id:
        items = [i for i in items if i.id == plaid_item_id]

    updated = 0
    positions_updated = 0
    as_of = date.today()

    for item in items:
        token = decrypt_value(item.access_token_encrypted)
        try:
            resp = client.investments_holdings_get(
                InvestmentsHoldingsGetRequest(access_token=token)
            )
        except Exception:
            continue

        resp_dict = _plaid_to_dict(resp)
        securities_by_id: dict[str, dict] = {}
        for sec in resp_dict.get("securities", []):
            s = _plaid_to_dict(sec)
            sid = s.get("security_id")
            if sid:
                securities_by_id[str(sid)] = s

        totals: dict[str, Decimal] = {}
        seen_by_ledger: dict[int, set[str]] = {}
        for holding in resp_dict.get("holdings", []):
            h = _plaid_to_dict(holding)
            plaid_account_id = h.get("account_id")
            value = h.get("institution_value")
            if plaid_account_id is None:
                continue
            if value is not None:
                totals[str(plaid_account_id)] = totals.get(
                    str(plaid_account_id), Decimal("0")
                ) + Decimal(str(value))

            plaid_acct = (
                db.query(PlaidAccount)
                .filter(PlaidAccount.plaid_account_id == str(plaid_account_id))
                .first()
            )
            if not plaid_acct or not plaid_acct.account_id:
                continue
            ledger = db.get(Account, plaid_acct.account_id)
            if not ledger or ledger.subtype.value not in INVESTMENT_SUBTYPES:
                continue

            security_id = h.get("security_id")
            sec = securities_by_id.get(str(security_id), {}) if security_id else {}
            ticker = (
                sec.get("ticker_symbol")
                or sec.get("name")
                or str(security_id or "UNKNOWN")
            )
            ticker = str(ticker).upper()[:32]
            security_name = str(sec.get("name") or ticker)
            qty = Decimal(str(h.get("quantity", 0)))
            if qty <= 0:
                continue
            institution_price = h.get("institution_price")
            market_price = (
                Decimal(str(institution_price)) if institution_price is not None else None
            )
            cost_basis = h.get("cost_basis")
            cost_total = (
                Decimal(str(cost_basis))
                if cost_basis is not None
                else (qty * market_price if market_price else Decimal("0"))
            )
            set_holding_position(
                db,
                ledger.id,
                ticker=ticker,
                security_name=security_name,
                quantity=qty,
                cost_basis_total=cost_total,
                market_price=market_price,
                as_of_date=as_of,
            )
            seen_by_ledger.setdefault(ledger.id, set()).add(ticker)
            positions_updated += 1

        for ledger_id, tickers in seen_by_ledger.items():
            stale = (
                db.query(Holding)
                .filter(Holding.account_id == ledger_id, Holding.ticker.notin_(tickers))
                .all()
            )
            for holding in stale:
                db.delete(holding)

        for plaid_acct in db.query(PlaidAccount).filter(PlaidAccount.plaid_item_id == item.id).all():
            if not plaid_acct.account_id:
                continue
            ledger = db.get(Account, plaid_acct.account_id)
            if not ledger or ledger.subtype.value not in INVESTMENT_SUBTYPES:
                continue
            if ledger.id in seen_by_ledger:
                continue
            for holding in db.query(Holding).filter(Holding.account_id == ledger.id).all():
                db.delete(holding)

        for plaid_account_id, total in totals.items():
            plaid_acct = (
                db.query(PlaidAccount)
                .filter(PlaidAccount.plaid_account_id == plaid_account_id)
                .first()
            )
            if not plaid_acct or not plaid_acct.account_id:
                continue
            ledger = db.get(Account, plaid_acct.account_id)
            if not ledger or ledger.subtype.value not in INVESTMENT_SUBTYPES:
                continue
            _upsert_account_mark(
                db,
                ledger.id,
                as_of,
                total,
                note="Plaid holdings sync",
            )
            plaid_acct.balance_current = total
            updated += 1

        item.last_holdings_sync_at = _utc_now()
        db.commit()

    return {"holdings_updated": updated, "positions_updated": positions_updated}


def sync_all(db: Session, *, force: bool = False) -> dict[str, int | bool]:
    from app.services.opening_balances import seed_opening_balances

    settings = get_settings()
    items = db.query(PlaidItem).all()
    if not items:
        return {
            "ran": False,
            "staged": 0,
            "posted": 0,
            "skipped": 0,
            "investment_staged": 0,
            "investment_posted": 0,
            "investment_skipped": 0,
            "holdings_updated": 0,
        }

    for item in items:
        _sync_accounts_for_item(db, item)

    if items:
        from app.services.plaid_dedup import (
            cleanup_satisfied_staging,
            repair_duplicate_plaid_transactions,
        )

        cleanup_satisfied_staging(db)
        pre_dup = repair_duplicate_plaid_transactions(db)
    else:
        pre_dup = {"voided": 0, "opening_updated": 0}

    transactions_due = force or any(
        sync_due(item.last_synced_at, settings.plaid_transactions_sync_days) for item in items
    )
    holdings_due = force or any(
        sync_due(item.last_holdings_sync_at, settings.plaid_holdings_sync_days) for item in items
    )

    result: dict[str, int | bool] = {
        "ran": transactions_due or holdings_due,
        "staged": 0,
        "posted": 0,
        "skipped": 0,
        "cutoff_skipped": 0,
        "investment_staged": 0,
        "investment_posted": 0,
        "investment_skipped": 0,
        "holdings_updated": 0,
        "plaid_duplicate_repair_pre": pre_dup.get("voided", 0),
    }

    if transactions_due:
        txn = sync_transactions(db)
        inv = sync_investment_transactions(db)
        result.update(txn)
        result["investment_staged"] = inv["investment_staged"]
        result["investment_posted"] = inv["investment_posted"]
        result["investment_skipped"] = inv["investment_skipped"]
        from app.services.posting_repair import repair_card_cross_posted_transactions

        repair = repair_card_cross_posted_transactions(db)
        result["card_cross_post_repair"] = repair
        dup = repair_duplicate_card_payments(db)
        result["duplicate_card_payment_repair"] = dup
        from app.services.plaid_dedup import (
            cleanup_satisfied_staging,
            repair_duplicate_plaid_transactions,
        )

        plaid_dup = repair_duplicate_plaid_transactions(db)
        result["plaid_duplicate_repair"] = plaid_dup
        staging_cleanup = cleanup_satisfied_staging(db)
        result["staging_cleanup"] = staging_cleanup

    for item in items:
        _sync_accounts_for_item(db, item)

    if holdings_due:
        holdings = sync_investment_holdings(db)
        result["holdings_updated"] = holdings["holdings_updated"]

    if force or holdings_due:
        from app.services.holdings import refresh_live_investment_values

        live = refresh_live_investment_values(db)
        result["live_quotes_fetched"] = live.get("quotes_fetched", 0)
        result["live_prices_updated"] = live.get("prices_updated", 0)
        result["live_accounts_updated"] = live.get("accounts_updated", 0)

    if transactions_due or holdings_due:
        opening = seed_opening_balances(db)
        result["opening_created"] = opening.get("created", 0)
        result["opening_updated"] = opening.get("updated", 0)

    return result


def run_scheduled_sync(db: Session) -> dict[str, int | bool]:
    return sync_all(db, force=False)


def _post_staged_for_item(db: Session, item: PlaidItem) -> int:
    pending = (
        db.query(ImportStaging)
        .filter(ImportStaging.status == StagingStatus.pending)
        .all()
    )
    count = 0
    for row in pending:
        if not row.plaid_account_id:
            continue
        plaid_acct = db.get(PlaidAccount, row.plaid_account_id)
        if not plaid_acct or not plaid_acct.account_id:
            continue
        if plaid_acct.plaid_item_id != item.id:
            continue
        ledger = db.get(Account, plaid_acct.account_id)
        if not ledger:
            continue
        if _before_tracking_start(db, ledger.id, row.txn_date):
            row.status = StagingStatus.skipped
            continue

        if _post_staged_row(db, row, ledger, plaid_acct):
            row.status = StagingStatus.posted
            count += 1
        else:
            row.status = StagingStatus.skipped
    db.commit()
    return count


def _post_staged_row(
    db: Session, row: ImportStaging, ledger: Account, plaid_acct: PlaidAccount
) -> bool:
    """Post a staged row. Returns True when a new ledger transaction was created."""
    existing = (
        db.query(Transaction)
        .filter(
            Transaction.external_id == row.external_id,
            Transaction.voided_at.is_(None),
        )
        .first()
    )
    if existing:
        return False

    from app.services.plaid_dedup import find_plaid_activity_duplicate

    duplicate = find_plaid_activity_duplicate(
        db,
        ledger.id,
        row.payee,
        row.amount,
        row.txn_date,
        exclude_staging_id=row.id,
    )
    if duplicate:
        return False

    raw = parse_plaid_raw(row.raw_json)
    amt = Decimal(str(row.amount))
    inv_type = raw.get("type")
    inv_subtype = raw.get("subtype")
    security_id = raw.get("security_id")
    security_name = None
    is_cash_equivalent = False
    if security_id and raw.get("_securities"):
        sec = raw["_securities"].get(security_id, {})
        security_name = sec.get("name") or sec.get("ticker_symbol")
        is_cash_equivalent = bool(sec.get("is_cash_equivalent"))

    from app.services.investment_contribution_detect import looks_like_external_contribution

    if looks_like_external_contribution(
        payee=row.payee or "",
        memo=str(raw.get("name") or ""),
        investment_subtype=str(inv_subtype) if inv_subtype else None,
        amount=amt,
        is_cash_equivalent=is_cash_equivalent,
        raw=raw,
    ):
        inv_type = "cash"
        inv_subtype = "contribution"
        amt = abs(amt)

    category_id = resolve_category_id(
        db,
        payee=row.payee,
        memo=raw.get("name"),
        raw_json=row.raw_json,
        investment_subtype=str(inv_subtype) if inv_subtype else None,
        investment_type=str(inv_type) if inv_type else None,
        security_name=security_name,
        amount=amt,
        account_subtype=ledger.subtype.value,
    )

    extra = {
        "investment_type": str(inv_type) if inv_type else None,
        "investment_subtype": str(inv_subtype) if inv_subtype else None,
        "security_name": security_name,
        "quantity": Decimal(str(raw["quantity"])) if raw.get("quantity") is not None else None,
        "price": Decimal(str(raw["price"])) if raw.get("price") is not None else None,
        "memo": raw.get("name"),
    }

    if ledger.subtype == AccountSubtype.checking:
        plaid_amount = float(raw.get("amount", row.amount))
        if is_card_payment(raw, plaid_amount, payee=row.payee or ""):
            payment_amount = abs(amt)
            card_acct = resolve_card_account_from_payment(db, row.payee or "")
            existing = find_card_payment_txn(
                db,
                row.txn_date,
                payment_amount,
                card_acct.id if card_acct else None,
                date_tolerance_days=CARD_PAYMENT_DATE_TOLERANCE_DAYS,
            )
            if existing:
                return False
            if card_acct:
                create_transaction(
                    db,
                    TransactionCreate(
                        txn_date=row.txn_date,
                        payee=row.payee or "Card payment",
                        memo=extra.get("memo"),
                        external_id=row.external_id,
                        entries=[
                            EntryLine(account_id=ledger.id, amount=amt),
                            EntryLine(
                                account_id=card_acct.id,
                                amount=-amt,
                                category_id=category_id,
                            ),
                        ],
                    ),
                    source=TransactionSource.plaid,
                )
                return True
            return False

    if ledger.subtype == AccountSubtype.credit_card:
        plaid_amount = float(raw.get("amount", row.amount))
        if is_card_payment(raw, plaid_amount, payee=row.payee or ""):
            existing = find_card_payment_txn(
                db,
                row.txn_date,
                abs(amt),
                ledger.id,
                date_tolerance_days=CARD_PAYMENT_DATE_TOLERANCE_DAYS,
            )
            if existing:
                return False
            checking = _first_checking(db)
            if checking:
                create_transaction(
                    db,
                    TransactionCreate(
                        txn_date=row.txn_date,
                        payee=row.payee or "Card payment",
                        memo=extra.get("memo"),
                        external_id=row.external_id,
                        entries=[
                            EntryLine(account_id=ledger.id, amount=abs(amt)),
                            EntryLine(account_id=checking.id, amount=-abs(amt)),
                        ],
                    ),
                    source=TransactionSource.plaid,
                )
                return True
        expense_acct = _get_expense_account(db)
        if expense_acct:
            create_transaction(
                db,
                TransactionCreate(
                    txn_date=row.txn_date,
                    payee=row.payee,
                    memo=extra.get("memo"),
                    external_id=row.external_id,
                    entries=[
                        EntryLine(
                            account_id=expense_acct.id,
                            amount=abs(amt),
                            category_id=category_id,
                        ),
                        EntryLine(account_id=ledger.id, amount=-abs(amt)),
                    ],
                ),
                source=TransactionSource.plaid,
            )
            return True
        return False

    offset_id = _offset_account(db, ledger.id, category_id)
    entries = [
        EntryLine(account_id=ledger.id, amount=amt),
        EntryLine(account_id=offset_id, amount=-amt, category_id=category_id),
    ]
    txn_create = TransactionCreate(
        txn_date=row.txn_date,
        payee=row.payee,
        memo=extra.get("memo"),
        external_id=row.external_id,
        entries=entries,
    )
    txn = create_transaction(db, txn_create, source=TransactionSource.plaid)
    if extra["investment_type"]:
        txn.investment_type = extra["investment_type"]
        txn.investment_subtype = extra["investment_subtype"]
        txn.security_name = extra["security_name"]
        txn.quantity = extra["quantity"]
        txn.price = extra["price"]
        db.commit()
        if ledger.subtype in (AccountSubtype.brokerage, AccountSubtype.retirement, AccountSubtype.hsa):
            from app.services.holdings import apply_investment_txn

            apply_investment_txn(db, txn, ledger.id)
            db.commit()
    return True


def _first_checking(db: Session) -> Account | None:
    return (
        db.query(Account)
        .filter(Account.subtype == AccountSubtype.checking, Account.is_active.is_(True))
        .first()
    )


def _get_expense_account(db: Session) -> Account | None:
    return db.query(Account).filter(Account.slug == "uncategorized_expense").first()


def _offset_account(db: Session, ledger_account_id: int, category_id: int | None) -> int:
    acc = db.get(Account, ledger_account_id)
    if category_id:
        from app.models.category import Category, CategoryType

        cat = db.get(Category, category_id)
        if cat and cat.category_type == CategoryType.income:
            income = db.query(Account).filter(Account.slug == "other_income").first()
            if income:
                return income.id
    uncategorized = _get_expense_account(db)
    if uncategorized:
        return uncategorized.id
    raise ValueError("Missing offset accounts; run seed-accounts")


def _infer_ledger_types(pa: PlaidAccount) -> tuple[AccountType, AccountSubtype]:
    plaid_type = (pa.plaid_type or "").lower()
    plaid_subtype = (pa.plaid_subtype or "").lower()

    if plaid_type == "credit":
        return AccountType.liability, AccountSubtype.credit_card
    if plaid_type == "investment":
        if plaid_subtype in {"401k", "401a", "403b", "457b", "pension", "ira", "roth", "roth 401k"}:
            return AccountType.asset, AccountSubtype.retirement
        if plaid_subtype == "hsa":
            return AccountType.asset, AccountSubtype.hsa
        return AccountType.asset, AccountSubtype.brokerage
    if plaid_subtype == "checking":
        return AccountType.asset, AccountSubtype.checking
    if plaid_subtype == "savings":
        return AccountType.asset, AccountSubtype.checking
    return AccountType.asset, AccountSubtype.checking


def plaid_status(db: Session) -> dict:
    settings = get_settings()
    count = db.query(PlaidItem).count()
    items = db.query(PlaidItem).all()
    last_txn = max((i.last_synced_at for i in items if i.last_synced_at), default=None)
    last_holdings = max(
        (i.last_holdings_sync_at for i in items if i.last_holdings_sync_at), default=None
    )
    return {
        "enabled": settings.plaid_enabled,
        "configured": settings.plaid_configured,
        "env": settings.plaid_env,
        "item_count": count,
        "transactions_sync_days": settings.plaid_transactions_sync_days,
        "holdings_sync_days": settings.plaid_holdings_sync_days,
        "cloud_scheduler_enabled": settings.cloud_scheduler_enabled,
        "last_transactions_sync_at": last_txn.isoformat() if last_txn else None,
        "last_holdings_sync_at": last_holdings.isoformat() if last_holdings else None,
    }


def list_plaid_accounts(db: Session) -> list[dict]:
    rows = db.query(PlaidAccount).all()
    result = []
    for pa in rows:
        ledger = pa.ledger_account
        item = pa.plaid_item
        result.append(
            {
                "id": pa.id,
                "plaid_account_id": pa.plaid_account_id,
                "name": pa.name,
                "official_name": pa.official_name,
                "mask": pa.mask,
                "balance_current": str(pa.balance_current) if pa.balance_current is not None else None,
                "plaid_type": pa.plaid_type,
                "plaid_subtype": pa.plaid_subtype,
                "institution_name": item.institution_name if item else None,
                "ledger_account_id": pa.account_id,
                "ledger_account_name": ledger.name if ledger else None,
            }
        )
    return result


def map_plaid_account(
    db: Session,
    plaid_account_id: int,
    *,
    ledger_account_id: int | None = None,
    create_ledger_account: bool = False,
    ledger_account_name: str | None = None,
    account_type: str | None = None,
    subtype: str | None = None,
) -> PlaidAccount:
    from app.services.slug import unique_account_slug

    pa = db.get(PlaidAccount, plaid_account_id)
    if not pa:
        raise ValueError("Plaid account not found")

    if create_ledger_account:
        name = ledger_account_name or pa.name
        if account_type and subtype:
            atype = AccountType(account_type)
            sub = AccountSubtype(subtype)
        else:
            atype, sub = _infer_ledger_types(pa)
        ledger = Account(
            name=name,
            slug=unique_account_slug(db, name),
            account_type=atype,
            subtype=sub,
            sync_source=SyncSource.plaid,
            tracking_start_date=default_tracking_start(sub),
        )
        db.add(ledger)
        db.flush()
        pa.account_id = ledger.id
    elif ledger_account_id is not None:
        ledger = db.get(Account, ledger_account_id)
        if not ledger:
            raise ValueError("Ledger account not found")
        pa.account_id = ledger_account_id
        ledger.sync_source = SyncSource.plaid
        if ledger.tracking_start_date is None and ledger.subtype != AccountSubtype.brokerage:
            ledger.tracking_start_date = default_tracking_start(ledger.subtype)
    else:
        raise ValueError("Provide ledger_account_id or create_ledger_account")

    db.commit()
    db.refresh(pa)
    return pa
