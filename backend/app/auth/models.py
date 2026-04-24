from pydantic import BaseModel, EmailStr, Field

from app.auth.rbac import Role


class User(BaseModel):
    id: str
    email: EmailStr
    role: Role
    password_hash: str
    is_active: bool = True
    is_super_admin: bool = False
    totp_secret: str | None = None
    totp_enabled: bool = False


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    role: Role
    is_active: bool
    is_super_admin: bool = False
    totp_enabled: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
