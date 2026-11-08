"""Контракт интеллектуального микросервиса.

В сервис передаются только обезличенные числовые векторы (давность, частота,
сумма покупок). Идентификаторы и персональные данные клиентов остаются
на стороне сервера бизнес-логики: соответствие строк клиентам восстанавливается
по порядковому номеру вектора в массиве.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

AlgorithmId = Literal["kmeans", "agglomerative", "dbscan"]
SegmentCode = Literal["vip", "churn", "newbie", "bargain", "regular", "noise"]

RFMVector = Annotated[
    list[Annotated[float, Field(ge=0)]],
    Field(min_length=3, max_length=3, description="[давность, дней; частота, чеков; сумма, BYN]"),
]
ZVector = Annotated[list[float], Field(min_length=3, max_length=3)]


class BenchmarkRequest(BaseModel):
    vectors: list[RFMVector] = Field(..., min_length=4, description="Обезличенная матрица признаков RFM")
    target_k: int | None = Field(None, ge=2, le=8, description="Заданное число кластеров или null для автоподбора")


class ScalerParams(BaseModel):
    mean: ZVector = Field(..., description="Средние значения признаков [R, ln(1+F), ln(1+M)]")
    scale: ZVector = Field(..., description="Стандартные отклонения признаков")


class ClusterProfile(BaseModel):
    cluster_no: int = Field(..., description="Номер кластера в модели (-1 — шум DBSCAN)")
    segment_code: SegmentCode
    cluster_label: str
    description: str
    client_count: int
    size_percent: float
    silhouette: float | None = Field(None, description="Средний коэффициент силуэта объектов кластера")
    r_center: float = Field(..., description="Средняя давность покупки, дней")
    f_center: float = Field(..., description="Среднее число чеков за период")
    m_center: float = Field(..., description="Средняя сумма покупок за период, BYN")
    z_center: ZVector | None = Field(None, description="Центроид в стандартизованном пространстве признаков")


class ModelResult(BaseModel):
    algorithm_id: AlgorithmId
    name: str
    silhouette_score: float
    davies_bouldin_score: float
    cluster_count: int
    noise_percent: float
    score: float = Field(..., description="Интегральная оценка для выбора победителя")
    is_winner: bool = False
    business_suitability: str
    suitability_badge: str
    labels: list[int]
    clusters: list[ClusterProfile]


class Winner(BaseModel):
    algorithm_id: AlgorithmId
    model_name: str
    verdict: str
    justification: str
    recommendation: str
    low_quality: bool = Field(..., description="Признак неудовлетворительного качества (силуэт ниже порога)")
    quality_threshold: float


class ElbowPoint(BaseModel):
    k: int
    inertia: float
    silhouette: float


class KnnPoint(BaseModel):
    index: int
    distance: float


class Dendrogram(BaseModel):
    icoord: list[list[float]] = Field(default_factory=list)
    dcoord: list[list[float]] = Field(default_factory=list)
    color_list: list[str] = Field(default_factory=list)
    ivl: list[str] = Field(default_factory=list)
    cut_threshold: float


class XaiData(BaseModel):
    elbow_curve: list[ElbowPoint]
    optimal_k: int
    knn_distances: list[KnnPoint]
    selected_eps: float
    min_samples: int
    dendrogram: Dendrogram
    explained_variance_ratio: list[float]


class BenchmarkResponse(BaseModel):
    n_samples: int
    calculated_at: str
    duration_ms: int
    scaler: ScalerParams
    pca_coords: list[list[float]]
    models: list[ModelResult]
    winner: Winner
    xai: XaiData


class Centroid(BaseModel):
    cluster_no: int
    z_center: ZVector


class AssignRequest(BaseModel):
    vectors: list[RFMVector] = Field(..., min_length=1)
    scaler: ScalerParams
    centroids: list[Centroid] = Field(..., min_length=1)


class AssignResponse(BaseModel):
    labels: list[int]
    duration_ms: int
