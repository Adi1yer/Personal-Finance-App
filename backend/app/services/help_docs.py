"""Read packaged setup help guides under docs/help/ for Advisor + Settings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT

HELP_DIR = REPO_ROOT / "docs" / "help"
_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")


def _safe_path(slug: str) -> Path:
    """Resolve a help slug to a file under docs/help only."""
    raw = (slug or "").strip().replace("\\", "/")
    if raw.endswith(".md"):
        raw = raw[:-3]
    # Allow "README" or "01-install-and-launch" style names only
    name = Path(raw).name
    if not _SLUG_RE.match(name) or "/" in raw or ".." in raw:
        raise ValueError("Invalid help guide name")
    help_root = HELP_DIR.resolve()
    path = (help_root / f"{name}.md").resolve()
    try:
        path.relative_to(help_root)
    except ValueError as exc:
        raise ValueError("Help guide not found") from exc
    if path.suffix != ".md" or not path.is_file():
        raise ValueError(f"Help guide not found: {name}")
    return path


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def list_help_guides() -> list[dict[str, str]]:
    """Ordered list of help guides (README first, then numbered, then rest)."""
    if not HELP_DIR.is_dir():
        return []

    files = sorted(HELP_DIR.glob("*.md"), key=lambda p: (p.name != "README.md", p.name.lower()))
    out: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        slug = path.stem
        title = _title_from_markdown(text, slug)
        # First non-empty paragraph after title as blurb
        blurb = ""
        saw_title = False
        for line in text.splitlines():
            s = line.strip()
            if not saw_title:
                if s.startswith("# "):
                    saw_title = True
                continue
            if not s or s.startswith("#") or s.startswith("|") or s.startswith("```"):
                if blurb:
                    break
                continue
            blurb = s
            break
        out.append({"slug": slug, "title": title, "blurb": blurb[:240]})
    return out


def read_help_guide(slug: str) -> dict[str, str]:
    path = _safe_path(slug)
    content = path.read_text(encoding="utf-8")
    return {
        "slug": path.stem,
        "title": _title_from_markdown(content, path.stem),
        "path": f"docs/help/{path.name}",
        "content": content,
    }


def search_help_guides(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Simple keyword search across help guides; returns snippets."""
    q = (query or "").strip().lower()
    if not q:
        return []
    terms = [t for t in re.split(r"\s+", q) if len(t) >= 2]
    if not terms:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for meta in list_help_guides():
        try:
            doc = read_help_guide(meta["slug"])
        except ValueError:
            continue
        text = doc["content"]
        lower = text.lower()
        score = sum(lower.count(t) for t in terms)
        if score <= 0:
            continue
        # Prefer a line that contains the first term
        snippet = ""
        for line in text.splitlines():
            if terms[0] in line.lower() and line.strip():
                snippet = line.strip()[:220]
                break
        if not snippet:
            snippet = meta.get("blurb") or doc["title"]
        scored.append(
            (
                score,
                {
                    "slug": doc["slug"],
                    "title": doc["title"],
                    "score": score,
                    "snippet": snippet,
                    "hint": f"Call read_help_guide with slug={doc['slug']} for full steps.",
                },
            )
        )
    scored.sort(key=lambda x: (-x[0], x[1]["slug"]))
    return [item for _, item in scored[: max(1, min(limit, 10))]]


def help_index_for_advisor() -> dict[str, Any]:
    guides = list_help_guides()
    return {
        "help_root": "docs/help/",
        "recommended_order": [
            g["slug"]
            for g in guides
            if g["slug"] != "README" and not g["slug"].startswith("99")
        ],
        "guides": guides,
        "usage": (
            "For how-to / setup questions: search_help_guides or read_help_guide, "
            "then walk the user through what they should see and do. "
            "Also call get_setup_status to tailor the next step."
        ),
    }
