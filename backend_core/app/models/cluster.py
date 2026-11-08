from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

RUN_DRAFT = "черновик"
RUN_RUNNING = "расчет"
RUN_DONE = "рассчитан"
RUN_FAILED = "ошибка"
RUN_APPROVED = "утвержден"
RUN_ARCHIVED = "архивный"


class SegmentationRun(Base):
    __tablename__ = "segmentation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default=RUN_DRAFT)
    days_period: Mapped[int] = mapped_column(Integer)
    reference_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_k: Mapped[int | None] = mapped_column(SmallInteger)
    algorithm: Mapped[str | None] = mapped_column(String(16))
    scaler_params: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    xai: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientFeature(Base):
    __tablename__ = "client_features"

    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("segmentation_runs.id", ondelete="CASCADE"), primary_key=True)
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    recency_days: Mapped[Decimal] = mapped_column(Numeric(8, 1))
    frequency: Mapped[int] = mapped_column(Integer)
    monetary: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    pca_x: Mapped[float | None] = mapped_column(Float)
    pca_y: Mapped[float | None] = mapped_column(Float)
    label_kmeans: Mapped[int | None] = mapped_column(SmallInteger)
    label_agglomerative: Mapped[int | None] = mapped_column(SmallInteger)
    label_dbscan: Mapped[int | None] = mapped_column(SmallInteger)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("segmentation_runs.id", ondelete="CASCADE"))
    cluster_no: Mapped[int] = mapped_column(SmallInteger)
    segment_code: Mapped[str] = mapped_column(String(16))
    cluster_label: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    silhouette_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    r_center: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    f_center: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    m_center: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    z_recency: Mapped[float | None] = mapped_column(Float)
    z_frequency: Mapped[float | None] = mapped_column(Float)
    z_monetary: Mapped[float | None] = mapped_column(Float)
    client_count: Mapped[int] = mapped_column(Integer)


class SegmentationSnapshot(Base):
    __tablename__ = "segmentation_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("segmentation_runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(2))
    reference_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())


class ClientClusterHistory(Base):
    __tablename__ = "client_cluster_history"

    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("segmentation_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clusters.id", ondelete="CASCADE"))


class ClientClusterMapping(Base):
    __tablename__ = "client_cluster_mapping"

    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clusters.id", ondelete="CASCADE"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())
