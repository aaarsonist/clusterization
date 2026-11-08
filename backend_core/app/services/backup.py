"""Резервное копирование БД: дамп pg_dump, шифрование AES-256-GCM, ротация, восстановление, расписание."""
import asyncio
import base64
import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select, text

from app.config import settings
from app.core.security import decrypt_bytes, encrypt_bytes
from app.database import async_session_maker, engine
from app.models.system import BackupSettings
from app.schemas.system import BackupItem

logger = logging.getLogger("backend_core.backup")

KIND_MANUAL = "ручная"
KIND_AUTO = "автоматическая"
KIND_SAFETY = "перед восстановлением"
MINSK = timezone(timedelta(hours=3))
_KEY = base64.b64decode(settings.BACKUP_ENCRYPTION_KEY)
_lock = asyncio.Lock()


def backup_dir() -> Path:
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pg_env() -> dict[str, str]:
    return {
        **os.environ,
        "PGHOST": settings.POSTGRES_SERVER, "PGPORT": str(settings.POSTGRES_PORT),
        "PGUSER": settings.POSTGRES_USER, "PGPASSWORD": settings.POSTGRES_PASSWORD,
        "PGDATABASE": settings.POSTGRES_DB,
        "PGSSLMODE": "verify-full" if settings.POSTGRES_SSL else "disable", "PGSSLROOTCERT": settings.TLS_CA_FILE,
    }


async def _run(*args: str, stdin: bytes | None = None) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_pg_env())
    out, err = await proc.communicate(stdin)
    if proc.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "replace").strip()[:1000])
    return out


def list_backups() -> list[BackupItem]:
    items = []
    for meta_path in backup_dir().glob("*.json"):
        try:
            items.append(BackupItem(**json.loads(meta_path.read_text(encoding="utf-8"))))
        except (ValueError, OSError):
            logger.warning("Поврежденный файл описания копии", extra={"file": meta_path.name})
    return sorted(items, key=lambda b: b.created_at, reverse=True)


def free_space() -> int:
    return shutil.disk_usage(backup_dir()).free


async def _database_size() -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT pg_database_size(current_database())"))).scalar_one())


async def _retention_count() -> int:
    async with async_session_maker() as db:
        row = (await db.execute(select(BackupSettings).where(BackupSettings.id == 1))).scalar_one_or_none()
        return row.retention_count if row else 14


def _rotate(keep: int) -> None:
    for item in list_backups()[keep:]:
        for suffix in ("", ".json"):
            path = backup_dir() / (item.file_name + suffix)
            path.unlink(missing_ok=True)


async def create_backup(kind: str, username: str | None) -> BackupItem:
    """Создание зашифрованной резервной копии с проверкой свободного места и ротацией."""
    async with _lock:
        if free_space() < 2 * await _database_size():
            raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "Недостаточно места на диске для резервной копии.")
        now = datetime.now(timezone.utc)
        suffix = {KIND_MANUAL: "manual", KIND_AUTO: "auto"}.get(kind, "safety")
        name = f"backup_{now.strftime('%Y%m%d_%H%M%S')}_{suffix}.dump.enc"
        dump = await _run("pg_dump", "--format=custom", "--no-owner", "--compress=6")
        blob = encrypt_bytes(dump, _KEY, name.encode("utf-8"))
        path = backup_dir() / name
        path.write_bytes(blob)
        item = BackupItem(file_name=name, created_at=now, kind=kind, size_bytes=len(blob),
                          sha256=hashlib.sha256(blob).hexdigest(), created_by=username)
        (backup_dir() / (name + ".json")).write_text(item.model_dump_json(indent=2), encoding="utf-8")
        _rotate(await _retention_count())
        logger.info("Создана резервная копия", extra={"file": name, "size": len(blob), "kind": kind})
        return item


async def restore_backup(file_name: str, username: str | None) -> BackupItem:
    """Восстановление БД из копии: проверка целостности, расшифровка, pg_restore в одной транзакции."""
    meta = next((b for b in list_backups() if b.file_name == file_name), None)
    path = backup_dir() / file_name
    if meta is None or not path.is_file() or path.parent != backup_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Резервная копия не найдена.")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != meta.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "Контрольная сумма копии не совпадает: файл поврежден.")
    try:
        dump = decrypt_bytes(blob, _KEY, file_name.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Не удалось расшифровать копию: неверный ключ или повреждение.") from exc

    await create_backup(KIND_SAFETY, username)
    async with _lock:
        # Завершение прочих сеансов СУБД, чтобы их блокировки не препятствовали пересозданию таблиц
        async with engine.connect() as conn:
            await conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"))
        await engine.dispose()
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
            tmp.write(dump)
            tmp_path = tmp.name
        try:
            await _run("pg_restore", "--clean", "--if-exists", "--no-owner", "--single-transaction",
                       "--dbname", settings.POSTGRES_DB, tmp_path)
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ошибка восстановления: {exc}") from exc
        finally:
            os.unlink(tmp_path)
            await engine.dispose()
    logger.info("База данных восстановлена из копии", extra={"file": file_name})
    return meta


async def scheduler_loop() -> None:
    """Ежеминутная проверка расписания: автоматическая копия раз в сутки в заданный час (время Минска)."""
    from app.services.audit import audit

    while True:
        try:
            async with async_session_maker() as db:
                cfg = (await db.execute(select(BackupSettings).where(BackupSettings.id == 1))).scalar_one_or_none()
            now = datetime.now(MINSK)
            if cfg and cfg.enabled and now.hour == cfg.run_hour:
                today = [b for b in list_backups() if b.kind == KIND_AUTO and b.created_at.astimezone(MINSK).date() == now.date()]
                if not today:
                    item = await create_backup(KIND_AUTO, "система")
                    await audit("Автоматическое резервное копирование", username="система", object_type="копия",
                                object_id=item.file_name, details={"size_bytes": item.size_bytes})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Сбой планировщика резервного копирования")
        await asyncio.sleep(60)
