from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.account import Account


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (base[:60] if base else "account")


def unique_category_slug(db: Session, name: str) -> str:
    from app.models.category import Category

    base = slugify(name) or "category"
    slug = base
    n = 2
    while db.query(Category).filter(Category.slug == slug).first():
        slug = f"{base}_{n}"
        n += 1
    return slug


def unique_account_slug(db: Session, name: str, exclude_id: int | None = None) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while True:
        q = db.query(Account).filter(Account.slug == slug)
        if exclude_id is not None:
            q = q.filter(Account.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base}_{n}"
        n += 1
