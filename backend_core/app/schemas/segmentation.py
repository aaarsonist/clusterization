from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ClusterBrief

AlgorithmId = Literal["kmeans", "agglomerative", "dbscan"]


class RunCreateRequest(BaseModel):
    days_period: int = Field(365, ge=30, le=730, description="Период анализа транзакций, дней")


class BenchmarkStartRequest(BaseModel):
    target_k: int | None = Field(None, ge=2, le=8, description="Число кластеров или null для автоподбора")


class ApproveRequest(BaseModel):
    algorithm: AlgorithmId


class FeatureStats(BaseModel):
    clients: int
    active_clients: int
    recency_mean: float
    recency_median: float
    frequency_mean: float
    frequency_median: float
    monetary_mean: float
    monetary_median: float


class RunInfo(BaseModel):
    id: int
    status: str
    days_period: int
    reference_date: datetime
    target_k: int | None = None
    algorithm: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    approved_at: datetime | None = None
    created_by: str | None = None


class RunDetail(RunInfo):
    features: FeatureStats
    metrics: dict[str, Any] | None = None
    xai: dict[str, Any] | None = None


class ScatterPoint(BaseModel):
    client_id: int
    client_name: str
    cluster_no: int
    cluster_label: str
    pca_x: float
    pca_y: float
    recency_days: float
    frequency: int
    monetary: float


class PointsResponse(BaseModel):
    algorithm: str
    total: int
    shown: int
    points: list[ScatterPoint]


class CurrentSegmentation(BaseModel):
    is_initialized: bool
    run: RunInfo | None = None
    silhouette_score: float | None = None
    davies_bouldin_score: float | None = None
    clusters: list[ClusterBrief] = []
    total_clients: int = 0
    assigned_clients: int = 0
    latest_run: RunInfo | None = None


class SnapshotInfo(BaseModel):
    id: int
    kind: str
    reference_date: datetime
    created_at: datetime
    clients: int


class MigrationSummary(BaseModel):
    total_clients_compared: int
    retained: int
    total_migrated: int
    retention_rate: float
    churn_risk_count: int
    upgrade_count: int
    downgrade_count: int


class MatrixSegment(BaseModel):
    cluster_id: int
    cluster_label: str
    segment_code: str


class TransitionMatrix(BaseModel):
    segments: list[MatrixSegment]
    matrix: list[list[int]]
    total_from: list[int]
    total_to: list[int]


class MarketingAlert(BaseModel):
    id: str
    type: Literal["critical", "success", "warning", "info"]
    title: str
    message: str
    action_label: str
    impact: str
    target_cluster_id: int | None = None


class MigrationClient(BaseModel):
    client_id: int
    external_code: str
    full_name: str
    phone: str
    old_cluster_id: int
    old_segment: str
    new_cluster_id: int
    new_segment: str
    direction: Literal["positive", "negative", "neutral"]


class MigrationDashboard(BaseModel):
    state: Literal["ready", "need_baseline", "need_second_snapshot"]
    message: str
    snapshots: list[SnapshotInfo] = []
    from_snapshot: SnapshotInfo | None = None
    to_snapshot: SnapshotInfo | None = None
    summary: MigrationSummary | None = None
    matrix: TransitionMatrix | None = None
    alerts: list[MarketingAlert] = []
    clients_sample: list[MigrationClient] = []


class DrillDownClient(BaseModel):
    client_id: int
    external_code: str
    full_name: str
    phone: str
    recency_days: float
    frequency: int
    monetary: Decimal
    financial_impact: Decimal
    impact_type: Literal["loss", "gain", "neutral"]


class DrillDownResponse(BaseModel):
    from_cluster: MatrixSegment
    to_cluster: MatrixSegment
    total_clients: int
    total_turnover: Decimal
    total_financial_impact: Decimal
    clients: list[DrillDownClient]


class ApproveResponse(BaseModel):
    run_id: int
    algorithm: str
    clusters_count: int
    assigned_clients: int
    relinked_rules: int
    snapshot_id: int
    approved_at: datetime


class SnapshotResponse(BaseModel):
    snapshot_id: int
    run_id: int
    tracked_clients: int
    changed_clients: int
    reference_date: datetime
