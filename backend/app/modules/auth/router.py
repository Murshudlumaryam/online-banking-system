from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import send_notification_task
from app.core.exceptions import UnauthorizedError
from app.db.session import get_db
from app.modules.auth.cookies import (
    clear_refresh_token_cookie,
    read_refresh_token_cookie,
    set_refresh_token_cookie,
)
from app.modules.auth.dependencies import get_client_ip, get_current_user
from app.modules.auth.schemas import (
    AccessTokenResponse,
    DisableTwoFactorRequest,
    EnableTwoFactorRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterCustomerRequest,
    RegisterResponse,
    SetupTwoFactorResponse,
    VerifyMfaLoginRequest,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    login_response, raw_tokens = await service.login(payload, ip_address=get_client_ip(request))
    if raw_tokens is not None:
        set_refresh_token_cookie(response, raw_tokens.refresh_token)
    return login_response


@router.post("/refresh", response_model=AccessTokenResponse, summary="Rotate an access/refresh token pair")
async def refresh_token(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    raw_refresh_token = read_refresh_token_cookie(request)
    if raw_refresh_token is None:
        raise UnauthorizedError("No refresh token cookie present")

    service = AuthService(session)
    tokens = await service.refresh(raw_refresh_token, ip_address=get_client_ip(request))
    set_refresh_token_cookie(response, tokens.refresh_token)
    return AccessTokenResponse.from_tokens(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the current refresh token")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> None:
    raw_refresh_token = read_refresh_token_cookie(request)
    if raw_refresh_token is not None:
        service = AuthService(session)
        await service.logout(raw_refresh_token)
    clear_refresh_token_cookie(response)


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
    response_model=AccessTokenResponse,
    summary="Complete a login that returned an MFA challenge",
)
async def verify_mfa_login(
    payload: VerifyMfaLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    service = AuthService(session)
    tokens = await service.verify_mfa_login(
        payload.challenge_token, payload.code, ip_address=get_client_ip(request)
    )
    set_refresh_token_cookie(response, tokens.refresh_token)
    return AccessTokenResponse.from_tokens(tokens)


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
