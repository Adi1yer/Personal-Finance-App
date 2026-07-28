from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.profile_db import init_profile_ledger
from app.models.profile import Profile

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RECOVERY_WORDS = (
    "amber", "brisk", "coral", "delta", "ember", "flint", "grove", "haven",
    "ivory", "jade", "kite", "linen", "maple", "noble", "olive", "prism",
    "quartz", "river", "stone", "terra", "ultra", "vivid", "willow", "xenon",
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_recovery_code(code: str) -> str:
    return re.sub(r"\s+", "", code.strip().lower())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_recovery_code(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return bcrypt.hashpw(normalized.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_recovery_code(code: str, code_hash: str | None) -> bool:
    if not code_hash:
        return False
    normalized = normalize_recovery_code(code)
    return bcrypt.checkpw(normalized.encode("utf-8"), code_hash.encode("utf-8"))


def generate_recovery_code() -> str:
    parts = [secrets.choice(_RECOVERY_WORDS) for _ in range(4)]
    return "-".join(parts)


def assign_recovery_code(profile: Profile) -> str:
    code = generate_recovery_code()
    profile.recovery_code_hash = hash_recovery_code(code)
    return code


def create_access_token(profile: Profile) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": profile.id,
        "email": profile.email,
        "exp": exp,
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.effective_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session") from exc


def register_profile(
    db: Session, email: str, password: str, display_name: str = ""
) -> tuple[Profile, str]:
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email address")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(Profile).filter(Profile.email == email).first():
        raise HTTPException(400, "An account with this email already exists")

    recovery_code = generate_recovery_code()
    profile = Profile(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip() or email.split("@")[0],
        recovery_code_hash=hash_recovery_code(recovery_code),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    init_profile_ledger(profile.id)
    return profile, recovery_code


def authenticate_profile(db: Session, email: str, password: str) -> Profile:
    email = normalize_email(email)
    profile = db.query(Profile).filter(Profile.email == email).first()
    if not profile or not verify_password(password, profile.password_hash):
        raise HTTPException(401, "Invalid email or password")
    init_profile_ledger(profile.id)
    return profile


def reset_password_with_recovery(
    db: Session, email: str, recovery_code: str, new_password: str
) -> Profile:
    email = normalize_email(email)
    if len(new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    profile = db.query(Profile).filter(Profile.email == email).first()
    if not profile:
        raise HTTPException(404, "No profile found for this email")
    if not profile.recovery_code_hash:
        raise HTTPException(
            400,
            "This profile has no recovery code. Reset via Terminal: "
            "make reset-password EMAIL=your@email.com",
        )
    if not verify_recovery_code(recovery_code, profile.recovery_code_hash):
        raise HTTPException(400, "Invalid recovery code")
    profile.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(profile)
    return profile


def change_password(
    db: Session, profile: Profile, current_password: str, new_password: str
) -> None:
    if len(new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if not verify_password(current_password, profile.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    profile.password_hash = hash_password(new_password)
    db.commit()


def regenerate_recovery_code(db: Session, profile: Profile) -> str:
    code = assign_recovery_code(profile)
    db.commit()
    db.refresh(profile)
    return code


def admin_reset_password(db: Session, email: str, new_password: str) -> tuple[Profile, str]:
    """CLI / local admin — sets password and issues a new recovery code."""
    email = normalize_email(email)
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")
    profile = db.query(Profile).filter(Profile.email == email).first()
    if not profile:
        known = [p.email for p in db.query(Profile).order_by(Profile.email).all()]
        hint = f" Known profiles: {', '.join(known)}" if known else " No profiles registered yet."
        raise LookupError(f"No profile for {email}.{hint}")
    profile.password_hash = hash_password(new_password)
    recovery_code = assign_recovery_code(profile)
    db.commit()
    db.refresh(profile)
    return profile, recovery_code
