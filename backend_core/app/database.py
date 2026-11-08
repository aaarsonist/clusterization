import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _ssl_context() -> ssl.SSLContext | bool:
    """Подключение к PostgreSQL только по TLS с проверкой сертификата сервера собственным УЦ."""
    if not settings.POSTGRES_SSL:
        return False
    context = ssl.create_default_context(cafile=settings.TLS_CA_FILE)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


engine = create_async_engine(
    settings.database_url(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"ssl": _ssl_context()},
)

async_session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: сессия БД с откатом незавершенной транзакции при ошибке."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
