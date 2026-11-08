"""Клиентская база: поиск по зашифрованным контактам, реестр и профиль клиента."""
import math
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decrypt_pii,
    email_hash,
    encrypt_pii,
    normalize_phone,
    phone_digits,
    phone_hash,
    phone_tail_hash,
)
from app.models.client import Client
from app.models.cluster import ClientClusterMapping, Cluster
from app.models.loyalty import LoyaltyRule, LoyaltyRuleCustomClient
from app.models.transaction import Transaction
from app.schemas.client import (
    ClientListItem,
    ClientListResponse,
    ClientProfile,
    ClientRuleItem,
    ClientTransaction,
)
from app.services.loyalty import applicable_rules


async def phone_lookup_ids(db: AsyncSession, raw: str) -> list[int]:
    """Поиск по номеру телефона через хеш-индексы: полный номер или последние 7 цифр."""
    digits = phone_digits(raw)
    e164 = normalize_phone(raw)
    if e164:
        stmt = select(Client.id).where(Client.phone_hash == phone_hash(e164))
    elif len(digits) >= 7:
        stmt = select(Client.id).where(Client.phone_tail_hash == phone_tail_hash(digits))
    else:
        return []
    return list((await db.execute(stmt)).scalars())


def new_client(external_code: str, full_name: str, phone: str, email: str | None = None) -> Client:
    e164 = normalize_phone(phone)
    if e164 is None:
        raise ValueError(f"номер телефона «{phone}» не соответствует формату +375XXXXXXXXX")
    email = (email or "").strip() or None
    return Client(
        external_code=external_code, full_name=full_name.strip(),
        phone_enc=encrypt_pii(e164), phone_hash=phone_hash(e164), phone_tail_hash=phone_tail_hash(e164),
        email_enc=encrypt_pii(email), email_hash=email_hash(email) if email else None,
    )


async def list_clients(db: AsyncSession, page: int, limit: int, search: str | None, cluster_id: int | None) -> ClientListResponse:
    conditions = []
    if search and search.strip():
        query = search.strip()
        by_phone = await phone_lookup_ids(db, query) if len(phone_digits(query)) >= 7 else []
        pattern = f"%{query}%"
        conditions.append(or_(Client.full_name.ilike(pattern), Client.external_code.ilike(pattern), Client.id.in_(by_phone)))
    if cluster_id is not None:
        conditions.append(ClientClusterMapping.cluster_id == cluster_id)

    base = select(Client.id).outerjoin(ClientClusterMapping, ClientClusterMapping.client_id == Client.id).where(*conditions)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    ids = list((await db.execute(base.order_by(Client.id).limit(limit).offset((page - 1) * limit))).scalars())

    rows = (await db.execute(text("""
        SELECT c.id, c.external_code, c.full_name, c.phone_enc,
               MAX(t.transaction_date) FILTER (WHERE t.status = 'проведен') AS last_purchase_date,
               COUNT(t.id) FILTER (WHERE t.status = 'проведен') AS frequency,
               COALESCE(SUM(t.total_amount) FILTER (WHERE t.status = 'проведен'), 0) AS total_spent,
               m.cluster_id, cl.cluster_label, cl.segment_code
        FROM clients c
        LEFT JOIN transactions t ON t.client_id = c.id
        LEFT JOIN client_cluster_mapping m ON m.client_id = c.id
        LEFT JOIN clusters cl ON cl.id = m.cluster_id
        WHERE c.id = ANY(:ids)
        GROUP BY c.id, m.cluster_id, cl.cluster_label, cl.segment_code
        ORDER BY c.id
    """), {"ids": ids})).all() if ids else []
    items = [
        ClientListItem(
            id=r.id, external_code=r.external_code, full_name=r.full_name, phone=decrypt_pii(r.phone_enc),
            last_purchase_date=r.last_purchase_date, frequency=r.frequency, total_spent=r.total_spent,
            cluster_id=r.cluster_id, cluster_label=r.cluster_label, segment_code=r.segment_code,
        )
        for r in rows
    ]
    return ClientListResponse(items=items, total=total, page=page, limit=limit, pages=max(1, math.ceil(total / limit)))


async def client_profile(db: AsyncSession, client_id: int) -> ClientProfile:
    client = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Данные клиента недоступны: клиент не найден.")
    stats = (await db.execute(text("""
        WITH ref AS (SELECT COALESCE(MAX(transaction_date), CURRENT_TIMESTAMP) AS ts FROM transactions WHERE status = 'проведен')
        SELECT ROUND((EXTRACT(EPOCH FROM (ref.ts - MAX(t.transaction_date) FILTER (WHERE t.status = 'проведен'))) / 86400.0)::numeric, 1) AS recency,
               COUNT(*) FILTER (WHERE t.status = 'проведен') AS frequency,
               COALESCE(SUM(t.total_amount) FILTER (WHERE t.status = 'проведен'), 0) AS monetary,
               COUNT(*) FILTER (WHERE t.status = 'отменен') AS cancelled
        FROM ref LEFT JOIN transactions t ON t.client_id = :cid
        GROUP BY ref.ts
    """), {"cid": client_id})).one()
    mapping = (await db.execute(
        select(Cluster).join(ClientClusterMapping, ClientClusterMapping.cluster_id == Cluster.id)
        .where(ClientClusterMapping.client_id == client_id))).scalar_one_or_none()
    transactions = (await db.execute(
        select(Transaction).where(Transaction.client_id == client_id)
        .order_by(Transaction.transaction_date.desc()).limit(50))).scalars().all()

    custom = (await db.execute(
        select(LoyaltyRuleCustomClient).where(LoyaltyRuleCustomClient.client_id == client_id))).scalars().all()
    included = {c.rule_id for c in custom if not c.is_excluded}
    excluded = {c.rule_id for c in custom if c.is_excluded}
    rules = (await db.execute(select(LoyaltyRule).where(LoyaltyRule.is_active.is_(True)))).scalars().all()
    cluster_id = mapping.id if mapping else None
    rule_items = [
        ClientRuleItem(
            id=r.id, rule_name=r.rule_name, reward_type=r.reward_type, reward_value=r.reward_value,
            min_check_amount=r.min_check_amount, days_valid=r.days_valid,
            source="персональное" if r.id in included else ("сегментное" if r.cluster_id == cluster_id else "общее"),
        )
        for r in applicable_rules(rules, cluster_id, included, excluded)
    ]
    frequency = stats.frequency or 0
    monetary = Decimal(stats.monetary or 0)
    return ClientProfile(
        id=client.id, external_code=client.external_code, full_name=client.full_name, phone=client.phone,
        email=client.email, created_at=client.created_at,
        recency_days=float(stats.recency) if stats.recency is not None else None,
        frequency=frequency, monetary=monetary,
        avg_check=(monetary / frequency).quantize(Decimal("0.01")) if frequency else Decimal("0.00"),
        cancelled_count=stats.cancelled or 0,
        cluster_id=cluster_id, cluster_label=mapping.cluster_label if mapping else None,
        segment_code=mapping.segment_code if mapping else None,
        transactions=[ClientTransaction(id=t.id, transaction_date=t.transaction_date, total_amount=t.total_amount,
                                        discount_amount=t.discount_amount, status=t.status) for t in transactions],
        rules=rule_items,
    )
