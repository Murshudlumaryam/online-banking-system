import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import (
    AccountBlockedError,
    ConflictError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    InvalidTotpCodeError,
    MfaChallengeInvalidError,
    TwoFactorAlreadyEnabledError,
    TwoFactorNotEnabledError,
    TwoFactorSetupNotStartedError,
)
from app.core.security import (
    InvalidTokenError,
    build_totp_provisioning_uri,
    create_access_token,
    create_mfa_challenge_token,
    create_password_reset_token,
    generate_refresh_token,
    generate_totp_secret,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_mfa_challenge_token,
    verify_password,
    verify_password_reset_token,
    verify_totp_code,
)
from app.modules.auth.models import RefreshToken
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.auth.schemas import (
    DisableTwoFactorRequest,
    EnableTwoFactorRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    RegisterCustomerRequest,
    SetupTwoFactorResponse,
    TokenResponse,
)
from app.modules.customers.repository import CustomerRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._users = UserRepository(session)
        self._customers = CustomerRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    async def register(self, payload: RegisterCustomerRequest, *, ip_address: str | None) -> User:
        if await self._users.email_exists(payload.email):
            raise EmailAlreadyRegisteredError()

        if payload.national_id and await self._customers.national_id_exists(payload.national_id):
            raise ConflictError("A customer with this national ID already exists")

        try:
            user = self._users.create(email=payload.email, password_hash=hash_password(payload.password))
            await self._session.flush()  # assign user.id before creating the dependent customer

            self._customers.create(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                date_of_birth=payload.date_of_birth,
                phone_number=payload.phone_number,
                address=payload.address,
                national_id=payload.national_id,
            )
            await self._session.commit()
        except IntegrityError as exc:
            # The email_exists()/national_id_exists() checks above are a
            # plain SELECT before this INSERT — a genuine TOCTOU race if two
            # requests with the same email (or national_id) commit at
            # nearly the same instant. The DB's UNIQUE constraints are the
            # real guarantee (data integrity holds either way — only one
            # row ever exists), but without this except block the loser saw
            # a raw, unhandled IntegrityError (a generic 500) instead of the
            # correct 409. Found via a concurrent-registration audit test
            # (tests/modules/auth/test_audit_registration_race.py).
            #
            # Note this must wrap the EARLIER flush() too, not just the
            # final commit() — the actual INSERT (and thus the constraint
            # check) happens at that flush, needed to obtain `user.id`
            # before the dependent customer row can reference it.
            await self._session.rollback()
            raise ConflictError(
                "This email or national ID is already registered"
            ) from exc
        await self._session.refresh(user)

        write_audit_log_task.delay(str(user.id), "CUSTOMER_REGISTERED", "user", str(user.id), ip_address, None)
        return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(
        self, payload: LoginRequest, *, ip_address: str | None
    ) -> tuple[LoginResponse, TokenResponse | None]:
        """
        Returns (response_body, raw_tokens). `raw_tokens` is None for the
        MFA-challenge branch (nothing issued yet) and populated on a normal
        successful login — the router uses it to set the refresh-token
        cookie, while `response_body` (never containing the raw refresh
        token) is what actually goes back as JSON.
        """
        user = await self._users.get_by_email(payload.email)

        if user is None or not verify_password(payload.password, user.password_hash):
            write_audit_log_task.delay(
                str(user.id) if user else None, "LOGIN_FAILED", "user", None, ip_address, None
            )
            raise InvalidCredentialsError()

        if user.is_blocked or not user.is_active:
            write_audit_log_task.delay(str(user.id), "LOGIN_BLOCKED", "user", str(user.id), ip_address, None)
            raise AccountBlockedError()

        if user.totp_enabled:
            write_audit_log_task.delay(
                str(user.id), "LOGIN_PASSWORD_OK_AWAITING_MFA", "user", str(user.id), ip_address, None
            )
            challenge_token = create_mfa_challenge_token(user_id=user.id)
            return LoginResponse.mfa_challenge(challenge_token), None

        await self._users.mark_login(user)
        tokens, _ = await self._issue_token_pair(user)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "LOGIN_SUCCESS", "user", str(user.id), ip_address, None)
        return LoginResponse.from_tokens(tokens), tokens

    # ------------------------------------------------------------------
    # Two-factor authentication (Phase 7; encrypted at rest since Phase 9)
    # ------------------------------------------------------------------
    async def setup_two_factor(self, user: User) -> SetupTwoFactorResponse:
        if user.totp_enabled:
            raise TwoFactorAlreadyEnabledError()

        secret = generate_totp_secret()
        user.totp_secret = encrypt_secret(secret)
        await self._users.save(user)
        await self._session.commit()

        return SetupTwoFactorResponse(
            secret=secret,
            provisioning_uri=build_totp_provisioning_uri(secret=secret, email=user.email),
        )

    async def enable_two_factor(self, user: User, payload: EnableTwoFactorRequest) -> None:
        if user.totp_enabled:
            raise TwoFactorAlreadyEnabledError()
        if not user.totp_secret:
            raise TwoFactorSetupNotStartedError()
        if not verify_totp_code(secret=self._decrypt_totp_secret(user.totp_secret), code=payload.code):
            raise InvalidTotpCodeError()

        user.totp_enabled = True
        await self._users.save(user)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "TWO_FACTOR_ENABLED", "user", str(user.id), None, None)

    async def disable_two_factor(self, user: User, payload: DisableTwoFactorRequest) -> None:
        if not user.totp_enabled:
            raise TwoFactorNotEnabledError()
        if not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError()
        if not user.totp_secret or not verify_totp_code(
            secret=self._decrypt_totp_secret(user.totp_secret), code=payload.code
        ):
            raise InvalidTotpCodeError()

        user.totp_enabled = False
        user.totp_secret = None
        await self._users.save(user)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "TWO_FACTOR_DISABLED", "user", str(user.id), None, None)

    async def verify_mfa_login(self, challenge_token: str, code: str, *, ip_address: str | None) -> TokenResponse:
        try:
            user_id = verify_mfa_challenge_token(challenge_token)
        except InvalidTokenError:
            raise MfaChallengeInvalidError()

        user = await self._users.get_by_id(user_id)
        if user is None or user.is_blocked or not user.is_active:
            raise MfaChallengeInvalidError()
        if not user.totp_enabled or not user.totp_secret:
            # 2FA was disabled between issuing the challenge and verifying it.
            raise MfaChallengeInvalidError()

        if not verify_totp_code(secret=self._decrypt_totp_secret(user.totp_secret), code=code):
            write_audit_log_task.delay(
                str(user.id), "MFA_LOGIN_FAILED", "user", str(user.id), ip_address, None
            )
            raise InvalidTotpCodeError()

        await self._users.mark_login(user)
        tokens, _ = await self._issue_token_pair(user)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "MFA_LOGIN_SUCCESS", "user", str(user.id), ip_address, None)
        return tokens

    @staticmethod
    def _decrypt_totp_secret(encrypted_secret: str) -> str:
        try:
            return decrypt_secret(encrypted_secret)
        except ValueError:
            # Corrupted ciphertext or an ENCRYPTION_KEY mismatch/rotation —
            # treated the same as "the code was wrong": never leak *why*
            # verification failed, and never crash the request over it.
            raise InvalidTotpCodeError()


    # ------------------------------------------------------------------
    # Refresh (rotation): old token is revoked, a new pair is issued.
    # Reuse of an already-revoked token revokes the entire family — signals
    # possible token theft.
    # ------------------------------------------------------------------
    async def refresh(self, raw_refresh_token: str, *, ip_address: str | None) -> TokenResponse:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored_token = await self._refresh_tokens.get_by_hash(token_hash)

        if stored_token is None:
            raise InvalidRefreshTokenError()

        if not self._refresh_tokens.is_valid(stored_token):
            # Reused / expired token: revoke every active token for this user as a precaution.
            await self._refresh_tokens.revoke_all_for_user(stored_token.user_id)
            await self._session.commit()
            write_audit_log_task.delay(
                str(stored_token.user_id), "REFRESH_TOKEN_REUSE_DETECTED", "user",
                str(stored_token.user_id), ip_address, None,
            )
            raise InvalidRefreshTokenError()

        user = await self._users.get_by_id(stored_token.user_id)
        if user is None or user.is_blocked or not user.is_active:
            raise InvalidRefreshTokenError()

        tokens, new_token_row = await self._issue_token_pair(user)
        await self._refresh_tokens.revoke(stored_token, replaced_by=new_token_row)
        await self._session.commit()
        return tokens

    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored_token = await self._refresh_tokens.get_by_hash(token_hash)
        if stored_token is not None and self._refresh_tokens.is_valid(stored_token):
            await self._refresh_tokens.revoke(stored_token)
            await self._session.commit()

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------
    async def change_password(self, user: User, payload: PasswordChangeRequest) -> None:
        if not verify_password(payload.current_password, user.password_hash):
            raise InvalidCredentialsError()

        user.password_hash = hash_password(payload.new_password)
        self._session.add(user)
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "PASSWORD_CHANGED", "user", str(user.id), None, None)

    async def request_password_reset(self, email: str) -> tuple[uuid.UUID, str] | None:
        """
        Returns (user_id, reset_token) so the router/background task can
        dispatch the notification to the right user. Always looks like it
        succeeded to the caller (no user enumeration), even if the email
        does not exist.
        """
        user = await self._users.get_by_email(email)
        if user is None:
            return None
        token = create_password_reset_token(user_id=user.id, current_password_hash=user.password_hash)
        return user.id, token

    async def confirm_password_reset(self, payload: PasswordResetConfirmRequest) -> None:
        # We don't know the user id yet, so we must decode without verifying
        # the fingerprint first is not possible — instead, decode the JWT
        # claims (sub) without trusting them, load the user, then verify
        # the fingerprint against that user's *current* hash.
        try:
            unverified_user_id = _extract_subject_unsafe(payload.reset_token)
        except InvalidTokenError:
            raise InvalidResetTokenError()

        user = await self._users.get_by_id(unverified_user_id)
        if user is None:
            raise InvalidResetTokenError()  # never confirm whether the account exists

        try:
            verify_password_reset_token(payload.reset_token, current_password_hash=user.password_hash)
        except InvalidTokenError:
            raise InvalidResetTokenError()

        user.password_hash = hash_password(payload.new_password)
        self._session.add(user)
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._session.commit()

        write_audit_log_task.delay(str(user.id), "PASSWORD_RESET", "user", str(user.id), None, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _issue_token_pair(self, user: User) -> tuple[TokenResponse, RefreshToken]:
        access_token = create_access_token(user_id=user.id, role=user.role.value)

        raw_refresh = generate_refresh_token()
        token_row = self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_token_expiry(),
        )
        await self._session.flush()

        response = TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=get_settings().access_token_expire_minutes * 60,
        )
        return response, token_row


def _extract_subject_unsafe(token: str) -> uuid.UUID:
    """Reads the `sub` claim without verifying signature ownership context —
    used only to look up which user's hash to verify the fingerprint against.
    Signature and expiry are still fully verified in verify_password_reset_token
    right after; this function never authorizes anything by itself."""
    from jose import jwt as _jwt

    from app.core.config import get_settings

    settings = get_settings()
    try:
        payload = _jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except Exception as exc:
        raise InvalidTokenError("Malformed reset token") from exc
    return uuid.UUID(payload["sub"])
