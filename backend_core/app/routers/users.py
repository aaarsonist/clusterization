from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, password_is_strong
from app.database import get_db
from app.models.user import ROLE_ADMIN, User
from app.schemas.auth import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services.audit import audit
from app.services.auth import require_roles

router = APIRouter(prefix="/users", tags=["Администрирование: пользователи"])
admin_only = require_roles(ROLE_ADMIN)
WEAK = "Пароль должен содержать не менее 8 символов, включая буквы и цифры."


async def _get(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден.")
    return user


@router.get("", response_model=list[UserOut], summary="Список учетных записей")
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(admin_only)) -> list[UserOut]:
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [UserOut.model_validate(u, from_attributes=True) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Создать учетную запись")
async def create_user(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(admin_only)) -> UserOut:
    if not password_is_strong(payload.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, WEAK)
    if (await db.execute(select(User.id).where(User.username == payload.username))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким логином уже существует.")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await audit("Создание пользователя", user=admin, object_type="пользователь", object_id=user.id, request=request,
                details={"username": user.username, "role": user.role})
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/{user_id}", response_model=UserOut, summary="Изменить роль или статус активности")
async def update_user(user_id: int, payload: UserUpdate, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(admin_only)) -> UserOut:
    user = await _get(db, user_id)
    if user.id == admin.id and (payload.is_active is False or (payload.role and payload.role != ROLE_ADMIN)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Нельзя деактивировать свою учетную запись или снять с себя роль администратора.")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    await audit("Изменение пользователя", user=admin, object_type="пользователь", object_id=user.id, request=request,
                details=changes)
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/{user_id}/password", response_model=UserOut, summary="Задать новый пароль пользователю")
async def reset_password(user_id: int, payload: PasswordReset, request: Request, db: AsyncSession = Depends(get_db),
                         admin: User = Depends(admin_only)) -> UserOut:
    if not password_is_strong(payload.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, WEAK)
    user = await _get(db, user_id)
    user.password_hash = hash_password(payload.password)
    await db.commit()
    await audit("Смена пароля пользователя", user=admin, object_type="пользователь", object_id=user.id, request=request)
    return UserOut.model_validate(user, from_attributes=True)
