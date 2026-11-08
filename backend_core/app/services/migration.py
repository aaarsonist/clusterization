"""Мониторинг миграции клиентов между сегментами (срезы T0/T1) и маркетинговые выгрузки."""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_pii
from app.models.cluster import (
    ClientClusterHistory,
    ClientClusterMapping,
    Cluster,
    SegmentationSnapshot,
)
from app.models.loyalty import LoyaltyRule, LoyaltyRuleCustomClient
from app.models.user import User
from app.schemas.segmentation import (
    DrillDownClient,
    DrillDownResponse,
    MarketingAlert,
    MatrixSegment,
    MigrationClient,
    MigrationDashboard,
    MigrationSummary,
    SnapshotInfo,
    SnapshotResponse,
    TransitionMatrix,
)
from app.services.ai_gateway import ai_gateway
from app.services.audit import audit
from app.services.loyalty import describe_reward, select_best_rule
from app.services.segmentation import TIER, compute_rfm, get_approved_run

CENT = Decimal("0.01")


def money(value: Decimal | float) -> str:
    return f"{Decimal(value).quantize(Decimal('1'), ROUND_HALF_UP):,}".replace(",", " ")


async def create_snapshot(db: AsyncSession, user: User | None) -> SnapshotResponse:
    """Срез T1: новые RFM-векторы классифицируются по центроидам утвержденной модели в ИИ-сервисе."""
    run = await get_approved_run(db)
    if run is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Базовая модель не утверждена. Сначала утвердите модель (срез T0).")
    clusters = (await db.execute(select(Cluster).where(Cluster.run_id == run.id))).scalars().all()
    centroids = [
        {"cluster_no": c.cluster_no, "z_center": [c.z_recency, c.z_frequency, c.z_monetary]}
        for c in clusters if c.segment_code != "noise" and c.z_recency is not None
    ]
    no_to_id = {c.cluster_no: c.id for c in clusters}
    reference_date, rows = await compute_rfm(db, run.days_period)
    labels = await ai_gateway.assign(
        [[r, float(f), float(m)] for _, r, f, m in rows], run.scaler_params, centroids)

    previous = dict((await db.execute(select(ClientClusterMapping.client_id, ClientClusterMapping.cluster_id))).all())
    pairs = [(row[0], no_to_id[label]) for row, label in zip(rows, labels, strict=True)]
    changed = sum(1 for cid, cl in pairs if previous.get(cid) not in (None, cl))

    now = datetime.now(timezone.utc)
    snapshot = SegmentationSnapshot(run_id=run.id, kind="T1", reference_date=reference_date,
                                    created_by_user_id=user.id if user else None)
    db.add(snapshot)
    await db.flush()
    await db.execute(insert(ClientClusterHistory), [
        {"snapshot_id": snapshot.id, "client_id": cid, "cluster_id": cl} for cid, cl in pairs])
    await db.execute(delete(ClientClusterMapping))
    await db.execute(insert(ClientClusterMapping), [
        {"client_id": cid, "cluster_id": cl, "updated_at": now} for cid, cl in pairs])
    await db.commit()
    await audit("Фиксация среза T1", user=user, object_type="срез", object_id=snapshot.id,
                details={"clients": len(pairs), "changed": changed})
    return SnapshotResponse(snapshot_id=snapshot.id, run_id=run.id, tracked_clients=len(pairs),
                            changed_clients=changed, reference_date=reference_date)


async def list_snapshots(db: AsyncSession, run_id: int) -> list[SnapshotInfo]:
    rows = (await db.execute(
        select(SegmentationSnapshot, func.count(ClientClusterHistory.client_id))
        .outerjoin(ClientClusterHistory, ClientClusterHistory.snapshot_id == SegmentationSnapshot.id)
        .where(SegmentationSnapshot.run_id == run_id)
        .group_by(SegmentationSnapshot.id).order_by(SegmentationSnapshot.created_at))).all()
    return [SnapshotInfo(id=s.id, kind=s.kind, reference_date=s.reference_date, created_at=s.created_at, clients=n)
            for s, n in rows]


def direction(old_code: str, new_code: str, same: bool) -> str:
    if same:
        return "neutral"
    if new_code == "churn" or TIER[new_code] < TIER[old_code]:
        return "negative"
    if TIER[new_code] > TIER[old_code]:
        return "positive"
    return "neutral"


async def _transitions(db: AsyncSession, run_id: int, from_id: int, to_id: int):
    return (await db.execute(text("""
        SELECT a.client_id, a.cluster_id AS old_id, b.cluster_id AS new_id,
               c.external_code, c.full_name, c.phone_enc, COALESCE(cf.monetary, 0) AS monetary_t0
        FROM client_cluster_history a
        JOIN client_cluster_history b ON b.client_id = a.client_id AND b.snapshot_id = :to_id
        JOIN clients c ON c.id = a.client_id
        LEFT JOIN client_features cf ON cf.run_id = :run_id AND cf.client_id = a.client_id
        WHERE a.snapshot_id = :from_id
        ORDER BY a.client_id
    """), {"from_id": from_id, "to_id": to_id, "run_id": run_id})).all()


async def _resolve_snapshots(db: AsyncSession, run_id: int, from_id: int | None, to_id: int | None):
    snapshots = await list_snapshots(db, run_id)
    by_id = {s.id: s for s in snapshots}
    if len(snapshots) < 2:
        return snapshots, None, None
    first = by_id.get(from_id) if from_id else snapshots[0]
    last = by_id.get(to_id) if to_id else snapshots[-1]
    if first is None or last is None or first.id == last.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Выберите два различных среза утвержденной модели.")
    return snapshots, first, last


async def migration_dashboard(db: AsyncSession, from_id: int | None = None, to_id: int | None = None) -> MigrationDashboard:
    run = await get_approved_run(db)
    if run is None:
        return MigrationDashboard(state="need_baseline", message=(
            "Для мониторинга миграции утвердите модель сегментации в разделе «Сегментация и анализ»."))
    snapshots, first, last = await _resolve_snapshots(db, run.id, from_id, to_id)
    if first is None:
        return MigrationDashboard(state="need_second_snapshot", snapshots=snapshots, message=(
            "Срез T0 зафиксирован. Для построения матрицы переходов зафиксируйте срез T1 после накопления новых покупок."))

    clusters = (await db.execute(select(Cluster).where(Cluster.run_id == run.id))).scalars().all()
    clusters = sorted(clusters, key=lambda c: (-TIER[c.segment_code], -c.client_count))
    index = {c.id: i for i, c in enumerate(clusters)}
    code = {c.id: c.segment_code for c in clusters}
    label = {c.id: c.cluster_label for c in clusters}
    k = len(clusters)
    matrix = [[0] * k for _ in range(k)]

    rows = await _transitions(db, run.id, first.id, last.id)
    retained = churn = upgrade = downgrade = 0
    vip_to_churn, vip_loss, newbie_up = 0, Decimal("0"), 0
    newbie_targets: dict[int, int] = {}
    sample: list[tuple] = []
    for r in rows:
        matrix[index[r.old_id]][index[r.new_id]] += 1
        same = r.old_id == r.new_id
        d = direction(code[r.old_id], code[r.new_id], same)
        if same:
            retained += 1
        elif code[r.new_id] == "churn":
            churn += 1
            if code[r.old_id] == "vip":
                vip_to_churn += 1
                vip_loss += Decimal(r.monetary_t0) * 30 / run.days_period
        elif d == "positive":
            upgrade += 1
            if code[r.old_id] == "newbie":
                newbie_up += 1
                newbie_targets[r.new_id] = newbie_targets.get(r.new_id, 0) + 1
        elif d == "negative":
            downgrade += 1
        if not same:
            sample.append((d, r))

    total = len(rows)
    churn_cluster = next((c.id for c in clusters if c.segment_code == "churn"), None)
    alerts: list[MarketingAlert] = []
    if vip_to_churn:
        alerts.append(MarketingAlert(
            id="vip-churn", type="critical", title="Риск потери оборота лояльных лидеров",
            message=(f"{vip_to_churn} клиентов из сегмента «Лояльные лидеры» перешли в зону риска оттока. "
                     f"Ежемесячный оборот под угрозой — {money(vip_loss)} BYN. Рекомендуется реактивационное предложение."),
            action_label="Создать реактивационное предложение", impact=f"−{money(vip_loss)} BYN/мес.",
            target_cluster_id=churn_cluster))
    if newbie_up:
        target = max(newbie_targets, key=newbie_targets.get)
        alerts.append(MarketingAlert(
            id="newbie-up", type="success", title="Новички стали постоянными клиентами",
            message=f"{newbie_up} новичков перешли в более ценные сегменты. Рекомендуется закрепить поведение персональным бонусом.",
            action_label="Создать персональный бонус", impact=f"+{newbie_up} клиентов", target_cluster_id=target))
    if churn:
        alerts.append(MarketingAlert(
            id="churn-drift", type="warning", title="Переток в зону риска оттока",
            message=f"В сегменты зоны риска оттока перешли {churn} клиентов. Рекомендуется запустить удерживающую рассылку.",
            action_label="Создать удерживающее предложение", impact=f"{churn} клиентов", target_cluster_id=churn_cluster))
    if upgrade:
        alerts.append(MarketingAlert(
            id="upgrade", type="info", title="Рост ценности клиентов",
            message=f"{upgrade} клиентов перешли в сегменты с более высокой ценностью за период наблюдения.",
            action_label="Открыть правила", impact=f"+{upgrade} клиентов"))

    sample.sort(key=lambda item: ({"negative": 0, "positive": 1}.get(item[0], 2), item[1].client_id))
    clients_sample = [
        MigrationClient(
            client_id=r.client_id, external_code=r.external_code, full_name=r.full_name, phone=decrypt_pii(r.phone_enc),
            old_cluster_id=r.old_id, old_segment=label[r.old_id], new_cluster_id=r.new_id, new_segment=label[r.new_id],
            direction=d,
        )
        for d, r in sample[:100]
    ]
    return MigrationDashboard(
        state="ready", message="Мониторинг миграции активен", snapshots=snapshots, from_snapshot=first, to_snapshot=last,
        summary=MigrationSummary(
            total_clients_compared=total, retained=retained, total_migrated=total - retained,
            retention_rate=round(retained / total * 100, 1) if total else 100.0,
            churn_risk_count=churn, upgrade_count=upgrade, downgrade_count=downgrade),
        matrix=TransitionMatrix(
            segments=[MatrixSegment(cluster_id=c.id, cluster_label=c.cluster_label, segment_code=c.segment_code)
                      for c in clusters],
            matrix=matrix,
            total_from=[sum(row) for row in matrix],
            total_to=[sum(matrix[i][j] for i in range(k)) for j in range(k)]),
        alerts=alerts, clients_sample=clients_sample,
    )


async def drilldown(db: AsyncSession, from_cluster: int, to_cluster: int,
                    from_id: int | None = None, to_id: int | None = None) -> DrillDownResponse:
    """Состав ячейки матрицы переходов с оценкой ежемесячного оборота, затронутого переходом."""
    run = await get_approved_run(db)
    if run is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Базовая модель не утверждена.")
    _, first, last = await _resolve_snapshots(db, run.id, from_id, to_id)
    if first is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Для детализации требуется не менее двух срезов.")
    clusters = {c.id: c for c in (await db.execute(select(Cluster).where(Cluster.run_id == run.id))).scalars()}
    if from_cluster not in clusters or to_cluster not in clusters:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сегмент не принадлежит утвержденной модели.")
    old, new = clusters[from_cluster], clusters[to_cluster]
    d = direction(old.segment_code, new.segment_code, from_cluster == to_cluster)
    _, current = await compute_rfm(db, run.days_period)
    current_rfm = {cid: (r, f, m) for cid, r, f, m in current}

    items: list[DrillDownClient] = []
    turnover = impact_total = Decimal("0")
    for r in await _transitions(db, run.id, first.id, last.id):
        if r.old_id != from_cluster or r.new_id != to_cluster:
            continue
        rec, freq, mon = current_rfm.get(r.client_id, (0.0, 0, Decimal("0")))
        monthly = (Decimal(r.monetary_t0) * 30 / run.days_period).quantize(CENT, ROUND_HALF_UP)
        impact = -monthly if d == "negative" else (monthly if d == "positive" else Decimal("0.00"))
        turnover += Decimal(mon)
        impact_total += impact
        items.append(DrillDownClient(
            client_id=r.client_id, external_code=r.external_code, full_name=r.full_name, phone=decrypt_pii(r.phone_enc),
            recency_days=rec, frequency=freq, monetary=Decimal(mon), financial_impact=impact,
            impact_type={"negative": "loss", "positive": "gain"}.get(d, "neutral"),
        ))
    items.sort(key=lambda c: c.monetary, reverse=True)
    seg = lambda c: MatrixSegment(cluster_id=c.id, cluster_label=c.cluster_label, segment_code=c.segment_code)  # noqa: E731
    return DrillDownResponse(from_cluster=seg(old), to_cluster=seg(new), total_clients=len(items),
                             total_turnover=turnover, total_financial_impact=impact_total, clients=items)


DIRECTION_LABELS = {"neutral": "Без изменений", "positive": "Рост ценности", "negative": "Снижение ценности или риск оттока"}


async def migration_export_rows(db: AsyncSession, from_id: int | None, to_id: int | None):
    run = await get_approved_run(db)
    if run is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Базовая модель не утверждена. Выгрузка невозможна.")
    _, first, last = await _resolve_snapshots(db, run.id, from_id, to_id)
    if first is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Для выгрузки миграции требуется не менее двух срезов.")
    clusters = {c.id: c for c in (await db.execute(select(Cluster).where(Cluster.run_id == run.id))).scalars()}
    headers = ["Номер телефона", "ФИО", "Код клиента", "Сегмент в начале периода", "Сегмент в конце периода",
               "Направление", "Сумма покупок за период T0 (BYN)"]
    rows = []
    for r in await _transitions(db, run.id, first.id, last.id):
        old, new = clusters[r.old_id], clusters[r.new_id]
        d = direction(old.segment_code, new.segment_code, r.old_id == r.new_id)
        rows.append([decrypt_pii(r.phone_enc), r.full_name, r.external_code, old.cluster_label, new.cluster_label,
                     DIRECTION_LABELS[d], float(r.monetary_t0)])
    return headers, rows


async def mailing_export_rows(db: AsyncSession, cluster_id: int | None):
    """Список рассылки (UC-9): контакты, сегмент и наиболее выгодное применимое предложение для каждого клиента."""
    where = "WHERE m.cluster_id = :cluster_id" if cluster_id is not None else ""
    clients = (await db.execute(text(f"""
        SELECT c.id, c.full_name, c.external_code, c.phone_enc, m.cluster_id, cl.cluster_label,
               COALESCE(SUM(t.total_amount) FILTER (WHERE t.status = 'проведен'), 0) AS total_spent
        FROM clients c
        LEFT JOIN client_cluster_mapping m ON m.client_id = c.id
        LEFT JOIN clusters cl ON cl.id = m.cluster_id
        LEFT JOIN transactions t ON t.client_id = c.id
        {where}
        GROUP BY c.id, m.cluster_id, cl.cluster_label
        ORDER BY c.id
    """), {"cluster_id": cluster_id} if cluster_id is not None else {})).all()
    rules = (await db.execute(select(LoyaltyRule).where(LoyaltyRule.is_active.is_(True)))).scalars().all()
    custom: dict[int, tuple[set[int], set[int]]] = {}
    for rc in (await db.execute(select(LoyaltyRuleCustomClient))).scalars():
        inc, exc = custom.setdefault(rc.client_id, (set(), set()))
        (exc if rc.is_excluded else inc).add(rc.rule_id)

    headers = ["Номер телефона", "ФИО", "Код клиента", "Сегмент", "Предложение для рассылки", "Размер выгоды",
               "Мин. сумма чека (BYN)", "Срок действия (дней)", "Сумма покупок (BYN)"]
    rows = []
    for c in clients:
        inc, exc = custom.get(c.id, (set(), set()))
        rule = select_best_rule(rules, c.cluster_id, inc, exc)
        rows.append([
            decrypt_pii(c.phone_enc), c.full_name, c.external_code, c.cluster_label or "Не сегментирован",
            rule.rule_name if rule else "Базовые условия", describe_reward(rule),
            float(rule.min_check_amount) if rule else 0.0, rule.days_valid if rule else "—", float(c.total_spent),
        ])
    label = clients[0].cluster_label if cluster_id is not None and clients else None
    return headers, rows, label


async def drilldown_export_rows(db: AsyncSession, from_cluster: int, to_cluster: int, from_id: int | None, to_id: int | None):
    data = await drilldown(db, from_cluster, to_cluster, from_id, to_id)
    headers = ["Номер телефона", "ФИО", "Код клиента", "Давность (дней)", "Чеков за период", "Сумма покупок за период (BYN)",
               "Влияние на оборот (BYN/мес.)"]
    rows = [[c.phone, c.full_name, c.external_code, c.recency_days, c.frequency, float(c.monetary), float(c.financial_impact)]
            for c in data.clients]
    return headers, rows, f"{data.from_cluster.cluster_label}_{data.to_cluster.cluster_label}"
