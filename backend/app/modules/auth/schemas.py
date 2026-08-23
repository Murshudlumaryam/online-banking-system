import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterCustomerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    phone_number: str = Field(min_length=5, max_length=32)
    address: str | None = Field(default=None, max_length=500)
    # Required, not optional: this is a bank, and a national ID (FIN/SSN
    # equivalent) is the baseline KYC identity check — an account without
    # one can't be verified to belong to a real, identifiable person.
    national_id: str = Field(min_length=1, max_length=64)

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_must_be_past(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return value

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(c.isupper() for c in value):
            raise ValueError("password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("password must contain at least one digit")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(c.isupper() for c in value):
            raise ValueError("new_password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("new_password must contain at least one digit")
        return value


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """
    Internal shape used between AuthService and the router — carries the raw
    refresh token so the router can put it in an HttpOnly cookie. Never
    returned to the client as JSON; see AccessTokenResponse for that.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AccessTokenResponse(BaseModel):
    """
    What actually goes in the JSON response body for login/refresh/2FA
    verify. Deliberately has no `refresh_token` field — that value is set as
    an HttpOnly, Secure, SameSite=Strict cookie instead (see
    app/modules/auth/router.py's cookie helpers) so it's never readable by
    JavaScript and therefore never exposed to an XSS payload the way a
    localStorage-held token would be.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int

    @classmethod
    def from_tokens(cls, tokens: TokenResponse) -> "AccessTokenResponse":
        return cls(access_token=tokens.access_token, expires_in=tokens.expires_in)


class LoginResponse(BaseModel):
    """
    Shape returned by POST /auth/login. When the account has 2FA enabled,
    the password check succeeding is not enough to issue real tokens — the
    response instead carries a short-lived `challenge_token` that must be
    presented together with a TOTP code to POST /auth/2fa/verify-login.

    No `refresh_token` field here either, for the same reason as
    AccessTokenResponse — it travels only as an HttpOnly cookie.
    """

    mfa_required: bool = False
    challenge_token: str | None = None
    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None

    @classmethod
    def from_tokens(cls, tokens: TokenResponse) -> "LoginResponse":
        return cls(
            mfa_required=False,
            access_token=tokens.access_token,
            expires_in=tokens.expires_in,
        )

    @classmethod
    def mfa_challenge(cls, challenge_token: str) -> "LoginResponse":
        return cls(mfa_required=True, challenge_token=challenge_token)


class VerifyMfaLoginRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SetupTwoFactorResponse(BaseModel):
    secret: str
    provisioning_uri: str


class EnableTwoFactorRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class DisableTwoFactorRequest(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CustomerSummary(BaseModel):
    id: uuid.UUID
    customer_number: str
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: str
    customer: CustomerSummary

    model_config = {"from_attributes": True}
