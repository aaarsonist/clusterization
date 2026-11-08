from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.system import BackupSettings
from app.models.user import ROLE_ADMIN, User
from app.schemas.common import StatusMessage
from app.schemas.system import (
    BackupItem,
    BackupOverview,
    BackupSettingsIn,
    BackupSettingsOut,
)
from app.services import backup as backup_service
from app.services.audit import audit
from app.services.auth import require_roles

router = APIRouter(prefix="/backups", tags=["Администрирование: резервное копирование"])
admin_only = require_roles(ROLE_ADMIN)


async def _settings(db: AsyncSession) -> BackupSettings:
    cfg = (await db.execute(select(BackupSettings).where(BackupSettings.id == 1))).scalar_one_or_none()
    if cfg is None:  # восстановление параметров по умолчанию при их отсутствии
        cfg = BackupSettings(id=1, enabled=True, run_hour=2, retention_count=14, updated_at=datetime.now(timezone.utc))
        db.add(cfg)
        await db.commit()
    return cfg


@router.get("", response_model=BackupOverview, summary="Список резервных копий и параметры расписания")
async def overview(db: AsyncSession = Depends(get_db), _: User = Depends(admin_only)) -> BackupOverview:
    cfg = await _settings(db)
    return BackupOverview(
        settings=BackupSettingsOut(enabled=cfg.enabled, run_hour=cfg.run_hour, retention_count=cfg.retention_count,
                                   updated_at=cfg.updated_at),
        backups=backup_service.list_backups(), free_space_bytes=backup_service.free_space(),
    )


@router.post("", response_model=BackupItem, status_code=201, summary="Создать резервную копию сейчас")
async def create(request: Request, admin: User = Depends(admin_only)) -> BackupItem:
    item = await backup_service.create_backup(backup_service.KIND_MANUAL, admin.username)
    await audit("Резервное копирование", user=admin, object_type="копия", object_id=item.file_name, request=request,
                details={"size_bytes": item.size_bytes})
    return item


@router.post("/{file_name}/restore", response_model=StatusMessage, summary="Восстановить базу данных из копии")
async def restore(file_name: str, request: Request, db: AsyncSession = Depends(get_db),
                  admin: User = Depends(admin_only)) -> StatusMessage:
    username = admin.username
    await db.close()  # сеанс проверки прав не должен удерживать блокировки на время восстановления
    item = await backup_service.restore_backup(file_name, username)
    await audit("Восстановление из резервной копии", username=username, object_type="копия", object_id=file_name,
                request=request, details={"backup_created_at": item.created_at.isoformat()})
    return StatusMessage(message=f"База данных восстановлена из копии от {item.created_at:%d.%m.%Y %H:%M} (UTC).")


@router.put("/settings", response_model=BackupSettingsOut, summary="Настроить автоматическое резервное копирование")
async def update_settings(payload: BackupSettingsIn, request: Request, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(admin_only)) -> BackupSettingsOut:
    cfg = await _settings(db)
    cfg.enabled, cfg.run_hour, cfg.retention_count = payload.enabled, payload.run_hour, payload.retention_count
    cfg.updated_by_user_id, cfg.updated_at = admin.id, datetime.now(timezone.utc)
    await db.commit()
    await audit("Настройка резервного копирования", user=admin, object_type="настройки", request=request,
                details=payload.model_dump())
    return BackupSettingsOut(**payload.model_dump(), updated_at=cfg.updated_at)
