"""Интеграционные тесты работающей системы (docker compose) через веб-шлюз https://localhost:8443."""
import os
import ssl
import subprocess
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = os.getenv("API_BASE", "https://localhost:8443")
CA_FILE = Path(__file__).with_name(".ca.crt")
MARKETER = ("marketer", "Marketer#2026")
ADMIN = ("admin", "Admin#2026")


def compose(*args: str, check: bool = True, timeout: int = 600) -> str:
    result = subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def psql(sql: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "loyalty_db", "-At", "-c", sql).strip()


def tls() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(CA_FILE))


def login(username: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, verify=tls(), timeout=120)
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def wait_run(client: httpx.Client, run_id: int, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/v1/segmentation/runs/{run_id}").json()
        if run["status"] not in ("черновик", "расчет"):
            return run
        time.sleep(1)
    raise TimeoutError("Расчет прогона не завершился")


@pytest.fixture(scope="session", autouse=True)
def environment():
    CA_FILE.write_text(compose("exec", "-T", "backend_core", "cat", "/certs/ca.crt"), encoding="utf-8")
    if os.getenv("SKIP_RESEED") != "1":
        compose("exec", "-T", "backend_core", "python", "scripts/seed_data.py")
    yield


@pytest.fixture(scope="session")
def anon() -> httpx.Client:
    return httpx.Client(base_url=BASE, verify=tls(), timeout=60)


@pytest.fixture(scope="session")
def marketer() -> httpx.Client:
    return login(*MARKETER)


@pytest.fixture(scope="session")
def admin() -> httpx.Client:
    return login(*ADMIN)


@pytest.fixture(scope="session")
def approved(marketer) -> dict:
    """Прогон с рассчитанными моделями и утвержденным победителем (срез T0)."""
    run = marketer.post("/api/v1/segmentation/runs", json={"days_period": 365}).json()
    marketer.post(f"/api/v1/segmentation/runs/{run['id']}/benchmark", json={"target_k": None})
    run = wait_run(marketer, run["id"])
    assert run["status"] == "рассчитан", run.get("error_message")
    winner = run["xai"]["winner"]["algorithm_id"]
    approval = marketer.post(f"/api/v1/segmentation/runs/{run['id']}/approve", json={"algorithm": winner})
    assert approval.status_code == 200, approval.text
    current = marketer.get("/api/v1/segmentation/current").json()
    return {"run": run, "approval": approval.json(), "current": current}
