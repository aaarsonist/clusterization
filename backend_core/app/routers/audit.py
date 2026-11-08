from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.system import AuditLog
from app.models.user import ROLE_ADMIN, User
from app.schemas.system import AuditItem, AuditPage
from app.services.auth import require_roles

router = APIRouter(prefix="/audit", tags=["Администрирование: журнал аудита"])


@router.get("", response_model=AuditPage, summary="Журнал аудита с фильтрацией и постраничным выводом")
async def get_audit(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None, max_length=64),
    username: str | None = Query(None, max_length=64),
    only_failed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN)),
) -> AuditPage:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if username:
        conditions.append(AuditLog.username.ilike(f"%{username}%"))
    if only_failed:
        conditions.append(AuditLog.success.is_(False))
    total = (await db.execute(select(func.count(AuditLog.id)).where(*conditions))).scalar_one()
    rows = (await db.execute(select(AuditLog).where(*conditions)
                             .order_by(AuditLog.event_time.desc(), AuditLog.id.desc()).limit(limit).offset(offset))).scalars()
    return AuditPage(items=[AuditItem.model_validate(r, from_attributes=True) for r in rows], total=total)


@router.get("/actions", response_model=list[str], summary="Перечень типов событий журнала")
async def get_actions(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles(ROLE_ADMIN))) -> list[str]:
    return list((await db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))).scalars())
