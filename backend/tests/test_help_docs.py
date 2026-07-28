"""Tests for packaged setup help guides."""

from __future__ import annotations

import pytest

from app.services.help_docs import list_help_guides, read_help_guide, search_help_guides


def test_list_help_guides_includes_core_topics():
    guides = list_help_guides()
    slugs = {g["slug"] for g in guides}
    assert "README" in slugs
    assert "04-plaid-bank-connect" in slugs
    assert "05-google-drive-backups" in slugs
    assert "06-accounts-and-contributions" in slugs


def test_read_and_search_help_guides():
    doc = read_help_guide("05-google-drive-backups")
    assert "test user" in doc["content"].lower()
    hits = search_help_guides("test user safari")
    assert hits
    assert any(h["slug"] == "05-google-drive-backups" for h in hits)


def test_read_help_guide_rejects_traversal():
    with pytest.raises(ValueError):
        read_help_guide("../SETUP")
    with pytest.raises(ValueError):
        read_help_guide("/etc/passwd")
