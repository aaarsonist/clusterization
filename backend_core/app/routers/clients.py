from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import ROLE_MARKETER, User
from app.schemas.client import ClientListResponse, ClientProfile
from app.services.auth import require_roles
from app.services.clients import client_profile, list_clients

router = APIRouter(prefix="/clients", tags=["Клиентская база"])
marketer = require_roles(ROLE_MARKETER)


@router.get("", response_model=ClientListResponse, summary="Реестр клиентов с поиском, фильтром по сегменту и пагинацией")
async def get_clients(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, max_length=100, description="ФИО, код клиента или номер телефона"),
    cluster_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(marketer),
) -> ClientListResponse:
    return await list_clients(db, page, limit, search, cluster_id)


@router.get("/{client_id}", response_model=ClientProfile, summary="Профиль клиента: метрики, история покупок, правила")
async def get_client(client_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(marketer)) -> ClientProfile:
    return await client_profile(db, client_id)
