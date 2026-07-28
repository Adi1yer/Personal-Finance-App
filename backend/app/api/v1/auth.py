from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_profile, get_registry_db
from app.models.profile import Profile
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    ProfileRead,
    RecoveryCodeResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
)
from app.services.auth import (
    authenticate_profile,
    change_password,
    create_access_token,
    regenerate_recovery_code,
    register_profile,
    reset_password_with_recovery,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_response(profile: Profile) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(profile),
        profile_id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_registry_db)) -> RegisterResponse:
    profile, recovery_code = register_profile(db, body.email, body.password, body.display_name)
    base = _auth_response(profile)
    return RegisterResponse(**base.model_dump(), recovery_code=recovery_code)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_registry_db)) -> AuthResponse:
    profile = authenticate_profile(db, body.email, body.password)
    return _auth_response(profile)


@router.post("/reset-password", response_model=AuthResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_registry_db)) -> AuthResponse:
    profile = reset_password_with_recovery(
        db, body.email, body.recovery_code, body.new_password
    )
    return _auth_response(profile)


@router.post("/change-password", status_code=204)
def change_password_route(
    body: ChangePasswordRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_registry_db),
) -> None:
    row = db.get(Profile, profile.id)
    if not row:
        raise HTTPException(404, "Profile not found")
    change_password(db, row, body.current_password, body.new_password)


@router.post("/regenerate-recovery", response_model=RecoveryCodeResponse)
def regenerate_recovery(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_registry_db),
) -> RecoveryCodeResponse:
    row = db.get(Profile, profile.id)
    if not row:
        raise HTTPException(404, "Profile not found")
    code = regenerate_recovery_code(db, row)
    return RecoveryCodeResponse(recovery_code=code)


@router.get("/session", response_model=ProfileRead)
def session(profile: Profile = Depends(get_current_profile)) -> ProfileRead:
    return ProfileRead(
        profile_id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        has_recovery_code=bool(profile.recovery_code_hash),
    )
