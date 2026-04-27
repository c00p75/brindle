from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.deps import current_user
from app.auth.jwt import issue_token
from app.auth.models import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TokenResponse,
    User,
    UserPublic,
)
from app.auth.rate_limit import forgot_password_limiter, login_limiter, totp_limiter
from app.auth.service import (
    authenticate,
    request_password_reset,
    reset_password,
    totp_check,
    totp_disable,
    totp_setup,
    totp_verify_and_enable,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    if not login_limiter.is_allowed(_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many login attempts — try again later")

    user = authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    if user.totp_enabled:
        if not body.totp_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "totp_code required")
        if not totp_limiter.is_allowed(_ip(request)):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many TOTP attempts")
        if not totp_check(user, body.totp_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid TOTP code")

    token = issue_token(subject=user.email, role=user.role.value)
    return TokenResponse(
        access_token=token,
        user=UserPublic(**user.model_dump(exclude={"password_hash", "totp_secret"})),
    )


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(current_user)) -> UserPublic:
    return UserPublic(**user.model_dump(exclude={"password_hash", "totp_secret"}))


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------

@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(request: Request, user: User = Depends(current_user)) -> TOTPSetupResponse:
    if not totp_limiter.is_allowed(_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many TOTP requests")
    secret, uri = totp_setup(user.email)
    return TOTPSetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/totp/verify")
async def verify_totp(body: TOTPVerifyRequest, request: Request, user: User = Depends(current_user)) -> dict:
    if not totp_limiter.is_allowed(_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many TOTP attempts")
    ok = totp_verify_and_enable(user.email, body.code)
    if not ok:
        raise HTTPException(400, "invalid TOTP code")
    return {"totp_enabled": True}


@router.delete("/totp")
async def disable_totp(user: User = Depends(current_user)) -> dict:
    totp_disable(user.email)
    return {"totp_enabled": False}


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordRequest, request: Request) -> dict:
    if not forgot_password_limiter.is_allowed(_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many reset requests — try again later")
    request_password_reset(body.email)
    return {"detail": "if that email exists, a reset link has been logged to the server console"}


@router.post("/reset-password")
async def do_reset_password(body: ResetPasswordRequest) -> dict:
    ok = reset_password(body.token, body.new_password)
    if not ok:
        raise HTTPException(400, "invalid or expired reset token")
    return {"detail": "password updated"}
