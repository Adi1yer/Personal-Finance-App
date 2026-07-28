from decimal import Decimal

from app.services.payee_normalization import (
    canonical_match_key,
    infer_direction,
    parse_zelle,
    strip_trailing_id,
    transaction_direction,
)


def test_strip_trailing_zelle_id():
    assert strip_trailing_id("RADHIKA PATWARDHAN JPM99ckej76s") == "RADHIKA PATWARDHAN"
    assert strip_trailing_id("ARYAN GUPTA BACnakhocqxb") == "ARYAN GUPTA"


def test_parse_zelle_to():
    info = parse_zelle("Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s")
    assert info is not None
    assert info.direction == "to"
    assert info.counterparty == "RADHIKA PATWARDHAN"
    assert info.canonical == "Zelle payment to RADHIKA PATWARDHAN"


def test_parse_zelle_from():
    info = parse_zelle("Zelle payment from ANNA MINDLINA CTIcW2KoX3vx")
    assert info is not None
    assert info.direction == "from"
    assert info.counterparty == "ANNA MINDLINA"
    assert info.canonical == "Zelle payment from ANNA MINDLINA"


def test_parse_zelle_from_aryan():
    info = parse_zelle("Zelle payment from ARYAN GUPTA BACnakhocqxb")
    assert info is not None
    assert info.canonical == "Zelle payment from ARYAN GUPTA"


def test_canonical_match_key():
    assert (
        canonical_match_key("Zelle payment to RADHIKA PATWARDHAN JPM99cjcq19q")
        == "Zelle payment to RADHIKA PATWARDHAN"
    )


def test_infer_direction_from_zelle_text():
    assert infer_direction("Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s") == "outflow"
    assert infer_direction("Zelle payment from ANNA MINDLINA CTIcW2KoX3vx") == "inflow"


def test_transaction_direction():
    assert transaction_direction(Decimal("25"), None) == "outflow"
    assert transaction_direction(None, Decimal("100")) == "inflow"
    assert transaction_direction(None, None) == "none"
