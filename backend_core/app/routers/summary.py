from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.models.loyalty import LoyaltyRule
from app.models.transaction import STATUS_CANCELLED, STATUS_CONFIRMED, Transaction
from app.models.user import ROLE_ADMIN, ROLE_MARKETER, User
from app.schemas.common import SummaryResponse
from app.services.auth import require_roles
from app.services.segmentation import cluster_briefs, get_approved_run

router = APIRouter(prefix="/summary", tags=["Аналитическая сводка"])


@router.get("", response_model=SummaryResponse, summary="Агрегированные показатели без персональных данных")
async def get_summary(db: AsyncSession = Depends(get_db),
                      _: User = Depends(require_roles(ROLE_MARKETER, ROLE_ADMIN))) -> SummaryResponse:
    clients = (await db.execute(select(func.count(Client.id)))).scalar_one()
    count, revenue, discount, avg = (await db.execute(select(
        func.count(Transaction.id),
        func.coalesce(func.sum(Transaction.total_amount), 0),
        func.coalesce(func.sum(Transaction.discount_amount), 0),
        func.coalesce(func.avg(Transaction.total_amount), 0),
    ).where(Transaction.status == STATUS_CONFIRMED))).one()
    cancelled = (await db.execute(
        select(func.count(Transaction.id)).where(Transaction.status == STATUS_CANCELLED))).scalar_one()
    rules = (await db.execute(select(func.count(LoyaltyRule.id)).where(LoyaltyRule.is_active.is_(True)))).scalar_one()
    run = await get_approved_run(db)
    return SummaryResponse(
        total_clients=clients, total_transactions=count, cancelled_transactions=cancelled,
        total_revenue=Decimal(revenue).quantize(Decimal("0.01")), total_discount=Decimal(discount).quantize(Decimal("0.01")),
        avg_check=Decimal(avg).quantize(Decimal("0.01")), active_loyalty_rules=rules,
        model_algorithm=run.algorithm if run else None, model_approved_at=run.approved_at if run else None,
        clusters=await cluster_briefs(db, run.id) if run else [],
    )
