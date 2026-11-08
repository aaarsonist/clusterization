"""Замеры времени отклика и масштабируемости развернутой системы (требования PER-1…PER-4)."""
import json
import time

from common import REPORTS, client, prepare_ca, run_benchmark, seed, timed


def main() -> None:
    prepare_ca()
    report: dict = {"seed_1500_s": round(seed(1500), 1)}
    m = client("marketer", "Marketer#2026")
    anon_login = lambda: client.__globals__["httpx"].Client(base_url=m.base_url, verify=m._transport._pool._ssl_context, timeout=60).post(  # noqa: E731
        "/api/v1/auth/login", json={"username": "marketer", "password": "Marketer#2026"})
    api = {}
    api["Вход в систему (bcrypt, 12 раундов)"] = timed(anon_login, 10)
    api["Сводные показатели"] = timed(lambda: m.get("/api/v1/summary"), 30)
    api["Страница реестра клиентов (10 записей)"] = timed(lambda: m.get("/api/v1/clients?page=50&limit=10"), 30)
    api["Поиск клиента по ФИО"] = timed(lambda: m.get("/api/v1/clients", params={"search": "Иванова"}), 30)
    phone = m.get("/api/v1/clients?limit=1").json()["items"][0]["phone"]
    api["Поиск клиента по телефону (хеш-индекс)"] = timed(lambda: m.get("/api/v1/clients", params={"search": phone}), 30)
    api["Профиль клиента"] = timed(lambda: m.get("/api/v1/clients/100"), 30)
    api["Расчет выгоды по чеку на кассе"] = timed(lambda: m.post("/api/v1/loyalty/calculate-discount", json={"phone": phone, "check_amount": 120}), 30)

    cycles = [run_benchmark(m)[1] for _ in range(3)]
    detail, _ = run_benchmark(m)
    winner = detail["xai"]["winner"]["algorithm_id"]
    started = time.perf_counter()
    m.post(f"/api/v1/segmentation/runs/{detail['id']}/approve", json={"algorithm": winner})
    report["approve_ms"] = round((time.perf_counter() - started) * 1000, 1)
    api["Точки проекции PCA (1500)"] = timed(lambda: m.get(f"/api/v1/segmentation/runs/{detail['id']}/points?algorithm={winner}"), 10)
    api["Список рассылки CSV (1500 строк)"] = timed(lambda: m.get("/api/v1/segmentation/export?format=csv"), 10)
    api["Список рассылки Excel (1500 строк)"] = timed(lambda: m.get("/api/v1/segmentation/export?format=xlsx"), 5)
    api["Фиксация среза T1 (1500)"] = timed(lambda: m.post("/api/v1/segmentation/snapshots"), 3)
    api["Матрица миграции"] = timed(lambda: m.get("/api/v1/segmentation/migration"), 10)
    report["api"] = api
    report["benchmark_1500"] = cycles

    scale = {}
    for n in (10000, 50000):
        seeded = seed(n)
        m = client("marketer", "Marketer#2026")
        detail, times = run_benchmark(m)
        times["seed_s"] = round(seeded, 1)
        times["winner"] = detail["xai"]["winner"]["algorithm_id"]
        times["silhouette"] = next(x["silhouette_score"] for x in detail["metrics"]["models"] if x["is_winner"])
        m.post(f"/api/v1/segmentation/runs/{detail['id']}/approve", json={"algorithm": times["winner"]})
        times["export_csv"] = timed(lambda: m.get("/api/v1/segmentation/export?format=csv"), 3)
        times["points"] = timed(lambda: m.get(f"/api/v1/segmentation/runs/{detail['id']}/points?algorithm=kmeans"), 3)
        times["snapshot"] = timed(lambda: m.post("/api/v1/segmentation/snapshots"), 1)
        scale[n] = times
    report["scale"] = scale
    seed(1500)
    (REPORTS / "perf.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
