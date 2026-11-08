import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import scipy
import sklearn
from fastapi import FastAPI
from pydantic import BaseModel

from app.config import settings
from app.logging_setup import RequestContextMiddleware, configure_logging
from app.routers.clustering import router as clustering_router

configure_logging("ai_service")
logger = logging.getLogger("ai_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Запуск интеллектуального микросервиса",
        extra={"sklearn": sklearn.__version__, "scipy": scipy.__version__, "pandas": pd.__version__, "numpy": np.__version__},
    )
    yield
    logger.info("Остановка интеллектуального микросервиса")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Изолированный микросервис сегментации клиентов методами кластерного анализа (K-Means++, Уорд, DBSCAN, PCA).",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.include_router(clustering_router, prefix=settings.API_V1_STR)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    sklearn_version: str
    numpy_version: str
    timestamp: datetime


@app.get("/health", response_model=HealthResponse, tags=["Системные"], summary="Проверка готовности сервиса")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="ai_service",
        version=settings.VERSION,
        sklearn_version=sklearn.__version__,
        numpy_version=np.__version__,
        timestamp=datetime.now(timezone.utc),
    )
