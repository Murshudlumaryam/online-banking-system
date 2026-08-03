import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AccountBlockedError, ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        token = request.cookies.get("banking_access_token")
        if not token:
            raise UnauthorizedError("Missing bearer token")
    else:
        token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    user_id = uuid.UUID(payload["sub"])
    user = await UserRepository(session).get_by_id(user_id)

    if user is None:
        raise UnauthorizedError("User no longer exists")
    if user.is_blocked or not user.is_active:
        raise AccountBlockedError()

    return user


def require_role(*allowed_roles: UserRole):
    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError("You do not have permission to perform this action")
        return current_user

    return _dependency


require_admin = require_role(UserRole.ADMIN)
require_customer = require_role(UserRole.CUSTOMER)
