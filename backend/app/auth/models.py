from pydantic import BaseModel, EmailStr, Field

from app.auth.rbac import Role


class User(BaseModel):
    id: str
    email: EmailStr
    role: Role
    password_hash: str
    is_active: bool = True


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    role: Role
    is_active: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
