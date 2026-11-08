from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ClusterBrief(BaseModel):
    id: int
    cluster_no: int
    segment_code: str
    cluster_label: str
    description: str = ""
    silhouette_score: float | None = None
    r_center: float
    f_center: float
    m_center: float
    client_count: int
    size_percent: float


class StatusMessage(BaseModel):
    status: str = "success"
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    ai_service: str
    timestamp: datetime


class SummaryResponse(BaseModel):
    total_clients: int
    total_transactions: int
    cancelled_transactions: int
    total_revenue: Decimal
    total_discount: Decimal
    avg_check: Decimal
    active_loyalty_rules: int
    model_algorithm: str | None = None
    model_approved_at: datetime | None = None
    clusters: list[ClusterBrief] = []
