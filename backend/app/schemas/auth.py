from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetPasswordRequest(BaseModel):
    email: str
    recovery_code: str
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile_id: str
    email: str
    display_name: str


class RegisterResponse(AuthResponse):
    recovery_code: str


class RecoveryCodeResponse(BaseModel):
    recovery_code: str


class ProfileRead(BaseModel):
    profile_id: str
    email: str
    display_name: str
    has_recovery_code: bool = False
