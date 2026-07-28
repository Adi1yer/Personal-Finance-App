"""Tests for browser-based Plaid Link sessions."""

from app.services import plaid_pending


def test_browser_link_session_roundtrip():
    plaid_pending.save_browser_link("profile-1", "link-token-abc")
    session = plaid_pending.get_browser_link("profile-1")
    assert session is not None
    assert session.link_token == "link-token-abc"
    plaid_pending.clear_browser_link("profile-1")
    assert plaid_pending.get_browser_link("profile-1") is None
