from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import ROLE_MARKETER, User
from app.schemas.segmentation import (
    AlgorithmId,
    ApproveRequest,
    ApproveResponse,
    BenchmarkStartRequest,
    CurrentSegmentation,
    DrillDownResponse,
    MigrationDashboard,
    PointsResponse,
    RunCreateRequest,
    RunDetail,
    RunInfo,
    SnapshotInfo,
    SnapshotResponse,
)
from app.services import migration as migration_service
from app.services import segmentation as seg
from app.services.audit import audit
from app.services.auth import require_roles
from app.services.exports import file_response, slug

router = APIRouter(prefix="/segmentation", tags=["Сегментация и мониторинг миграции"])
marketer = require_roles(ROLE_MARKETER)
FileFormat = Literal["csv", "xlsx"]


@router.post("/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED,
             summary="Сформировать матрицу признаков RFM за период (новый прогон)")
async def create_run(payload: RunCreateRequest, db: AsyncSession = Depends(get_db), user: User = Depends(marketer)):
    return await seg.create_run(db, user, payload.days_period)


@router.get("/runs", response_model=list[RunInfo], summary="Реестр прогонов (версий) моделей")
async def list_runs(db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    return await seg.list_runs(db)


@router.get("/runs/{run_id}", response_model=RunDetail, summary="Статус и результаты прогона")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    return await seg.run_detail(db, await seg.get_run(db, run_id))


@router.post("/runs/{run_id}/benchmark", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED,
             summary="Запустить фоновое сравнение трех моделей кластеризации")
async def start_benchmark(run_id: int, payload: BenchmarkStartRequest, db: AsyncSession = Depends(get_db),
                          user: User = Depends(marketer)):
    return await seg.start_benchmark(db, user, run_id, payload.target_k)


@router.get("/runs/{run_id}/points", response_model=PointsResponse, summary="Точки двумерной проекции PCA для модели")
async def get_points(run_id: int, algorithm: AlgorithmId = Query("kmeans"), db: AsyncSession = Depends(get_db),
                     _: User = Depends(marketer)):
    return await seg.get_points(db, run_id, algorithm)


@router.post("/runs/{run_id}/approve", response_model=ApproveResponse, summary="Утвердить модель (срез T0)")
async def approve(run_id: int, payload: ApproveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(marketer)):
    return await seg.approve_run(db, user, run_id, payload.algorithm)


@router.get("/current", response_model=CurrentSegmentation, summary="Утвержденная модель и ее сегменты")
async def current(db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    return await seg.current_segmentation(db)


@router.get("/snapshots", response_model=list[SnapshotInfo], summary="Срезы утвержденной модели")
async def snapshots(db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    run = await seg.get_approved_run(db)
    return await migration_service.list_snapshots(db, run.id) if run else []


@router.post("/snapshots", response_model=SnapshotResponse, summary="Зафиксировать срез T1 по центроидам модели")
async def create_snapshot(db: AsyncSession = Depends(get_db), user: User = Depends(marketer)):
    return await migration_service.create_snapshot(db, user)


@router.get("/migration", response_model=MigrationDashboard, summary="Матрица переходов клиентов между сегментами")
async def migration(from_snapshot: int | None = None, to_snapshot: int | None = None,
                    db: AsyncSession = Depends(get_db), _: User = Depends(marketer)):
    return await migration_service.migration_dashboard(db, from_snapshot, to_snapshot)


@router.get("/migration/clients", response_model=DrillDownResponse, summary="Клиенты ячейки матрицы переходов")
async def migration_clients(from_cluster: int, to_cluster: int, from_snapshot: int | None = None,
                            to_snapshot: int | None = None, db: AsyncSession = Depends(get_db),
                            _: User = Depends(marketer)):
    return await migration_service.drilldown(db, from_cluster, to_cluster, from_snapshot, to_snapshot)


@router.get("/migration/clients/export", summary="Выгрузка клиентов ячейки матрицы (CSV или Excel)")
async def migration_clients_export(request: Request, from_cluster: int, to_cluster: int,
                                   from_snapshot: int | None = None, to_snapshot: int | None = None,
                                   format: FileFormat = "csv", db: AsyncSession = Depends(get_db),
                                   user: User = Depends(marketer)) -> Response:
    headers, rows, name = await migration_service.drilldown_export_rows(db, from_cluster, to_cluster, from_snapshot, to_snapshot)
    await audit("Выгрузка данных", user=user, object_type="переход", request=request,
                details={"type": "детализация миграции", "rows": len(rows), "format": format})
    return file_response(headers, rows, f"migration_{slug(name)}", format)


@router.get("/migration/export", summary="Выгрузка отчета о миграции клиентов (CSV или Excel)")
async def migration_export(request: Request, from_snapshot: int | None = None, to_snapshot: int | None = None,
                           format: FileFormat = "csv", db: AsyncSession = Depends(get_db),
                           user: User = Depends(marketer)) -> Response:
    headers, rows = await migration_service.migration_export_rows(db, from_snapshot, to_snapshot)
    await audit("Выгрузка данных", user=user, object_type="отчет", request=request,
                details={"type": "отчет о миграции", "rows": len(rows), "format": format})
    return file_response(headers, rows, "customer_migration_report", format)


@router.get("/export", summary="Список рассылки по сегменту с предложениями лояльности (CSV или Excel)")
async def mailing_export(request: Request, cluster_id: int | None = None, format: FileFormat = "csv",
                         db: AsyncSession = Depends(get_db), user: User = Depends(marketer)) -> Response:
    headers, rows, label = await migration_service.mailing_export_rows(db, cluster_id)
    await audit("Выгрузка данных", user=user, object_type="сегмент", object_id=cluster_id, request=request,
                details={"type": "список рассылки", "rows": len(rows), "format": format})
    return file_response(headers, rows, f"mailing_segment_{slug(label or 'all')}", format)
