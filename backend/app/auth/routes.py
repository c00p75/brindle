from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import current_user
from app.auth.jwt import issue_token
from app.auth.models import LoginRequest, TokenResponse, User, UserPublic
from app.auth.service import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    user = authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = issue_token(subject=user.email, role=user.role.value)
    return TokenResponse(
        access_token=token,
        user=UserPublic(**user.model_dump(exclude={"password_hash"})),
    )


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(current_user)) -> UserPublic:
    return UserPublic(**user.model_dump(exclude={"password_hash"}))
