"""Алгоритмическое ядро интеллектуального микросервиса.

Конвейер обработки:
1) пространство признаков X = [R, ln(1 + F), ln(1 + M)];
2) Z-стандартизация (StandardScaler), параметры которой возвращаются серверу
   и используются при последующей классификации среза T1;
3) сравнение трёх моделей: K-Means++ (перебор k = 2..8, метод локтя и силуэт),
   иерархическая кластеризация Уорда (дендрограмма), DBSCAN (график k-NN);
4) расчёт метрик качества (силуэт, индекс Дэвиса–Болдина), выбор победителя;
5) проекция PCA на плоскость для визуализации;
6) профилирование кластеров и присвоение бизнес-наименований.

Для больших выборок ресурсоёмкие этапы (силуэт, Уорд, DBSCAN) выполняются
на детерминированной подвыборке с последующим отнесением остальных объектов
к ближайшему центроиду (ядру), что сохраняет линейную сложность конвейера.
"""
import logging
import time
from datetime import datetime, timezone

import numpy as np
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import davies_bouldin_score, silhouette_samples, silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from app.schemas.clustering import (
    AssignResponse,
    BenchmarkResponse,
    Centroid,
    ClusterProfile,
    Dendrogram,
    ElbowPoint,
    KnnPoint,
    ModelResult,
    ScalerParams,
    Winner,
    XaiData,
)

logger = logging.getLogger("ai_service.clustering")

RANDOM_STATE = 42
K_MIN, K_MAX = 2, 8
OPTIMAL_K_RANGE = (3, 6)
SILHOUETTE_SAMPLE = 5000
ELBOW_SILHOUETTE_SAMPLE = 2000
WARD_SAMPLE = 3000
DBSCAN_SAMPLE = 10000
DBSCAN_MIN_SAMPLES = 5
DBSCAN_EPS_PERCENTILE = 85
DBSCAN_EPS_MIN = 0.2
QUALITY_THRESHOLD = 0.35
DB_WEIGHT = 0.15
NOISE_PENALTY = 0.4
NOISE_LIMIT_PERCENT = 15.0
DEGENERATE_PENALTY = 1.0

SEGMENT_LABELS = {
    "vip": "Лояльные лидеры",
    "churn": "Зона риска оттока",
    "newbie": "Перспективные новички",
    "bargain": "Экономные постоянные",
    "regular": "Постоянные клиенты",
    "noise": "Нетипичные клиенты (выбросы)",
}


def fmt(value: float, digits: int = 3) -> str:
    """Форматирование числа с десятичной запятой для текстов на русском языке."""
    return f"{value:.{digits}f}".replace(".", ",")


def build_features(raw: np.ndarray) -> np.ndarray:
    """Логарифмирование правосторонне асимметричных признаков частоты и суммы."""
    return np.column_stack([raw[:, 0], np.log1p(raw[:, 1]), np.log1p(raw[:, 2])])


def standardize(features: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
    safe_scale = np.where(scale > 1e-12, scale, 1.0)
    return (features - mean) / safe_scale


def sample_indices(n: int, limit: int) -> np.ndarray:
    """Детерминированная подвыборка индексов без возвращения."""
    if n <= limit:
        return np.arange(n)
    rng = np.random.default_rng(RANDOM_STATE)
    return np.sort(rng.choice(n, size=limit, replace=False))


def quality_metrics(z: np.ndarray, labels: np.ndarray) -> tuple[float, float, dict[int, float]]:
    """Силуэт (общий и по кластерам) и индекс Дэвиса–Болдина без учёта шума."""
    mask = labels != -1
    clusters = np.unique(labels[mask])
    if clusters.size < 2 or mask.sum() <= clusters.size:
        return 0.0, 0.0, {}
    z_valid, l_valid = z[mask], labels[mask]
    idx = sample_indices(len(z_valid), SILHOUETTE_SAMPLE)
    z_s, l_s = z_valid[idx], l_valid[idx]
    if np.unique(l_s).size < 2:
        return 0.0, 0.0, {}
    s = silhouette_samples(z_s, l_s)
    per_cluster = {int(c): float(s[l_s == c].mean()) for c in clusters if np.any(l_s == c)}
    db = float(davies_bouldin_score(z_valid, l_valid))
    return float(s.mean()), db, per_cluster


def nearest_centroid(z: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Номер ближайшего центроида по евклидову расстоянию для каждой строки."""
    d2 = ((z[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
    return d2.argmin(axis=1)


def run_kmeans(z: np.ndarray, target_k: int | None) -> tuple[np.ndarray, int, list[ElbowPoint]]:
    n = len(z)
    k_max = min(K_MAX, n - 1)
    elbow: list[ElbowPoint] = []
    models: dict[int, np.ndarray] = {}
    for k in range(K_MIN, k_max + 1):
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(z)
        sil = float(silhouette_score(z, labels, sample_size=min(n, ELBOW_SILHOUETTE_SAMPLE), random_state=RANDOM_STATE))
        elbow.append(ElbowPoint(k=k, inertia=round(float(km.inertia_), 2), silhouette=round(sil, 4)))
        models[k] = labels

    if target_k is not None and target_k in models:
        best_k = target_k
    else:
        candidates = [p for p in elbow if OPTIMAL_K_RANGE[0] <= p.k <= OPTIMAL_K_RANGE[1]] or elbow
        best_k = max(candidates, key=lambda p: p.silhouette).k
    return models[best_k], best_k, elbow


def run_ward(z: np.ndarray, k: int) -> tuple[np.ndarray, Dendrogram]:
    idx = sample_indices(len(z), WARD_SAMPLE)
    z_s = z[idx]
    link = linkage(z_s, method="ward")
    labels_s = fcluster(link, t=k, criterion="maxclust") - 1

    labels = np.empty(len(z), dtype=int)
    if len(idx) == len(z):
        labels[:] = labels_s
    else:
        uniq = np.unique(labels_s)
        centroids = np.vstack([z_s[labels_s == c].mean(axis=0) for c in uniq])
        labels[:] = uniq[nearest_centroid(z, centroids)]
        labels[idx] = labels_s

    # Горизонтальный срез дендрограммы между высотами объединений, дающий k кластеров
    m = len(link)
    if 2 <= k <= m:
        upper = link[m - k + 1, 2] if m - k + 1 < m else link[m - k, 2]
        cut = (link[m - k, 2] + upper) / 2
    else:
        cut = link[-1, 2] * 0.7
    tree = dendrogram(link, truncate_mode="lastp", p=16, no_plot=True)
    dendro = Dendrogram(
        icoord=tree["icoord"],
        dcoord=tree["dcoord"],
        color_list=tree["color_list"],
        ivl=tree["ivl"],
        cut_threshold=round(float(cut), 3),
    )
    return labels, dendro


def run_dbscan(z: np.ndarray) -> tuple[np.ndarray, float, list[KnnPoint]]:
    idx = sample_indices(len(z), DBSCAN_SAMPLE)
    z_s = z[idx]
    n_neighbors = min(DBSCAN_MIN_SAMPLES, len(z_s) - 1)
    distances, _ = NearestNeighbors(n_neighbors=n_neighbors).fit(z_s).kneighbors(z_s)
    k_dist = np.sort(distances[:, -1])
    eps = max(DBSCAN_EPS_MIN, float(np.percentile(k_dist, DBSCAN_EPS_PERCENTILE)))

    model = DBSCAN(eps=eps, min_samples=DBSCAN_MIN_SAMPLES).fit(z_s)
    labels_s = model.labels_

    labels = np.full(len(z), -1, dtype=int)
    labels[idx] = labels_s
    core = model.core_sample_indices_
    rest = np.setdiff1d(np.arange(len(z)), idx)
    if rest.size and core.size:
        # Объекты вне подвыборки относятся к кластеру ближайшей ядровой точки в радиусе eps
        nn = NearestNeighbors(n_neighbors=1).fit(z_s[core])
        dist, pos = nn.kneighbors(z[rest])
        inside = dist[:, 0] <= eps
        labels[rest[inside]] = labels_s[core[pos[inside, 0]]]

    points = np.linspace(0, len(k_dist) - 1, min(70, len(k_dist)), dtype=int)
    knn = [KnnPoint(index=int(i + 1), distance=round(float(k_dist[i]), 3)) for i in points]
    return labels, round(eps, 3), knn


def profile_clusters(raw: np.ndarray, z: np.ndarray, labels: np.ndarray) -> list[ClusterProfile]:
    """Расчёт профилей кластеров и присвоение бизнес-наименований по центроидам RFM."""
    total = len(raw)
    global_r, global_f, global_m = raw.mean(axis=0)
    stats = []
    for c in sorted(np.unique(labels)):
        mask = labels == c
        r, f, m = raw[mask].mean(axis=0)
        stats.append({
            "no": int(c), "count": int(mask.sum()), "r": float(r), "f": float(f), "m": float(m),
            "z": None if c == -1 else [round(float(v), 6) for v in z[mask].mean(axis=0)],
        })

    regular = [s for s in stats if s["no"] != -1]
    codes: dict[int, str] = {}
    if regular:
        vip = max(regular, key=lambda s: s["m"] * s["f"] / (s["r"] + 1))
        codes[vip["no"]] = "vip"
    # Зона риска оттока: все кластеры, средняя давность покупки которых не меньше 0,8 средней по базе
    for s in regular:
        if s["no"] not in codes and s["r"] >= 0.8 * global_r:
            codes[s["no"]] = "churn"
    rest = [s for s in regular if s["no"] not in codes]
    if rest:
        newbie = min(rest, key=lambda s: (s["f"], s["r"]))
        codes[newbie["no"]] = "newbie"
    for s in regular:
        if s["no"] not in codes:
            codes[s["no"]] = "bargain" if s["m"] < global_m and s["f"] >= 0.7 * global_f else "regular"

    used: dict[str, int] = {}
    profiles: list[ClusterProfile] = []
    for s in stats:
        code = "noise" if s["no"] == -1 else codes[s["no"]]
        used[code] = used.get(code, 0) + 1
        label = SEGMENT_LABELS[code] if used[code] == 1 else f"{SEGMENT_LABELS[code]} (группа {used[code]})"
        r, f, m = s["r"], s["f"], s["m"]
        descriptions = {
            "vip": f"Наиболее ценные клиенты: {fmt(f, 1)} чеков и {fmt(m, 0)} BYN покупок за период, последняя покупка {fmt(r, 0)} дн. назад.",
            "churn": f"Давно не покупали ({fmt(r, 0)} дн.), ранее совершили {fmt(f, 1)} покупок. Требуется реактивация.",
            "newbie": f"Недавно привлечённые клиенты: {fmt(f, 1)} покупок, последняя {fmt(r, 0)} дн. назад, сумма {fmt(m, 0)} BYN.",
            "bargain": f"Регулярные покупки ({fmt(f, 1)} чеков) при небольшой сумме ({fmt(m, 0)} BYN), чувствительны к скидкам.",
            "regular": f"Умеренная активность: {fmt(f, 1)} чеков, {fmt(m, 0)} BYN за период, давность {fmt(r, 0)} дн.",
            "noise": "Клиенты с нетипичным поведением, не вошедшие ни в одну плотную группу.",
        }
        profiles.append(ClusterProfile(
            cluster_no=s["no"],
            segment_code=code,
            cluster_label=label,
            description=descriptions[code],
            client_count=s["count"],
            size_percent=round(s["count"] / max(1, total) * 100.0, 2),
            r_center=round(r, 2),
            f_center=round(f, 2),
            m_center=round(m, 2),
            z_center=s["z"],
        ))
    return profiles


def score_model(algorithm_id: str, sil: float, db: float, k: int, noise: float) -> float:
    """Интегральная оценка: Score = S − 0,15·min(3; DB) − штрафы DBSCAN за шум и вырожденность."""
    score = sil - DB_WEIGHT * min(3.0, db)
    if algorithm_id == "dbscan":
        if noise > NOISE_LIMIT_PERCENT:
            score -= NOISE_PENALTY
        if k < 2:
            score -= DEGENERATE_PENALTY
    return round(score, 4)


def build_winner(best: ModelResult) -> Winner:
    sil, db = fmt(best.silhouette_score), fmt(best.davies_bouldin_score)
    texts = {
        "kmeans": (
            f"Модель K-Means++ показала наилучшее разделение клиентов (силуэт {sil}) без шумовых объектов.",
            f"Сформировано {best.cluster_count} компактных сегментов, индекс Дэвиса–Болдина {db}; распределена вся клиентская база.",
            "Рекомендуется утвердить модель как основу персонализированных правил лояльности.",
        ),
        "agglomerative": (
            f"Иерархическая кластеризация методом Уорда сформировала устойчивую структуру (силуэт {sil}).",
            f"Дерево объединений выделило {best.cluster_count} сегментов с минимальным приростом внутрикластерной дисперсии (индекс {db}).",
            "Подходит для многоуровневых программ лояльности со ступенчатыми привилегиями.",
        ),
        "dbscan": (
            f"DBSCAN выделил {best.cluster_count} плотных групп при силуэте {sil}.",
            f"Доля нетипичных клиентов составила {fmt(best.noise_percent, 1)} %, индекс Дэвиса–Болдина {db}.",
            "Рекомендуется для выявления клиентов с нетипичным покупательским поведением.",
        ),
    }
    verdict, justification, recommendation = texts[best.algorithm_id]
    low = best.silhouette_score < QUALITY_THRESHOLD
    if low:
        recommendation = (
            f"Качество разбиения ниже порога {fmt(QUALITY_THRESHOLD, 2)}: данные слабо разделимы. "
            "Рекомендуется изменить период анализа или число кластеров."
        )
    return Winner(
        algorithm_id=best.algorithm_id,
        model_name=best.name,
        verdict=verdict,
        justification=justification,
        recommendation=recommendation,
        low_quality=low,
        quality_threshold=QUALITY_THRESHOLD,
    )


def run_benchmark(vectors: list[list[float]], target_k: int | None = None) -> BenchmarkResponse:
    started = time.perf_counter()
    raw = np.asarray(vectors, dtype=float)
    features = build_features(raw)
    scaler = StandardScaler().fit(features)
    z = scaler.transform(features)
    n = len(z)

    km_labels, best_k, elbow = run_kmeans(z, target_k)
    ward_labels, dendro = run_ward(z, best_k)
    db_labels, eps, knn = run_dbscan(z)

    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    coords = pca.fit_transform(z)

    meta = {
        "kmeans": ("K-Means++", "Высокая", "Оптимально для программ лояльности"),
        "agglomerative": ("Иерархическая (метод Уорда)", "Высокая", "Чёткая иерархия"),
        "dbscan": ("DBSCAN (плотностной)", "", ""),
    }
    models: list[ModelResult] = []
    for algorithm_id, labels in (("kmeans", km_labels), ("agglomerative", ward_labels), ("dbscan", db_labels)):
        sil, db, per_cluster = quality_metrics(z, labels)
        k = int(np.unique(labels[labels != -1]).size)
        noise = round(float((labels == -1).mean() * 100.0), 1)
        name, suitability, badge = meta[algorithm_id]
        if algorithm_id == "dbscan":
            suitability = "Ограниченная" if noise > NOISE_LIMIT_PERCENT or k < 2 else "Умеренная"
            badge = f"Шум {fmt(noise, 1)} %" if noise > 10 else "Поиск аномалий"
        profiles = profile_clusters(raw, z, labels)
        for p in profiles:
            if p.cluster_no in per_cluster:
                p.silhouette = round(per_cluster[p.cluster_no], 4)
        models.append(ModelResult(
            algorithm_id=algorithm_id,
            name=name,
            silhouette_score=round(sil, 4),
            davies_bouldin_score=round(db, 4),
            cluster_count=k,
            noise_percent=noise,
            score=score_model(algorithm_id, sil, db, k, noise),
            business_suitability=suitability,
            suitability_badge=badge,
            labels=[int(v) for v in labels],
            clusters=profiles,
        ))

    best = max(models, key=lambda m: m.score)
    best.is_winner = True
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "Сравнение моделей выполнено",
        extra={"n_samples": n, "winner": best.algorithm_id, "duration_ms": duration_ms},
    )

    return BenchmarkResponse(
        n_samples=n,
        calculated_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        scaler=ScalerParams(mean=[float(v) for v in scaler.mean_], scale=[float(v) for v in scaler.scale_]),
        pca_coords=[[round(float(x), 4), round(float(y), 4)] for x, y in coords],
        models=models,
        winner=build_winner(best),
        xai=XaiData(
            elbow_curve=elbow,
            optimal_k=best_k,
            knn_distances=knn,
            selected_eps=eps,
            min_samples=DBSCAN_MIN_SAMPLES,
            dendrogram=dendro,
            explained_variance_ratio=[round(float(v), 4) for v in pca.explained_variance_ratio_],
        ),
    )


def assign_to_centroids(
    vectors: list[list[float]],
    mean: list[float],
    scale: list[float],
    centroids: list[Centroid],
) -> AssignResponse:
    """Классификация нового среза по центроидам утверждённой модели (без переобучения)."""
    started = time.perf_counter()
    raw = np.asarray(vectors, dtype=float)
    z = standardize(build_features(raw), np.asarray(mean), np.asarray(scale))
    matrix = np.asarray([c.z_center for c in centroids], dtype=float)
    numbers = np.asarray([c.cluster_no for c in centroids], dtype=int)
    labels = numbers[nearest_centroid(z, matrix)]
    return AssignResponse(labels=[int(v) for v in labels], duration_ms=int((time.perf_counter() - started) * 1000))
