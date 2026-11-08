"""Аутентификация по JWT, ролевой контроль доступа и защита от подбора паролей."""
import time
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Требуется аутентификация в системе.")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Срок действия сеанса истек. Выполните вход повторно.") from None
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Недействительный токен доступа.") from None

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized("Учетная запись не найдена или деактивирована.")
    return user


def require_roles(*roles: str) -> Callable:
    """Фабрика зависимостей ролевого контроля доступа (RBAC)."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для выполнения операции.")
        return user

    return checker


class LoginThrottle:
    """Временная блокировка входа после серии неудачных попыток для одного логина."""

    def __init__(self, max_failures: int, lock_seconds: int):
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def remaining_lock(self, username: str) -> int:
        until = self._locked_until.get(username.lower(), 0.0)
        return max(0, int(until - time.monotonic()))

    def register_failure(self, username: str) -> bool:
        key = username.lower()
        now = time.monotonic()
        window = [t for t in self._failures.get(key, []) if now - t < self.lock_seconds] + [now]
        self._failures[key] = window
        if len(window) >= self.max_failures:
            self._locked_until[key] = now + self.lock_seconds
            self._failures[key] = []
            return True
        return False

    def reset(self, username: str) -> None:
        self._failures.pop(username.lower(), None)
        self._locked_until.pop(username.lower(), None)


login_throttle = LoginThrottle(settings.LOGIN_MAX_FAILURES, settings.LOGIN_LOCK_MINUTES * 60)
