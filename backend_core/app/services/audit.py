"""Журнал аудита: запись событий в отдельной транзакции, не зависящей от бизнес-операции."""
import logging
from typing import Any

from fastapi import Request

from app.database import async_session_maker
from app.models.system import AuditLog
from app.models.user import User

logger = logging.getLogger("backend_core.audit")


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else None


async def audit(
    action: str,
    *,
    user: User | None = None,
    username: str | None = None,
    object_type: str | None = None,
    object_id: Any = None,
    success: bool = True,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    try:
        async with async_session_maker() as session:
            session.add(AuditLog(
                user_id=user.id if user else None,
                username=(user.username if user else username),
                action=action,
                object_type=object_type,
                object_id=None if object_id is None else str(object_id),
                success=success,
                ip_address=client_ip(request),
                details=details or {},
            ))
            await session.commit()
    except Exception:  # журнал аудита не должен прерывать основную операцию
        logger.exception("Не удалось записать событие аудита", extra={"action": action})
