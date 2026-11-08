import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.core.logging_setup import RequestContextMiddleware, configure_logging
from app.database import engine
from app.routers import (
    audit,
    auth,
    backups,
    clients,
    loyalty,
    segmentation,
    summary,
    sync,
    users,
)
from app.schemas.common import HealthResponse
from app.services.ai_gateway import ai_gateway
from app.services.backup import scheduler_loop
from app.services.segmentation import fail_interrupted_runs

configure_logging("backend_core")
logger = logging.getLogger("backend_core")

VALIDATION_MESSAGES = {
    "missing": "обязательное поле",
    "string_too_short": "слишком короткое значение (минимум {min_length} симв.)",
    "string_too_long": "слишком длинное значение (максимум {max_length} симв.)",
    "string_pattern_mismatch": "значение содержит недопустимые символы",
    "greater_than": "значение должно быть больше {gt}",
    "greater_than_equal": "значение должно быть не меньше {ge}",
    "less_than_equal": "значение должно быть не больше {le}",
    "int_parsing": "ожидается целое число",
    "decimal_parsing": "ожидается число",
    "float_parsing": "ожидается число",
    "literal_error": "недопустимое значение",
    "decimal_max_places": "не более {decimal_places} знаков после запятой",
    "json_invalid": "некорректный формат JSON",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск сервера бизнес-логики", extra={"version": settings.VERSION})
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await fail_interrupted_runs()
    scheduler = asyncio.create_task(scheduler_loop())
    yield
    scheduler.cancel()
    await engine.dispose()
    logger.info("Сервер бизнес-логики остановлен")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="REST API программного средства сегментации клиентов методами кластерного анализа в целях персонализации лояльности.",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Перевод ошибок валидации входных данных на русский язык."""
    errors = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        template = VALIDATION_MESSAGES.get(err.get("type", ""))
        if template:
            try:
                message = template.format(**(err.get("ctx") or {}))
            except (KeyError, IndexError):
                message = template
        else:
            message = str(err.get("msg", "некорректное значение")).removeprefix("Value error, ")
        errors.append({"loc": err.get("loc"), "msg": message, "field": field})
    return JSONResponse(status_code=422, content={"detail": errors})


for module in (auth, users, clients, summary, segmentation, loyalty, sync, backups, audit):
    app.include_router(module.router, prefix=settings.API_V1_STR)


@app.get("/health", response_model=HealthResponse, tags=["Системные"], summary="Проверка состояния сервера, СУБД и ИИ-сервиса")
async def health() -> HealthResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"ошибка: {exc.__class__.__name__}"
    ai_status = await ai_gateway.health()
    return HealthResponse(
        status="ok" if db_status == "ok" and ai_status == "ok" else "degraded",
        service="backend_core", version=settings.VERSION, database=db_status, ai_service=ai_status,
        timestamp=datetime.now(timezone.utc),
    )
