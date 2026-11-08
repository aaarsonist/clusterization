"""Модульные тесты алгоритмического ядра интеллектуального микросервиса."""
import time

import numpy as np
import pytest
from conftest import make_vectors

from app.schemas.clustering import Centroid, ModelResult
from app.services import clustering as core


def test_features_log_transform():
    raw = np.array([[10.0, 0.0, 0.0], [5.0, np.e - 1, np.e**2 - 1]])
    features = core.build_features(raw)
    assert features[0].tolist() == [10.0, 0.0, 0.0]
    assert features[1, 1] == pytest.approx(1.0)
    assert features[1, 2] == pytest.approx(2.0)


def test_benchmark_structure(benchmark_1500):
    result = benchmark_1500
    assert result.n_samples == 1500
    assert len(result.pca_coords) == 1500
    assert [m.algorithm_id for m in result.models] == ["kmeans", "agglomerative", "dbscan"]
    for model in result.models:
        assert len(model.labels) == 1500
        assert sum(c.client_count for c in model.clusters) == 1500
    assert sum(m.is_winner for m in result.models) == 1
    assert len(result.xai.elbow_curve) == 7


def test_kmeans_finds_four_groups(benchmark_1500):
    kmeans = benchmark_1500.models[0]
    assert benchmark_1500.xai.optimal_k == 4
    assert kmeans.cluster_count == 4
    assert kmeans.silhouette_score > 0.5
    assert kmeans.noise_percent == 0


def test_segment_codes_and_unique_labels(benchmark_1500):
    clusters = benchmark_1500.models[0].clusters
    codes = {c.segment_code for c in clusters}
    assert {"vip", "churn", "newbie"} <= codes
    labels = [c.cluster_label for c in clusters]
    assert len(labels) == len(set(labels))
    vip = next(c for c in clusters if c.segment_code == "vip")
    assert vip.m_center == max(c.m_center for c in clusters)


def test_target_k_is_respected(vectors_1500):
    result = core.run_benchmark(vectors_1500, target_k=3)
    assert result.models[0].cluster_count == 3
    assert result.models[1].cluster_count == 3


def test_benchmark_is_deterministic(vectors_1500, benchmark_1500):
    again = core.run_benchmark(vectors_1500)
    assert again.models[0].labels == benchmark_1500.models[0].labels
    assert again.winner.algorithm_id == benchmark_1500.winner.algorithm_id


def test_assign_reproduces_training_labels(vectors_1500, benchmark_1500):
    kmeans = benchmark_1500.models[0]
    centroids = [Centroid(cluster_no=c.cluster_no, z_center=c.z_center) for c in kmeans.clusters]
    result = core.assign_to_centroids(vectors_1500, benchmark_1500.scaler.mean, benchmark_1500.scaler.scale, centroids)
    agreement = np.mean(np.array(result.labels) == np.array(kmeans.labels))
    assert agreement >= 0.99


def test_quality_metrics_degenerate_partition():
    z = np.random.default_rng(0).normal(size=(50, 3))
    assert core.quality_metrics(z, np.zeros(50, dtype=int)) == (0.0, 0.0, {})


def test_dbscan_noise_profile():
    z = np.vstack([np.random.default_rng(1).normal(0, 0.1, (60, 3)), [[8, 8, 8]]])
    labels, eps, knn = core.run_dbscan(z)
    assert labels[-1] == -1
    assert eps >= core.DBSCAN_EPS_MIN
    assert knn


def test_score_penalties():
    assert core.score_model("kmeans", 0.6, 0.5, 4, 0.0) == pytest.approx(0.525)
    assert core.score_model("dbscan", 0.6, 0.5, 4, 20.0) == pytest.approx(0.125)
    assert core.score_model("dbscan", 0.6, 0.5, 1, 0.0) == pytest.approx(-0.475)


def test_low_quality_flag():
    model = ModelResult(algorithm_id="kmeans", name="K-Means++", silhouette_score=0.2, davies_bouldin_score=1.5,
                        cluster_count=4, noise_percent=0, score=0, business_suitability="", suitability_badge="",
                        labels=[], clusters=[])
    winner = core.build_winner(model)
    assert winner.low_quality is True
    assert "ниже порога" in winner.recommendation


@pytest.mark.slow
def test_performance_50000_clients():
    vectors = make_vectors(50000, seed=7)
    started = time.perf_counter()
    result = core.run_benchmark(vectors)
    elapsed = time.perf_counter() - started
    assert result.n_samples == 50000
    assert elapsed < 5.0, f"полный цикл занял {elapsed:.2f} с"
