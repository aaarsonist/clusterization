"""Формирование матрицы признаков, сравнение моделей, утверждение и мониторинг миграции (UC-3, UC-4, UC-6, UC-7, UC-12)."""
from conftest import wait_run


def test_feature_matrix(marketer):
    run = marketer.post("/api/v1/segmentation/runs", json={"days_period": 180})
    assert run.status_code == 201
    body = run.json()
    assert body["status"] == "черновик"
    assert body["features"]["clients"] == 1500
    assert 0 < body["features"]["active_clients"] <= 1500


def test_invalid_period_rejected(marketer):
    response = marketer.post("/api/v1/segmentation/runs", json={"days_period": 10})
    assert response.status_code == 422
    assert "не меньше 30" in response.json()["detail"][0]["msg"]


def test_benchmark_and_approval(approved, marketer):
    run = approved["run"]
    assert run["status"] == "рассчитан"
    models = {m["algorithm_id"]: m for m in run["metrics"]["models"]}
    assert set(models) == {"kmeans", "agglomerative", "dbscan"}
    assert models["kmeans"]["silhouette_score"] > 0.35
    assert len(run["xai"]["elbow_curve"]) == 7
    assert run["xai"]["dendrogram"]["cut_threshold"] > 0
    current = approved["current"]
    assert current["is_initialized"] and current["assigned_clients"] == 1500
    assert {c["segment_code"] for c in current["clusters"]} >= {"vip", "churn"}
    repeat = marketer.post(f"/api/v1/segmentation/runs/{run['id']}/approve", json={"algorithm": "kmeans"})
    assert repeat.status_code == 409


def test_points_for_scatter(approved, marketer):
    run_id = approved["run"]["id"]
    for algorithm in ("kmeans", "agglomerative", "dbscan"):
        points = marketer.get(f"/api/v1/segmentation/runs/{run_id}/points", params={"algorithm": algorithm}).json()
        assert points["total"] == 1500 and points["shown"] == 1500
        assert {"pca_x", "pca_y", "cluster_label"} <= set(points["points"][0])


def test_target_k(marketer):
    run = marketer.post("/api/v1/segmentation/runs", json={"days_period": 365}).json()
    marketer.post(f"/api/v1/segmentation/runs/{run['id']}/benchmark", json={"target_k": 5})
    done = wait_run(marketer, run["id"])
    kmeans = next(m for m in done["metrics"]["models"] if m["algorithm_id"] == "kmeans")
    assert kmeans["cluster_count"] == 5


def test_migration_requires_second_snapshot(approved, marketer):
    dashboard = marketer.get("/api/v1/segmentation/migration").json()
    assert dashboard["state"] == "need_second_snapshot"


def test_month_simulation_and_migration(approved, marketer):
    result = marketer.post("/api/v1/sync/demo/simulate-month")
    assert result.status_code == 200, result.text
    assert result.json()["tracked_clients"] == 1500
    dashboard = marketer.get("/api/v1/segmentation/migration").json()
    assert dashboard["state"] == "ready"
    matrix = dashboard["matrix"]["matrix"]
    assert sum(map(sum, matrix)) == dashboard["summary"]["total_clients_compared"] == 1500
    diagonal = sum(matrix[i][i] for i in range(len(matrix)))
    assert diagonal == dashboard["summary"]["retained"]
    assert dashboard["summary"]["total_migrated"] > 0


def test_drilldown_and_exports(approved, marketer):
    dashboard = marketer.get("/api/v1/segmentation/migration").json()
    segments, matrix = dashboard["matrix"]["segments"], dashboard["matrix"]["matrix"]
    i, j = next((i, j) for i in range(len(matrix)) for j in range(len(matrix)) if i != j and matrix[i][j])
    params = {"from_cluster": segments[i]["cluster_id"], "to_cluster": segments[j]["cluster_id"]}
    cell = marketer.get("/api/v1/segmentation/migration/clients", params=params).json()
    assert cell["total_clients"] == matrix[i][j]
    csv = marketer.get("/api/v1/segmentation/migration/clients/export", params={**params, "format": "csv"})
    assert csv.content.startswith(b"\xef\xbb\xbf") and csv.headers["content-type"].startswith("text/csv")
    xlsx = marketer.get("/api/v1/segmentation/migration/export", params={"format": "xlsx"})
    assert xlsx.content[:2] == b"PK"
    mailing = marketer.get("/api/v1/segmentation/export", params={"cluster_id": segments[0]["cluster_id"]})
    lines = mailing.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("Номер телефона;ФИО") and lines[1].startswith("+375")
