from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import send_notification_task
from app.db.session import get_db
from app.modules.auth.dependencies import get_client_ip, get_current_user
from app.modules.auth.schemas import (
    DisableTwoFactorRequest,
    EnableTwoFactorRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegisterCustomerRequest,
    RegisterResponse,
    SessionResponse,
    SetupTwoFactorResponse,
    TokenResponse,
    VerifyMfaLoginRequest,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _cookie_secure() -> bool:
    from app.core.config import get_settings

    return get_settings().is_production


def _set_token_cookies(response: Response, tokens: TokenResponse) -> None:
    secure = _cookie_secure()
    response.set_cookie(
        "banking_access_token",
        tokens.access_token,
        max_age=tokens.expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1",
    )
    response.set_cookie(
        "banking_refresh_token",
        tokens.refresh_token,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_token_cookies(response: Response) -> None:
    for name, path in (
        ("banking_access_token", "/api/v1"),
        ("banking_refresh_token", "/api/v1/auth"),
    ):
        response.delete_cookie(name, path=path, httponly=True, secure=_cookie_secure(), samesite="lax")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer",
)
async def register(
    payload: RegisterCustomerRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    service = AuthService(session)
    user = await service.register(payload, ip_address=get_client_ip(request))
    return RegisterResponse.model_validate(user)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password (returns an MFA challenge if 2FA is enabled)",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    service = AuthService(session)
    result = await service.login(payload, ip_address=get_client_ip(request))
    if result.access_token and result.refresh_token and result.expires_in:
        _set_token_cookies(
            response,
            TokenResponse(
                access_token=result.access_token,
                refresh_token=result.refresh_token,
                expires_in=result.expires_in,
            ),
        )
    return result


@router.post("/refresh", response_model=TokenResponse, summary="Rotate an access/refresh token pair")
async def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(session)
    raw_refresh_token = payload.refresh_token or request.cookies.get("banking_refresh_token")
    if not raw_refresh_token:
        from app.core.exceptions import InvalidRefreshTokenError

        raise InvalidRefreshTokenError()
    tokens = await service.refresh(raw_refresh_token, ip_address=get_client_ip(request))
    _set_token_cookies(response, tokens)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a refresh token")
async def logout(
    payload: LogoutRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    raw_refresh_token = payload.refresh_token or request.cookies.get("banking_refresh_token")
    if raw_refresh_token:
        await service.logout(raw_refresh_token)
    _clear_token_cookies(response)


@router.get("/session", response_model=SessionResponse, summary="Return the current authenticated session")
async def get_session(current_user: User = Depends(get_current_user)) -> SessionResponse:
    return SessionResponse(id=current_user.id, email=current_user.email, role=current_user.role.value)


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password",
)
async def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    await service.change_password(current_user, payload)


@router.post(
    "/password/reset-request",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request a password reset link/code",
)
async def request_password_reset(
    payload: PasswordResetRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    result = await service.request_password_reset(payload.email)
    # Always respond 204 regardless of whether the email exists (no user enumeration).
    if result:
        user_id, reset_token = result
        send_notification_task.delay(
            str(user_id), "email", "password_reset", {"reset_token": reset_token}
        )


@router.post(
    "/password/reset-confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm a password reset using the issued token",
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    await service.confirm_password_reset(payload)


@router.post(
    "/2fa/setup",
    response_model=SetupTwoFactorResponse,
    summary="Start two-factor authentication enrollment",
)
async def setup_two_factor(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SetupTwoFactorResponse:
    service = AuthService(session)
    return await service.setup_two_factor(current_user)


@router.post(
    "/2fa/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm enrollment by verifying a code from the authenticator app",
)
async def enable_two_factor(
    payload: EnableTwoFactorRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    await service.enable_two_factor(current_user, payload)


@router.post(
    "/2fa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable two-factor authentication (requires password + current code)",
)
async def disable_two_factor(
    payload: DisableTwoFactorRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(session)
    await service.disable_two_factor(current_user, payload)


@router.post(
    "/2fa/verify-login",
    response_model=TokenResponse,
    summary="Complete a login that returned an MFA challenge",
)
async def verify_mfa_login(
    payload: VerifyMfaLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(session)
    tokens = await service.verify_mfa_login(
        payload.challenge_token, payload.code, ip_address=get_client_ip(request)
    )
    _set_token_cookies(response, tokens)
    return tokens


@router.post(
    "/debug-promote-to-admin",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
    summary="[test environment only] Promotes the current user to ADMIN",
)
async def debug_promote_to_admin(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    from fastapi import HTTPException

    from app.core.test_mode import is_test_environment
    from app.modules.users.models import UserRole
    from app.modules.users.repository import UserRepository

    if not is_test_environment():
        # Same deliberate-404 rule as the debug OTP endpoint: this route
        # must be indistinguishable from "doesn't exist" outside test.
        raise HTTPException(status_code=404, detail="Not Found")

    current_user.role = UserRole.ADMIN
    await UserRepository(session).save(current_user)
    await session.commit()
