from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SyncStatus(BaseModel):
    source_name: str = "Кассовый контур (POS)"
    status: str = "в сети"
    total_transactions: int
    total_clients: int
    last_transaction_date: datetime | None = None
    last_sync_at: datetime | None = None


class PosSyncResult(BaseModel):
    new_transactions: int
    total_transactions: int
    synced_at: datetime


class CsvImportResult(BaseModel):
    rows_processed: int
    transactions_added: int
    clients_created: int
    errors: list[str] = []
    synced_at: datetime


class MonthSimulationResult(BaseModel):
    new_transactions: int
    snapshot_id: int
    tracked_clients: int
    changed_clients: int


class AuditItem(BaseModel):
    id: int
    event_time: datetime
    username: str | None
    action: str
    object_type: str | None
    object_id: str | None
    success: bool
    ip_address: str | None
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditItem]
    total: int


class BackupItem(BaseModel):
    file_name: str
    created_at: datetime
    kind: str
    size_bytes: int
    sha256: str
    created_by: str | None = None


class BackupSettingsIn(BaseModel):
    enabled: bool
    run_hour: int = Field(..., ge=0, le=23)
    retention_count: int = Field(..., ge=1, le=90)


class BackupSettingsOut(BackupSettingsIn):
    updated_at: datetime


class BackupOverview(BaseModel):
    settings: BackupSettingsOut
    backups: list[BackupItem]
    free_space_bytes: int
