"""Общие функции замеров: подключение к развернутой системе, генерация данных, ожидание расчета."""
import ssl
import statistics
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "tests" / "reports"
CA = REPORTS / "ca.crt"
BASE = "https://localhost:8443"


def compose(*args: str, timeout: int = 1800) -> str:
    result = subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout, check=True)
    return result.stdout


def prepare_ca() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CA.write_text(compose("exec", "-T", "backend_core", "cat", "/certs/ca.crt"), encoding="utf-8")


def seed(clients: int) -> float:
    started = time.perf_counter()
    compose("exec", "-T", "backend_core", "python", "scripts/seed_data.py", "--clients", str(clients))
    return time.perf_counter() - started


def client(username: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, verify=ssl.create_default_context(cafile=str(CA)), timeout=600)
    token = c.post("/api/v1/auth/login", json={"username": username, "password": password}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def timed(fn, repeat: int) -> dict:
    samples = []
    for _ in range(repeat):
        started = time.perf_counter()
        response = fn()
        samples.append((time.perf_counter() - started) * 1000)
        assert response.status_code < 400, response.text[:300]
    samples.sort()
    return {"n": repeat, "median_ms": round(statistics.median(samples), 1),
            "p95_ms": round(samples[max(0, int(len(samples) * 0.95) - 1)], 1), "max_ms": round(samples[-1], 1)}


def run_benchmark(c: httpx.Client, days: int = 365, target_k: int | None = None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    run = c.post("/api/v1/segmentation/runs", json={"days_period": days}).json()
    t1 = time.perf_counter()
    c.post(f"/api/v1/segmentation/runs/{run['id']}/benchmark", json={"target_k": target_k})
    while True:
        detail = c.get(f"/api/v1/segmentation/runs/{run['id']}").json()
        if detail["status"] not in ("черновик", "расчет"):
            break
        time.sleep(0.2)
    t2 = time.perf_counter()
    assert detail["status"] == "рассчитан", detail.get("error_message")
    return detail, {"matrix_s": round(t1 - t0, 2), "benchmark_s": round(t2 - t1, 2),
                    "ai_s": round(detail["metrics"]["duration_ms"] / 1000, 2)}
