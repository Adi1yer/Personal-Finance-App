"""Detect real investment contributions (re-exports institution adapters)."""

from __future__ import annotations

from app.services.institutions import looks_like_external_contribution

__all__ = ["looks_like_external_contribution"]
