from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_pii
from app.database import get_db
from app.models.client import Client
from app.models.cluster import ClientClusterMapping, Cluster
from app.models.loyalty import LoyaltyRule, LoyaltyRuleCustomClient
from app.models.user import ROLE_MARKETER, User
from app.schemas.common import StatusMessage
from app.schemas.loyalty import (
    AttachClientRequest,
    AudienceClient,
    AudienceResponse,
    DiscountRequest,
    DiscountResponse,
    RuleCreate,
    RuleOut,
    RuleUpdate,
)
from app.services.audit import audit
from app.services.auth import require_roles
from app.services.clients import phone_lookup_ids
from app.services.exports import file_response, slug
from app.services.loyalty import calculate_benefit, describe_reward, select_best_rule
from app.services.segmentation import get_approved_run

router = APIRouter(prefix="/loyalty", tags=["Программа лояльности"])
marketer = require_roles(ROLE_MARKETER)
GENERAL = "Общее правило (все сегменты)"

AUDIENCE_COUNT_SQL = text("""
    SELECT r.id,
      CASE WHEN r.cluster_id IS NULL THEN
        (SELECT COUNT(*) FROM clients)
        - (SELECT COUNT(*) FROM loyalty_rule_custom_clients x WHERE x.rule_id = r.id AND x.is_excluded)
      ELSE
        (SELECT COUNT(*) FROM client_cluster_mapping m WHERE m.cluster_id = r.cluster_id AND NOT EXISTS (
            SELECT 1 FROM loyalty_rule_custom_clients x WHERE x.rule_id = r.id AND x.client_id = m.client_id AND x.is_excluded))
        + (SELECT COUNT(*) FROM loyalty_rule_custom_clients x
           LEFT JOIN client_cluster_mapping m ON m.client_id = x.client_id
           WHERE x.rule_id = r.id AND NOT x.is_excluded AND m.cluster_id IS DISTINCT FROM r.cluster_id)
      END AS audience
    FROM loyalty_rules r
""")

AUDIENCE_SQL = """
    SELECT c.id, c.external_code, c.full_name, c.phone_enc, COALESCE(cl.cluster_label, 'Не сегментирован') AS cluster_label,
           COALESCE((SELECT SUM(t.total_amount) FROM transactions t WHERE t.client_id = c.id AND t.status = 'проведен'), 0)
               AS total_spent,
           (x.client_id IS NOT NULL AND NOT x.is_excluded) AS is_custom_included
    FROM clients c
    LEFT JOIN client_cluster_mapping m ON m.client_id = c.id
    LEFT JOIN clusters cl ON cl.id = m.cluster_id
    LEFT JOIN loyalty_rule_custom_clients x ON x.client_id = c.id AND x.rule_id = :rule_id
    WHERE (x.is_excluded IS NULL OR NOT x.is_excluded)
      AND (CAST(:cluster_id AS BIGINT) IS NULL OR m.cluster_id = :cluster_id OR (x.client_id IS NOT NULL AND NOT x.is_excluded))
      {extra}
    ORDER BY is_custom_included DESC, total_spent DESC, c.id
"""


async def _rule(db: AsyncSession, rule_id: int) -> LoyaltyRule:
    rule = (await db.execute(select(LoyaltyRule).where(LoyaltyRule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Правило лояльности не найдено.")
    return rule


async def _check_cluster(db: AsyncSession, cluster_id: int | None) -> None:
    if cluster_id is None:
        return
    run = await get_approved_run(db)
    cluster = (await db.execute(select(Cluster).where(Cluster.id == cluster_id))).scalar_one_or_none()
    if cluster is None or run is None or cluster.run_id != run.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Сегмент не принадлежит утвержденной модели сегментации.")


async def _out(db: AsyncSession, rules: list[LoyaltyRule]) -> list[RuleOut]:
    clusters = {c.id: c for c in (await db.execute(select(Cluster))).scalars()}
    users = dict((await db.execute(select(User.id, User.username))).all())
    counts = dict((await db.execute(AUDIENCE_COUNT_SQL)).all())
    return [
        RuleOut(
            id=r.id, cluster_id=r.cluster_id,
            cluster_label=clusters[r.cluster_id].cluster_label if r.cluster_id in clusters else GENERAL,
            segment_code=clusters[r.cluster_id].segment_code if r.cluster_id in clusters else None,
            rule_name=r.rule_name, reward_type=r.reward_type, reward_value=r.reward_value,
            min_check_amount=r.min_check_amount, days_valid=r.days_valid, is_active=r.is_active,
            audience_count=counts.get(r.id, 0), created_by=users.get(r.created_by_user_id),
            created_at=r.created_at, updated_at=r.updated_at,
        )
        for r in rules
    ]


@router.get("/rules", response_model=list[RuleOut], summary="Реестр правил программы лояльности")
async def list_rules(db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    rules = (await db.execute(select(LoyaltyRule).order_by(LoyaltyRule.is_active.desc(), LoyaltyRule.created_at.desc()))).scalars()
    return await _out(db, list(rules))


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, summary="Создать правило лояльности")
async def create_rule(payload: RuleCreate, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(marketer)):
    await _check_cluster(db, payload.cluster_id)
    rule = LoyaltyRule(**payload.model_dump(), created_by_user_id=user.id)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await audit("Создание правила лояльности", user=user, object_type="правило", object_id=rule.id, request=request,
                details=payload.model_dump(mode="json"))
    return (await _out(db, [rule]))[0]


@router.put("/rules/{rule_id}", response_model=RuleOut, summary="Изменить правило лояльности")
async def update_rule(rule_id: int, payload: RuleUpdate, request: Request, db: AsyncSession = Depends(get_db),
                      user: User = Depends(marketer)):
    rule = await _rule(db, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    if "cluster_id" in changes:
        await _check_cluster(db, changes["cluster_id"])
    for key, value in changes.items():
        setattr(rule, key, value)
    if rule.reward_type != "баллы" and rule.reward_value > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Размер скидки или кешбэка не может превышать 100 %.")
    await db.commit()
    await db.refresh(rule)
    await audit("Изменение правила лояльности", user=user, object_type="правило", object_id=rule.id, request=request,
                details=payload.model_dump(mode="json", exclude_unset=True))
    return (await _out(db, [rule]))[0]


@router.delete("/rules/{rule_id}", response_model=StatusMessage, summary="Удалить правило лояльности")
async def delete_rule(rule_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(marketer)):
    rule = await _rule(db, rule_id)
    await db.delete(rule)
    await db.commit()
    await audit("Удаление правила лояльности", user=user, object_type="правило", object_id=rule_id, request=request)
    return StatusMessage(message="Правило удалено.")


async def _audience(db: AsyncSession, rule: LoyaltyRule, search: str | None, limit: int | None):
    extra, params = "", {"rule_id": rule.id, "cluster_id": rule.cluster_id}
    if search and search.strip():
        ids = await phone_lookup_ids(db, search)
        extra = "AND (c.full_name ILIKE :q OR c.external_code ILIKE :q OR c.id = ANY(:ids))"
        params |= {"q": f"%{search.strip()}%", "ids": ids}
    sql = AUDIENCE_SQL.format(extra=extra) + (" LIMIT :limit" if limit else "")
    if limit:
        params["limit"] = limit
    return (await db.execute(text(sql), params)).all()


@router.get("/rules/{rule_id}/clients", response_model=AudienceResponse, summary="Аудитория правила с учетом ручных изменений")
async def rule_clients(rule_id: int, search: str | None = Query(None, max_length=100), limit: int = Query(100, ge=1, le=500),
                       db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    rule = await _rule(db, rule_id)
    out = (await _out(db, [rule]))[0]
    rows = await _audience(db, rule, search, limit)
    excluded = (await db.execute(select(LoyaltyRuleCustomClient).where(
        LoyaltyRuleCustomClient.rule_id == rule_id, LoyaltyRuleCustomClient.is_excluded.is_(True)))).scalars().all()
    return AudienceResponse(
        rule_id=rule.id, rule_name=rule.rule_name, cluster_label=out.cluster_label, total_count=out.audience_count,
        excluded_count=len(excluded),
        clients=[AudienceClient(client_id=r.id, external_code=r.external_code, full_name=r.full_name,
                                phone=decrypt_pii(r.phone_enc), cluster_label=r.cluster_label, total_spent=r.total_spent,
                                is_custom_included=r.is_custom_included) for r in rows],
    )


@router.get("/rules/{rule_id}/export", summary="Выгрузить аудиторию правила для рассылки (CSV или Excel)")
async def export_rule(rule_id: int, request: Request, format: Literal["csv", "xlsx"] = "csv",
                      db: AsyncSession = Depends(get_db), user: User = Depends(marketer)) -> Response:
    rule = await _rule(db, rule_id)
    rows = await _audience(db, rule, None, None)
    headers = ["Номер телефона", "ФИО", "Код клиента", "Сегмент", "Предложение", "Размер выгоды",
               "Мин. сумма чека (BYN)", "Срок действия (дней)", "Сумма покупок (BYN)"]
    data = [[decrypt_pii(r.phone_enc), r.full_name, r.external_code, r.cluster_label, rule.rule_name, describe_reward(rule),
             float(rule.min_check_amount), rule.days_valid, float(r.total_spent)] for r in rows]
    await audit("Выгрузка данных", user=user, object_type="правило", object_id=rule.id, request=request,
                details={"type": "аудитория правила", "rows": len(data), "format": format})
    return file_response(headers, data, f"campaign_{slug(rule.rule_name)}", format)


async def _custom(db: AsyncSession, rule_id: int, client_id: int, excluded: bool) -> Client:
    await _rule(db, rule_id)
    client = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Клиент не найден.")
    await db.execute(pg_insert(LoyaltyRuleCustomClient).values(rule_id=rule_id, client_id=client_id, is_excluded=excluded)
                     .on_conflict_do_update(index_elements=["rule_id", "client_id"], set_={"is_excluded": excluded}))
    await db.commit()
    return client


@router.post("/rules/{rule_id}/clients", response_model=StatusMessage, summary="Вручную прикрепить клиента к правилу")
async def attach_client(rule_id: int, payload: AttachClientRequest, request: Request, db: AsyncSession = Depends(get_db),
                        user: User = Depends(marketer)):
    client = await _custom(db, rule_id, payload.client_id, excluded=False)
    await audit("Ручное включение клиента в правило", user=user, object_type="правило", object_id=rule_id, request=request,
                details={"client_id": client.id})
    return StatusMessage(message=f"Клиент {client.full_name} прикреплен к правилу.")


@router.delete("/rules/{rule_id}/clients/{client_id}", response_model=StatusMessage, summary="Исключить клиента из правила")
async def exclude_client(rule_id: int, client_id: int, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(marketer)):
    client = await _custom(db, rule_id, client_id, excluded=True)
    await audit("Исключение клиента из правила", user=user, object_type="правило", object_id=rule_id, request=request,
                details={"client_id": client.id})
    return StatusMessage(message=f"Клиент {client.full_name} исключен из правила.")


@router.post("/calculate-discount", response_model=DiscountResponse, summary="Расчет персональной выгоды по чеку на кассе")
async def calculate_discount(payload: DiscountRequest, db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    if payload.client_id is not None:
        ids = [payload.client_id]
    elif payload.phone and payload.phone.strip():
        ids = await phone_lookup_ids(db, payload.phone)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Укажите идентификатор клиента или номер телефона.")
    if len(ids) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Найдено несколько клиентов. Уточните номер телефона полностью.")
    client = (await db.execute(select(Client).where(Client.id.in_(ids)))).scalar_one_or_none() if ids else None
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Клиент не найден в базе данных.")

    cluster = (await db.execute(select(Cluster).join(ClientClusterMapping, ClientClusterMapping.cluster_id == Cluster.id)
                                .where(ClientClusterMapping.client_id == client.id))).scalar_one_or_none()
    custom = (await db.execute(select(LoyaltyRuleCustomClient).where(LoyaltyRuleCustomClient.client_id == client.id))).scalars().all()
    included = {c.rule_id for c in custom if not c.is_excluded}
    excluded = {c.rule_id for c in custom if c.is_excluded}
    rules = (await db.execute(select(LoyaltyRule).where(LoyaltyRule.is_active.is_(True)))).scalars().all()
    rule = select_best_rule(list(rules), cluster.id if cluster else None, included, excluded, payload.check_amount)
    benefit = calculate_benefit(rule, payload.check_amount)
    return DiscountResponse(
        client_id=client.id, client_name=client.full_name, external_code=client.external_code,
        cluster_label=cluster.cluster_label if cluster else "Не сегментирован",
        applied_rule_id=rule.id if rule else None, applied_rule_name=rule.rule_name if rule else None,
        reward_type=rule.reward_type if rule else None, reward_value=rule.reward_value if rule else None,
        original_amount=payload.check_amount, discount_amount=benefit.discount, bonus_amount=benefit.bonus,
        final_amount=benefit.final, benefit_description=benefit.description,
    )
