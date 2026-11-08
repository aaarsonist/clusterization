from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.audit import audit
from app.services.auth import get_current_user, login_throttle

router = APIRouter(prefix="/auth", tags=["Аутентификация"])


@router.post("/login", response_model=TokenResponse, summary="Вход в систему и получение токена доступа")
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    locked = login_throttle.remaining_lock(payload.username)
    if locked:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Вход временно заблокирован после серии неудачных попыток. Повторите через {locked // 60 + 1} мин.")
    user = (await db.execute(select(User).where(User.username == payload.username))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        blocked = login_throttle.register_failure(payload.username)
        await audit("Вход в систему", username=payload.username, success=False, request=request,
                    details={"reason": "неверный логин или пароль", "blocked": blocked})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль.")
    if not user.is_active:
        await audit("Вход в систему", user=user, success=False, request=request, details={"reason": "учетная запись деактивирована"})
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Учетная запись деактивирована. Обратитесь к администратору.")

    login_throttle.reset(payload.username)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await audit("Вход в систему", user=user, request=request)
    return TokenResponse(
        access_token=create_access_token(user.id, user.username, user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id, username=user.username, role=user.role,
    )


@router.get("/me", response_model=UserOut, summary="Профиль текущего пользователя")
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
