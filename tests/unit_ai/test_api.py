"""Тесты REST-интерфейса интеллектуального микросервиса (валидация входных данных)."""
from conftest import make_vectors
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_benchmark_endpoint():
    response = client.post("/api/v1/clusterize/benchmark", json={"vectors": make_vectors(200), "target_k": None})
    assert response.status_code == 200
    body = response.json()
    assert body["n_samples"] == 200
    assert body["winner"]["algorithm_id"] in ("kmeans", "agglomerative", "dbscan")


def test_rejects_too_few_vectors():
    response = client.post("/api/v1/clusterize/benchmark", json={"vectors": [[1, 1, 1]] * 3})
    assert response.status_code == 422


def test_rejects_negative_values():
    response = client.post("/api/v1/clusterize/benchmark", json={"vectors": [[1, 1, 1]] * 4 + [[-1, 2, 3]]})
    assert response.status_code == 422


def test_rejects_k_not_less_than_n():
    response = client.post("/api/v1/clusterize/benchmark", json={"vectors": make_vectors(20)[:5], "target_k": 5})
    assert response.status_code == 422


def test_assign_endpoint():
    payload = {
        "vectors": [[1, 10, 1000], [200, 1, 10]],
        "scaler": {"mean": [50, 1.5, 5.0], "scale": [60, 1.0, 2.0]},
        "centroids": [{"cluster_no": 0, "z_center": [-1, 1, 1]}, {"cluster_no": 1, "z_center": [2, -1, -1]}],
    }
    response = client.post("/api/v1/clusterize/assign", json=payload)
    assert response.status_code == 200
    assert response.json()["labels"] == [0, 1]
