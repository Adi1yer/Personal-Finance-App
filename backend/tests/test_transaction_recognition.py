from decimal import Decimal

from app.models.category import Category
from app.services.categorization import resolve_category_id
from app.services.register_labels import register_column_labels
from app.services.transaction_recognition import (
    conflict_group_key,
    extract_ticker,
    normalize_merchant,
    recognize_transaction,
)


BST_DIV_PAYEE = (
    "BLACKROCK SCIENCE & TECHNOLOGY TRUST BST DIV ON 1.06775 SHS"
)
BST_REINVEST_PAYEE = (
    "BLACKROCK SCIENCE & TECHNOLOGY TRUST BST REINVEST @ 49.432400"
)
SWEEP_PAYEE = "CHASE DEPOSIT SWEEP TO BROKERAGE"


def test_bst_dividend_recognition():
    r = recognize_transaction(
        payee=BST_DIV_PAYEE,
        account_subtype="brokerage",
        security_name="BST",
        amount=Decimal("50"),
        payment=Decimal("50"),
    )
    assert r.family == "dividend"
    assert r.ticker == "BST"
    assert r.canonical_key == "BST dividend"
    assert r.activity_label == "Dividend BST"
    assert r.suggested_category_slug == "interest_dividends"
    assert r.direction == "inflow"


def test_bst_reinvest_recognition():
    r = recognize_transaction(
        payee=BST_REINVEST_PAYEE,
        account_subtype="brokerage",
        security_name="BST",
        amount=Decimal("-50"),
        charge=Decimal("50"),
    )
    assert r.family == "reinvest"
    assert r.ticker == "BST"
    assert r.canonical_key == "BST reinvest"
    assert r.activity_label == "Reinvest BST"
    assert r.suggested_category_slug == "interest_dividends"


def test_chase_ira_deposit_recognized_as_contribution():
    r = recognize_transaction(
        payee="CHASE IRA DEPOSIT SWEEP JPMORGAN CHASE BANK NA INTRA-DAY DEPOSIT",
        account_subtype="retirement",
        amount=Decimal("-7500"),
    )
    assert r.family == "contribution"
    assert r.activity_label == "Contribution"
    assert r.suggested_category_slug == "investment_contribution"


def test_chase_deposit_sweep():
    r = recognize_transaction(
        payee=SWEEP_PAYEE,
        account_subtype="brokerage",
        amount=Decimal("-100"),
    )
    assert r.family == "sweep"
    assert r.is_internal_transfer is True
    assert r.canonical_key == "Chase deposit sweep"


def test_zelle_regression():
    r = recognize_transaction(
        payee="Zelle payment to RADHIKA PATWARDHAN JPM99cjcq19q",
        account_subtype="checking",
    )
    assert r.family == "zelle"
    assert r.canonical_key == "Zelle payment to RADHIKA PATWARDHAN"
    assert r.direction == "outflow"


def test_apple_cash_balance_transfer():
    r = recognize_transaction(
        payee="Apple Cash balance transfer",
        account_subtype="checking",
        amount=Decimal("-25"),
    )
    assert r.family == "apple_cash"
    assert r.canonical_key == "Apple Cash balance transfer"


def test_credit_card_purchase():
    r = recognize_transaction(
        payee="STARBUCKS #1234 SEATTLE WA",
        account_subtype="credit_card",
        amount=Decimal("-5.75"),
        charge=Decimal("5.75"),
    )
    assert r.family == "card_purchase"
    assert r.canonical_key == "Starbucks"
    assert r.activity_label == "Purchase Starbucks"
    assert r.direction == "outflow"


def test_credit_card_payment():
    r = recognize_transaction(
        payee="Payment Thank You - Web",
        account_subtype="credit_card",
        amount=Decimal("150.47"),
        payment=Decimal("150.47"),
    )
    assert r.family == "card_payment"
    assert r.canonical_key == "Card payment"
    assert r.activity_label == "Payment"
    assert r.direction == "inflow"
    assert r.is_internal_transfer is True


def test_credit_card_refund():
    r = recognize_transaction(
        payee="AMAZON.COM REFUND",
        account_subtype="credit_card",
        amount=Decimal("29.99"),
        payment=Decimal("29.99"),
    )
    assert r.family == "card_refund"
    assert "Refund" in (r.activity_label or "")


def test_credit_card_interest_charge():
    r = recognize_transaction(
        payee="INTEREST CHARGE ON PURCHASES",
        account_subtype="credit_card",
        amount=Decimal("-12.34"),
        charge=Decimal("12.34"),
    )
    assert r.family == "card_fee"
    assert r.activity_label == "Interest charge"
    assert r.suggested_category_slug == "utilities"


def test_checking_card_payment_with_mask():
    r = recognize_transaction(
        payee="Payment to Chase card ending in 5047 06/18",
        account_subtype="checking",
        amount=Decimal("-150.47"),
        raw_json='{"amount": 150.47, "name": "Payment to Chase card ending in 5047 06/18"}',
    )
    assert r.family == "card_payment"
    assert r.canonical_key == "Card payment ••••5047"
    assert r.direction == "outflow"


def test_merchant_normalization():
    assert normalize_merchant("WHOLE FOODS #1234") == "Whole Foods"
    assert normalize_merchant("AMZN MKTP US*AB12CD") == "Amazon"
    assert normalize_merchant("SQ *BLUE BOTTLE COFFEE") == "Blue Bottle Coffee"


def test_extract_ticker_from_security_name():
    assert extract_ticker(security_name="BST") == "BST"
    assert extract_ticker(payee=BST_DIV_PAYEE) == "BST"


def test_drip_category_preference(db_session):
    drip = Category(name="DRIP", slug="drip", category_type="expense")
    db_session.add(drip)
    db_session.commit()

    cat_id = resolve_category_id(
        db_session,
        payee=BST_REINVEST_PAYEE,
        account_subtype="brokerage",
        security_name="BST",
        amount=Decimal("-50"),
    )
    assert cat_id == drip.id


def test_register_credit_card_column_labels():
    out, inp, bal = register_column_labels("credit_card")
    assert out == "Charge"
    assert inp == "Payment"
    assert bal == "Balance owed"


def test_venmo_conflict_group_ignores_direction():
    outflow = recognize_transaction(
        payee="Venmo",
        account_subtype="checking",
        charge=Decimal("159"),
    )
    inflow = recognize_transaction(
        payee="Venmo",
        account_subtype="checking",
        payment=Decimal("50"),
    )
    assert conflict_group_key(outflow, payee="Venmo") == "venmo"
    assert conflict_group_key(inflow, payee="Venmo") == "venmo"


def test_venmo_different_payees_same_conflict_group():
    a = recognize_transaction(payee="Venmo Payment ABC", account_subtype="checking", charge=Decimal("20"))
    b = recognize_transaction(payee="Venmo Payment XYZ", account_subtype="checking", charge=Decimal("30"))
    assert conflict_group_key(a, payee="Venmo Payment ABC") == "venmo"
    assert conflict_group_key(b, payee="Venmo Payment XYZ") == "venmo"


def test_zelle_conflict_group_is_counterparty_specific():
    r = recognize_transaction(
        payee="Zelle payment to RADHIKA PATWARDHAN JPM99cjcq19q",
        account_subtype="checking",
    )
    assert conflict_group_key(r, payee="Zelle payment to RADHIKA PATWARDHAN JPM99cjcq19q") == (
        "Zelle payment to RADHIKA PATWARDHAN"
    )
    out, inp, bal = register_column_labels("credit_card")
    assert out == "Charge"
    assert inp == "Payment"
    assert bal == "Balance owed"
