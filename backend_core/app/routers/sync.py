import csv
import io
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_phone, phone_digits, phone_hash
from app.database import get_db
from app.models.client import Client
from app.models.cluster import (
    ClientClusterHistory,
    ClientClusterMapping,
    ClientFeature,
    Cluster,
    SegmentationRun,
    SegmentationSnapshot,
)
from app.models.loyalty import LoyaltyRule, LoyaltyRuleCustomClient
from app.models.transaction import STATUS_CANCELLED, STATUS_CONFIRMED, Transaction
from app.models.user import ROLE_ADMIN, ROLE_MARKETER, User
from app.schemas.common import StatusMessage
from app.schemas.system import (
    CsvImportResult,
    MonthSimulationResult,
    PosSyncResult,
    SyncStatus,
)
from app.services.audit import audit
from app.services.auth import require_roles
from app.services.clients import new_client
from app.services.migration import create_snapshot
from app.services.segmentation import get_approved_run

router = APIRouter(prefix="/sync", tags=["Загрузка транзакционных данных"])
staff = require_roles(ROLE_MARKETER, ROLE_ADMIN)
_last_sync: datetime | None = None
MAX_FILE_BYTES = 10 * 1024 * 1024

COLUMNS = {
    "phone": {"client_phone", "phone", "телефон", "номер телефона", "номер_телефона"},
    "code": {"client_code", "external_code", "code", "код", "код клиента", "код_клиента"},
    "date": {"transaction_date", "date", "datetime", "дата", "дата чека", "дата_чека"},
    "amount": {"amount", "total_amount", "сумма", "сумма чека", "сумма_чека", "итого"},
    "discount": {"discount", "discount_amount", "скидка"},
    "status": {"status", "статус"},
    "name": {"full_name", "фио", "клиент"},
    "email": {"email", "e-mail", "почта"},
}
DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y")


def parse_datetime_flexible(value: str) -> datetime:
    """Разбор даты в форматах, принятых в кассовых системах и 1С."""
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"неизвестный формат даты «{value}»")


def parse_amount(value: str) -> Decimal:
    return Decimal(value.replace(" ", "").replace("\u00a0", "").replace(",", "."))


@router.get("/status", response_model=SyncStatus, summary="Состояние источника транзакционных данных")
async def sync_status(db: AsyncSession = Depends(get_db), _: User = Depends(staff)) -> SyncStatus:
    total_tx = (await db.execute(select(func.count(Transaction.id)))).scalar_one()
    total_clients = (await db.execute(select(func.count(Client.id)))).scalar_one()
    last_tx = (await db.execute(select(func.max(Transaction.transaction_date)))).scalar_one()
    return SyncStatus(total_transactions=total_tx, total_clients=total_clients, last_transaction_date=last_tx,
                      last_sync_at=_last_sync)


@router.post("/pos-sync", response_model=PosSyncResult, summary="Эмуляция регламентного обмена с кассами (закрытие смены)")
async def pos_sync(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(staff)) -> PosSyncResult:
    global _last_sync
    client_ids = list((await db.execute(select(Client.id))).scalars())
    if not client_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В базе данных нет клиентов.")
    now = datetime.now(timezone.utc)
    count = random.randint(40, 80)
    for _ in range(count):
        amount = Decimal(str(round(random.uniform(20, 350), 2)))
        discount = Decimal(str(round(float(amount) * random.uniform(0, 0.15), 2))) if random.random() > 0.3 else Decimal("0")
        db.add(Transaction(client_id=random.choice(client_ids),
                           transaction_date=now - timedelta(seconds=random.randint(300, 7 * 86400)),
                           total_amount=amount, discount_amount=discount,
                           status=STATUS_CANCELLED if random.random() < 0.03 else STATUS_CONFIRMED))
    await db.commit()
    _last_sync = now
    total = (await db.execute(select(func.count(Transaction.id)))).scalar_one()
    await audit("Синхронизация с кассами", user=user, request=request, details={"new_transactions": count})
    return PosSyncResult(new_transactions=count, total_transactions=total, synced_at=now)


@router.get("/template-csv", summary="Шаблон файла выгрузки чеков")
async def template_csv(_: User = Depends(staff)) -> Response:
    body = ("client_phone;full_name;transaction_date;amount;discount_amount;status\n"
            "+375291112233;Иванов Иван Иванович;2026-01-25 14:30:00;124,50;10,00;проведен\n"
            "+375292223344;Петрова Анна Сергеевна;2026-01-25 16:15:00;45,80;0;проведен\n"
            "+375333334455;;2026-01-26 11:05:00;289,00;25,00;отменен\n")
    return Response(content=body.encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="pos_transactions_template.csv"'})


@router.post("/upload-csv", response_model=CsvImportResult, summary="Пакетный импорт чеков из CSV-файла")
async def upload_csv(request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                     user: User = Depends(staff)) -> CsvImportResult:
    """Импорт выполняется в одной транзакции: корректные строки сохраняются вместе, ошибочные пропускаются."""
    global _last_sync
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Поддерживаются только файлы с расширением .csv.")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Загруженный файл пуст.")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Размер файла превышает 10 МБ.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1251", errors="replace")
    delimiter = ";" if content[:2048].count(";") >= content[:2048].count(",") else ","
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader, [])]
    idx = {key: next((i for i, h in enumerate(header) if h in names), -1) for key, names in COLUMNS.items()}
    if idx["date"] < 0 or idx["amount"] < 0 or (idx["phone"] < 0 and idx["code"] < 0):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Не найдены обязательные колонки: телефон или код клиента, дата чека, сумма чека.")

    codes = dict((await db.execute(select(Client.external_code, Client.id))).all())
    phones = dict((await db.execute(select(Client.phone_hash, Client.id))).all())
    cell = lambda row, key: row[idx[key]].strip() if 0 <= idx[key] < len(row) else ""  # noqa: E731
    processed = added = created = 0
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        processed += 1
        try:
            code, e164 = cell(row, "code"), normalize_phone(cell(row, "phone"))
            client_id = codes.get(code) if code else None
            if client_id is None and e164:
                client_id = phones.get(phone_hash(e164))
            if client_id is None:
                name = cell(row, "name")
                if not (name and e164):
                    raise ValueError(f"клиент «{code or cell(row, 'phone')}» не найден, а ФИО или телефон для создания анкеты не указаны")
                client = new_client(code or f"IMP-{phone_digits(e164)[-9:]}", name, e164, cell(row, "email"))
                db.add(client)
                await db.flush()
                client_id = phones[client.phone_hash] = codes[client.external_code] = client.id
                created += 1
            amount = parse_amount(cell(row, "amount"))
            if amount <= 0:
                raise ValueError("сумма чека должна быть больше нуля")
            discount = parse_amount(cell(row, "discount")) if cell(row, "discount") else Decimal("0")
            if not Decimal("0") <= discount <= amount:
                raise ValueError("скидка должна быть в пределах от 0 до суммы чека")
            tx_status = cell(row, "status").lower() or STATUS_CONFIRMED
            if tx_status not in (STATUS_CONFIRMED, STATUS_CANCELLED):
                raise ValueError(f"недопустимый статус чека «{tx_status}»")
            db.add(Transaction(client_id=client_id, transaction_date=parse_datetime_flexible(cell(row, "date")),
                               total_amount=amount, discount_amount=discount, status=tx_status))
            added += 1
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"Строка {line}: {exc}.")
    await db.commit()
    _last_sync = datetime.now(timezone.utc)
    await audit("Импорт чеков из CSV", user=user, request=request,
                details={"file": file.filename, "rows": processed, "added": added, "clients_created": created, "errors": len(errors)})
    return CsvImportResult(rows_processed=processed, transactions_added=added, clients_created=created,
                           errors=errors[:20], synced_at=_last_sync)


@router.post("/demo/reset-zero-state", response_model=StatusMessage, summary="Сбросить модели, срезы и правила (демонстрация)")
async def reset_zero_state(request: Request, db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles(ROLE_ADMIN))) -> StatusMessage:
    for model in (LoyaltyRuleCustomClient, LoyaltyRule, ClientClusterHistory, SegmentationSnapshot, ClientClusterMapping,
                  Cluster, ClientFeature, SegmentationRun):
        await db.execute(delete(model))
    await db.commit()
    await audit("Сброс аналитических данных", user=user, request=request)
    return StatusMessage(message="Модели сегментации, срезы и правила лояльности удалены; клиенты и чеки сохранены.")


@router.post("/demo/simulate-month", response_model=MonthSimulationResult, summary="Смоделировать прошедший месяц и зафиксировать срез T1")
async def simulate_month(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(staff)) -> MonthSimulationResult:
    """Эмуляция течения времени: история сдвигается на 30 дней назад, за прошедший месяц генерируются покупки
    с поведенческим дрейфом сегментов, после чего фиксируется срез T1."""
    if await get_approved_run(db) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сначала утвердите модель сегментации (срез T0).")
    shift = timedelta(days=30)
    for table, column in (("transactions", "transaction_date"), ("clients", "created_at"),
                          ("segmentation_snapshots", "reference_date"), ("segmentation_runs", "reference_date")):
        await db.execute(text(f"UPDATE {table} SET {column} = {column} - make_interval(days => 30)"))
    segments = (await db.execute(select(ClientClusterMapping.client_id, Cluster.segment_code)
                                 .join(Cluster, Cluster.id == ClientClusterMapping.cluster_id))).all()
    behaviour = {"vip": (0.82, (1, 3), (150, 480)), "newbie": (0.40, (2, 4), (45, 190)), "regular": (0.55, (1, 2), (35, 140)),
                 "bargain": (0.55, (1, 2), (25, 90)), "churn": (0.10, (1, 1), (40, 120)), "noise": (0.30, (1, 2), (30, 200))}
    now = datetime.now(timezone.utc)
    count = 0
    for client_id, code in segments:
        share, visits, amounts = behaviour[code]
        if random.random() >= share:
            continue
        for _ in range(random.randint(*visits)):
            amount = round(random.uniform(*amounts), 2)
            db.add(Transaction(client_id=client_id, transaction_date=now - shift + timedelta(seconds=random.randint(3600, 29 * 86400)),
                               total_amount=Decimal(str(amount)),
                               discount_amount=Decimal(str(round(amount * random.uniform(0, 0.12), 2)))))
            count += 1
    await db.commit()
    result = await create_snapshot(db, user)
    await audit("Моделирование месяца", user=user, request=request, details={"new_transactions": count})
    return MonthSimulationResult(new_transactions=count, snapshot_id=result.snapshot_id,
                                 tracked_clients=result.tracked_clients, changed_clients=result.changed_clients)
