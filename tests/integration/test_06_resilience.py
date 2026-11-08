"""Отказоустойчивость: недоступность интеллектуального сервиса не нарушает работу сервера (ROB-1)."""
import time

import pytest
from conftest import compose, wait_run

pytestmark = pytest.mark.resilience


def test_ai_service_outage(marketer, anon):
    compose("stop", "ai_service")
    try:
        health = anon.get("/health").json()
        assert health["status"] == "degraded" and health["database"] == "ok"
        run = marketer.post("/api/v1/segmentation/runs", json={"days_period": 365}).json()
        marketer.post(f"/api/v1/segmentation/runs/{run['id']}/benchmark", json={"target_k": None})
        failed = wait_run(marketer, run["id"], timeout=60)
        assert failed["status"] == "ошибка" and "недоступен" in failed["error_message"]
        assert marketer.get("/api/v1/clients", params={"limit": 5}).status_code == 200
        snapshot = marketer.post("/api/v1/segmentation/snapshots")
        assert snapshot.status_code == 503
    finally:
        compose("start", "ai_service")
    deadline = time.time() + 120
    while time.time() < deadline and anon.get("/health").json()["ai_service"] != "ok":
        time.sleep(2)
    assert anon.get("/health").json()["ai_service"] == "ok"
