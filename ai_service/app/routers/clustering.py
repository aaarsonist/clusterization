from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.schemas.clustering import (
    AssignRequest,
    AssignResponse,
    BenchmarkRequest,
    BenchmarkResponse,
)
from app.services.clustering import assign_to_centroids, run_benchmark

router = APIRouter(prefix="/clusterize", tags=["Кластерный анализ"])


@router.post(
    "/benchmark",
    response_model=BenchmarkResponse,
    summary="Сравнить три модели кластеризации",
    description=(
        "Принимает обезличенную матрицу RFM, выполняет логарифмирование и стандартизацию признаков, "
        "обучает K-Means++, иерархическую модель Уорда и DBSCAN, рассчитывает метрики качества, "
        "проекцию PCA, профили сегментов и данные для объяснения результатов."
    ),
)
async def benchmark(request: BenchmarkRequest) -> BenchmarkResponse:
    if request.target_k is not None and request.target_k >= len(request.vectors):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Число кластеров должно быть меньше числа клиентов.")
    try:
        return await run_in_threadpool(run_benchmark, request.vectors, request.target_k)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Некорректные входные данные: {exc}") from exc


@router.post(
    "/assign",
    response_model=AssignResponse,
    summary="Отнести клиентов к центроидам утверждённой модели",
    description="Классифицирует новый срез признаков по центроидам базовой модели T0 в её пространстве признаков.",
)
async def assign(request: AssignRequest) -> AssignResponse:
    return await run_in_threadpool(
        assign_to_centroids, request.vectors, request.scaler.mean, request.scaler.scale, request.centroids
    )
