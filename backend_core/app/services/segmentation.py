"""Бизнес-логика жизненного цикла модели сегментации.

Этапы: формирование матрицы признаков RFM (черновик) → фоновое сравнение моделей
в интеллектуальном сервисе (расчет → рассчитан/ошибка) → утверждение выбранной модели
пользователем (утвержден, срез T0); ранее утвержденная модель переводится в архив.
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.client import Client
from app.models.cluster import (
    RUN_APPROVED,
    RUN_ARCHIVED,
    RUN_DONE,
    RUN_DRAFT,
    RUN_FAILED,
    RUN_RUNNING,
    ClientClusterHistory,
    ClientClusterMapping,
    ClientFeature,
    Cluster,
    SegmentationRun,
    SegmentationSnapshot,
)
from app.models.loyalty import LoyaltyRule
from app.models.user import User
from app.schemas.common import ClusterBrief
from app.schemas.segmentation import (
    ApproveResponse,
    CurrentSegmentation,
    FeatureStats,
    PointsResponse,
    RunDetail,
    RunInfo,
    ScatterPoint,
)
from app.services.ai_gateway import ai_gateway
from app.services.audit import audit

logger = logging.getLogger("backend_core.segmentation")

ALGORITHMS = ("kmeans", "agglomerative", "dbscan")
LABEL_COLUMNS = {
    "kmeans": ClientFeature.label_kmeans,
    "agglomerative": ClientFeature.label_agglomerative,
    "dbscan": ClientFeature.label_dbscan,
}
TIER = {"vip": 4, "regular": 3, "bargain": 3, "newbie": 2, "churn": 1, "noise": 0}
MAX_POINTS = 5000

_background_tasks: set[asyncio.Task] = set()

# Давность — по всей истории проведенных чеков; частота и сумма — за выбранный период.
RFM_SQL = text("""
    WITH ref AS (
        SELECT COALESCE(MAX(transaction_date), CURRENT_TIMESTAMP) AS ts
        FROM transactions WHERE status = 'проведен'
    )
    SELECT c.id AS client_id,
           ref.ts AS reference_date,
           GREATEST(0, ROUND((EXTRACT(EPOCH FROM (ref.ts - COALESCE(MAX(t.transaction_date), c.created_at)))
                              / 86400.0)::numeric, 1)) AS recency_days,
           COUNT(t.id) FILTER (WHERE t.transaction_date > ref.ts - make_interval(days => :days)) AS frequency,
           COALESCE(SUM(t.total_amount) FILTER (WHERE t.transaction_date > ref.ts - make_interval(days => :days)), 0)
               AS monetary
    FROM clients c
    CROSS JOIN ref
    LEFT JOIN transactions t
           ON t.client_id = c.id AND t.status = 'проведен' AND t.transaction_date <= ref.ts
    GROUP BY c.id, c.created_at, ref.ts
    ORDER BY c.id
""")


async def compute_rfm(db: AsyncSession, days_period: int) -> tuple[datetime, list[tuple[int, float, int, Decimal]]]:
    rows = (await db.execute(RFM_SQL, {"days": days_period})).all()
    if not rows:
        return datetime.now(timezone.utc), []
    return rows[0].reference_date, [(r.client_id, float(r.recency_days), int(r.frequency), r.monetary) for r in rows]


def run_info(run: SegmentationRun, username: str | None = None) -> RunInfo:
    return RunInfo(
        id=run.id, status=run.status, days_period=run.days_period, reference_date=run.reference_date,
        target_k=run.target_k, algorithm=run.algorithm, error_message=run.error_message,
        created_at=run.created_at, completed_at=run.completed_at, approved_at=run.approved_at, created_by=username,
    )


async def _username(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return (await db.execute(select(User.username).where(User.id == user_id))).scalar_one_or_none()


async def get_run(db: AsyncSession, run_id: int, lock: bool = False) -> SegmentationRun:
    stmt = select(SegmentationRun).where(SegmentationRun.id == run_id)
    if lock:
        stmt = stmt.with_for_update()
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Прогон сегментации №{run_id} не найден.")
    return run


async def get_approved_run(db: AsyncSession) -> SegmentationRun | None:
    stmt = select(SegmentationRun).where(SegmentationRun.status == RUN_APPROVED)
    return (await db.execute(stmt)).scalar_one_or_none()


async def feature_stats(db: AsyncSession, run_id: int) -> FeatureStats:
    row = (await db.execute(text("""
        SELECT COUNT(*) AS clients,
               COUNT(*) FILTER (WHERE frequency > 0) AS active,
               COALESCE(AVG(recency_days), 0) AS r_mean,
               COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY recency_days), 0) AS r_med,
               COALESCE(AVG(frequency), 0) AS f_mean,
               COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY frequency), 0) AS f_med,
               COALESCE(AVG(monetary), 0) AS m_mean,
               COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY monetary), 0) AS m_med
        FROM client_features WHERE run_id = :run_id
    """), {"run_id": run_id})).one()
    return FeatureStats(
        clients=row.clients, active_clients=row.active,
        recency_mean=round(float(row.r_mean), 1), recency_median=round(float(row.r_med), 1),
        frequency_mean=round(float(row.f_mean), 2), frequency_median=round(float(row.f_med), 1),
        monetary_mean=round(float(row.m_mean), 2), monetary_median=round(float(row.m_med), 2),
    )


async def run_detail(db: AsyncSession, run: SegmentationRun) -> RunDetail:
    info = run_info(run, await _username(db, run.created_by_user_id))
    return RunDetail(**info.model_dump(), features=await feature_stats(db, run.id), metrics=run.metrics, xai=run.xai)


async def create_run(db: AsyncSession, user: User, days_period: int) -> RunDetail:
    """Шаг 1 (UC-3): расчет и сохранение матрицы признаков RFM за выбранный период."""
    reference_date, rows = await compute_rfm(db, days_period)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В базе данных нет клиентов для анализа.")
    if sum(1 for r in rows if r[2] > 0) < 4:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "За выбранный период недостаточно проведенных чеков для кластеризации. Расширьте интервал анализа.",
        )
    run = SegmentationRun(status=RUN_DRAFT, days_period=days_period, reference_date=reference_date,
                          created_by_user_id=user.id)
    db.add(run)
    await db.flush()
    await db.execute(insert(ClientFeature), [
        {"run_id": run.id, "client_id": cid, "recency_days": r, "frequency": f, "monetary": m}
        for cid, r, f, m in rows
    ])
    await db.commit()
    await db.refresh(run)
    await audit("Формирование матрицы признаков", user=user, object_type="прогон", object_id=run.id,
                details={"days_period": days_period, "clients": len(rows)})
    return await run_detail(db, run)


async def start_benchmark(db: AsyncSession, user: User, run_id: int, target_k: int | None) -> RunDetail:
    """Шаг 2 (UC-4, UC-6): постановка асинхронной задачи сравнения моделей (Async Request-Reply)."""
    run = await get_run(db, run_id, lock=True)
    if run.status == RUN_RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Расчет по данному прогону уже выполняется.")
    if run.status in (RUN_APPROVED, RUN_ARCHIVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Прогон уже утвержден. Сформируйте новую матрицу признаков.")
    run.status, run.target_k, run.error_message = RUN_RUNNING, target_k, None
    await db.commit()
    task = asyncio.create_task(_benchmark_job(run.id, target_k, user.id, user.username))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return await run_detail(db, run)


async def _mark_failed(run_id: int, message: str) -> None:
    async with async_session_maker() as db:
        await db.execute(update(SegmentationRun).where(SegmentationRun.id == run_id).values(
            status=RUN_FAILED, error_message=message[:2000], completed_at=datetime.now(timezone.utc)))
        await db.commit()


async def _benchmark_job(run_id: int, target_k: int | None, user_id: int, username: str) -> None:
    try:
        async with async_session_maker() as db:
            rows = (await db.execute(
                select(ClientFeature.client_id, ClientFeature.recency_days, ClientFeature.frequency, ClientFeature.monetary)
                .where(ClientFeature.run_id == run_id).order_by(ClientFeature.client_id)
            )).all()
            # Обезличивание: в ИИ-сервис передаются только числовые векторы без идентификаторов клиентов
            vectors = [[float(r.recency_days), float(r.frequency), float(r.monetary)] for r in rows]
            result = await ai_gateway.benchmark(vectors, target_k)

            models = {m["algorithm_id"]: m for m in result["models"]}
            coords = result["pca_coords"]
            await db.execute(update(ClientFeature), [
                {
                    "run_id": run_id, "client_id": r.client_id,
                    "pca_x": coords[i][0], "pca_y": coords[i][1],
                    "label_kmeans": models["kmeans"]["labels"][i],
                    "label_agglomerative": models["agglomerative"]["labels"][i],
                    "label_dbscan": models["dbscan"]["labels"][i],
                }
                for i, r in enumerate(rows)
            ])
            run = await get_run(db, run_id)
            run.scaler_params = result["scaler"]
            run.metrics = {
                "n_samples": result["n_samples"],
                "duration_ms": result["duration_ms"],
                "models": [{k: v for k, v in m.items() if k != "labels"} for m in result["models"]],
            }
            run.xai = {**result["xai"], "winner": result["winner"]}
            run.status, run.completed_at = RUN_DONE, datetime.now(timezone.utc)
            await db.commit()
        await audit("Сравнение моделей кластеризации", username=username, object_type="прогон", object_id=run_id,
                    details={"winner": result["winner"]["algorithm_id"], "n_samples": result["n_samples"],
                             "duration_ms": result["duration_ms"], "low_quality": result["winner"]["low_quality"]})
    except HTTPException as exc:
        await _mark_failed(run_id, str(exc.detail))
        await audit("Сравнение моделей кластеризации", username=username, object_type="прогон", object_id=run_id,
                    success=False, details={"error": str(exc.detail)})
    except Exception as exc:  # фиксация любого сбоя фоновой задачи в статусе прогона
        logger.exception("Сбой фоновой задачи сравнения моделей", extra={"run_id": run_id})
        await _mark_failed(run_id, f"Внутренняя ошибка расчета: {exc}")


async def fail_interrupted_runs() -> None:
    """При старте сервера прогоны, прерванные перезапуском, переводятся в статус ошибки."""
    async with async_session_maker() as db:
        await db.execute(update(SegmentationRun).where(SegmentationRun.status == RUN_RUNNING).values(
            status=RUN_FAILED, error_message="Расчет прерван перезапуском сервера.", completed_at=datetime.now(timezone.utc)))
        await db.commit()


def model_of(run: SegmentationRun, algorithm: str) -> dict[str, Any]:
    for model in (run.metrics or {}).get("models", []):
        if model["algorithm_id"] == algorithm:
            return model
    raise HTTPException(status.HTTP_409_CONFLICT, "Результаты модели для данного прогона отсутствуют.")


async def get_points(db: AsyncSession, run_id: int, algorithm: str) -> PointsResponse:
    """Точки двумерной проекции PCA; при большой базе — детерминированная подвыборка (не более 5000 точек)."""
    run = await get_run(db, run_id)
    labels = {c["cluster_no"]: c["cluster_label"] for c in model_of(run, algorithm)["clusters"]}
    column = LABEL_COLUMNS[algorithm]
    total = (await db.execute(select(func.count()).where(ClientFeature.run_id == run_id))).scalar_one()
    rows = (await db.execute(
        select(ClientFeature, Client.full_name, column.label("label"))
        .join(Client, Client.id == ClientFeature.client_id)
        .where(ClientFeature.run_id == run_id)
        .order_by(text("md5(client_features.client_id::text)"))
        .limit(MAX_POINTS)
    )).all()
    points = [
        ScatterPoint(
            client_id=f.client_id, client_name=name, cluster_no=label, cluster_label=labels.get(label, f"Кластер {label}"),
            pca_x=f.pca_x or 0.0, pca_y=f.pca_y or 0.0, recency_days=float(f.recency_days),
            frequency=f.frequency, monetary=float(f.monetary),
        )
        for f, name, label in rows
    ]
    return PointsResponse(algorithm=algorithm, total=total, shown=len(points), points=points)


async def approve_run(db: AsyncSession, user: User, run_id: int, algorithm: str) -> ApproveResponse:
    """Шаг 3: утверждение модели пользователем (Human-in-the-loop) и фиксация среза T0."""
    run = await get_run(db, run_id, lock=True)
    if run.status != RUN_DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Утвердить можно только рассчитанный прогон (текущий статус: {run.status}).")
    model = model_of(run, algorithm)
    if model["cluster_count"] < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Модель вырождена: выделено менее двух кластеров.")

    now = datetime.now(timezone.utc)
    previous = await get_approved_run(db)
    old_codes: dict[int, str] = {}
    if previous is not None:
        old_codes = dict((await db.execute(
            select(Cluster.id, Cluster.segment_code).where(Cluster.run_id == previous.id))).all())
        previous.status = RUN_ARCHIVED
        await db.flush()

    run.status, run.algorithm, run.approved_at = RUN_APPROVED, algorithm, now
    no_to_id: dict[int, int] = {}
    code_to_id: dict[str, int] = {}
    for profile in sorted(model["clusters"], key=lambda p: -p["client_count"]):
        z = profile.get("z_center") or [None, None, None]
        cluster = Cluster(
            run_id=run.id, cluster_no=profile["cluster_no"], segment_code=profile["segment_code"],
            cluster_label=profile["cluster_label"], description=profile["description"],
            silhouette_score=profile.get("silhouette"), r_center=profile["r_center"], f_center=profile["f_center"],
            m_center=profile["m_center"], z_recency=z[0], z_frequency=z[1], z_monetary=z[2],
            client_count=profile["client_count"],
        )
        db.add(cluster)
        await db.flush()
        no_to_id[cluster.cluster_no] = cluster.id
        code_to_id.setdefault(cluster.segment_code, cluster.id)

    column = LABEL_COLUMNS[algorithm]
    assignments = (await db.execute(
        select(ClientFeature.client_id, column).where(ClientFeature.run_id == run.id))).all()
    pairs = [(cid, no_to_id[label]) for cid, label in assignments if label in no_to_id]

    await db.execute(delete(ClientClusterMapping))
    if pairs:
        await db.execute(insert(ClientClusterMapping), [
            {"client_id": cid, "cluster_id": cl, "updated_at": now} for cid, cl in pairs])

    snapshot = SegmentationSnapshot(run_id=run.id, kind="T0", reference_date=run.reference_date, created_by_user_id=user.id)
    db.add(snapshot)
    await db.flush()
    if pairs:
        await db.execute(insert(ClientClusterHistory), [
            {"snapshot_id": snapshot.id, "client_id": cid, "cluster_id": cl} for cid, cl in pairs])

    # Перепривязка действующих правил лояльности к сегментам новой модели по коду сегмента
    relinked = 0
    if old_codes:
        rules = (await db.execute(select(LoyaltyRule).where(LoyaltyRule.cluster_id.in_(old_codes)))).scalars().all()
        for rule in rules:
            new_id = code_to_id.get(old_codes[rule.cluster_id])
            if new_id is not None:
                rule.cluster_id = new_id
                relinked += 1
            else:
                rule.is_active = False
    await db.commit()
    await audit("Утверждение модели сегментации", user=user, object_type="прогон", object_id=run.id,
                details={"algorithm": algorithm, "clusters": len(no_to_id), "clients": len(pairs), "relinked_rules": relinked})
    return ApproveResponse(run_id=run.id, algorithm=algorithm, clusters_count=len(no_to_id), assigned_clients=len(pairs),
                           relinked_rules=relinked, snapshot_id=snapshot.id, approved_at=now)


async def cluster_briefs(db: AsyncSession, run_id: int) -> list[ClusterBrief]:
    """Сегменты утвержденной модели с актуальной численностью по текущему распределению клиентов."""
    counts = dict((await db.execute(
        select(ClientClusterMapping.cluster_id, func.count()).group_by(ClientClusterMapping.cluster_id))).all())
    clusters = (await db.execute(select(Cluster).where(Cluster.run_id == run_id))).scalars().all()
    total = sum(counts.get(c.id, 0) for c in clusters) or 1
    briefs = [
        ClusterBrief(
            id=c.id, cluster_no=c.cluster_no, segment_code=c.segment_code, cluster_label=c.cluster_label,
            description=c.description, silhouette_score=float(c.silhouette_score) if c.silhouette_score is not None else None,
            r_center=float(c.r_center), f_center=float(c.f_center), m_center=float(c.m_center),
            client_count=counts.get(c.id, 0), size_percent=round(counts.get(c.id, 0) / total * 100, 2),
        )
        for c in clusters
    ]
    return sorted(briefs, key=lambda b: (-TIER.get(b.segment_code, 0), -b.client_count))


async def current_segmentation(db: AsyncSession) -> CurrentSegmentation:
    total_clients = (await db.execute(select(func.count(Client.id)))).scalar_one()
    latest = (await db.execute(
        select(SegmentationRun).where(SegmentationRun.status != RUN_APPROVED)
        .order_by(SegmentationRun.id.desc()).limit(1))).scalar_one_or_none()
    latest_info = run_info(latest, await _username(db, latest.created_by_user_id)) if latest else None
    run = await get_approved_run(db)
    if run is None:
        return CurrentSegmentation(is_initialized=False, total_clients=total_clients, latest_run=latest_info)
    model = model_of(run, run.algorithm)
    briefs = await cluster_briefs(db, run.id)
    return CurrentSegmentation(
        is_initialized=True,
        run=run_info(run, await _username(db, run.created_by_user_id)),
        silhouette_score=model["silhouette_score"],
        davies_bouldin_score=model["davies_bouldin_score"],
        clusters=briefs,
        total_clients=total_clients,
        assigned_clients=sum(b.client_count for b in briefs),
        latest_run=latest_info if latest and latest.id > run.id else None,
    )


async def list_runs(db: AsyncSession, limit: int = 20) -> list[RunInfo]:
    rows = (await db.execute(
        select(SegmentationRun, User.username).outerjoin(User, User.id == SegmentationRun.created_by_user_id)
        .order_by(SegmentationRun.id.desc()).limit(limit))).all()
    return [run_info(run, username) for run, username in rows]
