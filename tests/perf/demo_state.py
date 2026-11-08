"""Подготовка демонстрационного состояния для снимков экрана: модель, правила, срез T1, копия, пользователи."""
from common import client, prepare_ca, run_benchmark, seed

RULES = {
    "vip": ("Привилегия лояльных лидеров: кешбэк 10 %", "кешбэк", 10, 100, 90),
    "churn": ("Возвращение клиента: скидка 20 %", "скидка", 20, 50, 30),
    "newbie": ("Второй заказ: скидка 10 %", "скидка", 10, 30, 45),
    "bargain": ("Клуб постоянных покупателей: 300 баллов", "баллы", 300, 60, 60),
}

prepare_ca()
seed(1500)
m = client("marketer", "Marketer#2026")
detail, _ = run_benchmark(m)
m.post(f"/api/v1/segmentation/runs/{detail['id']}/approve", json={"algorithm": detail["xai"]["winner"]["algorithm_id"]})
clusters = m.get("/api/v1/segmentation/current").json()["clusters"]
for code, (name, kind, value, min_check, days) in RULES.items():
    cluster = next(c for c in clusters if c["segment_code"] == code)
    m.post("/api/v1/loyalty/rules", json={"cluster_id": cluster["id"], "rule_name": name, "reward_type": kind,
                                          "reward_value": value, "min_check_amount": min_check, "days_valid": days})
m.post("/api/v1/loyalty/rules", json={"cluster_id": None, "rule_name": "Базовая скидка держателя карты 3 %",
                                      "reward_type": "скидка", "reward_value": 3, "min_check_amount": 0, "days_valid": 365})
print(m.post("/api/v1/sync/demo/simulate-month").json())
a = client("admin", "Admin#2026")
a.post("/api/v1/users", json={"username": "ivanova", "password": "Marketing#01", "role": "маркетолог"})
print(a.post("/api/v1/backups").json()["file_name"])
