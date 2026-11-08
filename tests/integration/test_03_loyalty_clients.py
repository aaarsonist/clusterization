"""Клиентская база, профиль клиента и программа лояльности (UC-2, UC-5, UC-8, UC-9, UC-13)."""
import io

from openpyxl import load_workbook


def test_clients_pagination_and_search(marketer):
    page = marketer.get("/api/v1/clients", params={"page": 2, "limit": 10}).json()
    assert page["total"] == 1500 and page["pages"] == 150 and len(page["items"]) == 10
    first = page["items"][0]
    by_name = marketer.get("/api/v1/clients", params={"search": first["full_name"].split()[0]}).json()
    assert by_name["total"] >= 1
    by_phone = marketer.get("/api/v1/clients", params={"search": first["phone"]}).json()
    assert [c["id"] for c in by_phone["items"]] == [first["id"]]
    by_tail = marketer.get("/api/v1/clients", params={"search": first["phone"][-7:]}).json()
    assert first["id"] in [c["id"] for c in by_tail["items"]]
    nothing = marketer.get("/api/v1/clients", params={"search": "Несуществующий Клиент"}).json()
    assert nothing["total"] == 0


def test_cluster_filter(approved, marketer):
    cluster = approved["current"]["clusters"][0]
    page = marketer.get("/api/v1/clients", params={"cluster_id": cluster["id"], "limit": 100}).json()
    assert page["total"] > 0 and all(c["cluster_id"] == cluster["id"] for c in page["items"])


def test_client_profile(marketer):
    profile = marketer.get("/api/v1/clients/1").json()
    assert profile["phone"].startswith("+375") and "@" in profile["email"]
    assert profile["frequency"] > 0 and len(profile["transactions"]) > 0
    assert marketer.get("/api/v1/clients/999999").status_code == 404


def test_rule_lifecycle_and_discount(approved, marketer):
    cluster = next(c for c in approved["current"]["clusters"] if c["segment_code"] == "vip")
    invalid = marketer.post("/api/v1/loyalty/rules", json={
        "cluster_id": cluster["id"], "rule_name": "Ошибка", "reward_type": "скидка", "reward_value": 150, "days_valid": 30})
    assert invalid.status_code == 422
    created = marketer.post("/api/v1/loyalty/rules", json={
        "cluster_id": cluster["id"], "rule_name": "Привилегия лидеров", "reward_type": "скидка",
        "reward_value": 12, "min_check_amount": 50, "days_valid": 30})
    assert created.status_code == 201
    rule = created.json()
    assert rule["audience_count"] == cluster["client_count"]

    audience = marketer.get(f"/api/v1/loyalty/rules/{rule['id']}/clients", params={"limit": 5}).json()
    client = audience["clients"][0]
    discount = marketer.post("/api/v1/loyalty/calculate-discount", json={"phone": client["phone"], "check_amount": 200})
    assert discount.json()["applied_rule_id"] == rule["id"]
    assert discount.json()["discount_amount"] == "24.00" and discount.json()["final_amount"] == "176.00"

    marketer.delete(f"/api/v1/loyalty/rules/{rule['id']}/clients/{client['client_id']}")
    after = marketer.post("/api/v1/loyalty/calculate-discount", json={"client_id": client["client_id"], "check_amount": 200})
    assert after.json()["applied_rule_id"] != rule["id"]
    updated = marketer.get("/api/v1/loyalty/rules").json()
    assert next(r for r in updated if r["id"] == rule["id"])["audience_count"] == cluster["client_count"] - 1

    toggled = marketer.put(f"/api/v1/loyalty/rules/{rule['id']}", json={"is_active": False})
    assert toggled.json()["is_active"] is False
    export = marketer.get(f"/api/v1/loyalty/rules/{rule['id']}/export", params={"format": "xlsx"})
    sheet = load_workbook(io.BytesIO(export.content)).active
    assert sheet["A1"].value == "Номер телефона" and sheet.max_row == cluster["client_count"]
    assert marketer.delete(f"/api/v1/loyalty/rules/{rule['id']}").status_code == 200


def test_manual_inclusion_into_other_rule(approved, marketer):
    clusters = approved["current"]["clusters"]
    rule = marketer.post("/api/v1/loyalty/rules", json={
        "cluster_id": clusters[-1]["id"], "rule_name": "Ручное включение", "reward_type": "баллы",
        "reward_value": 500, "days_valid": 10}).json()
    outsider = marketer.get("/api/v1/clients", params={"cluster_id": clusters[0]["id"], "limit": 1}).json()["items"][0]
    assert marketer.post(f"/api/v1/loyalty/rules/{rule['id']}/clients", json={"client_id": outsider["id"]}).status_code == 200
    profile = marketer.get(f"/api/v1/clients/{outsider['id']}").json()
    assert any(r["id"] == rule["id"] and r["source"] == "персональное" for r in profile["rules"])
    marketer.delete(f"/api/v1/loyalty/rules/{rule['id']}")


def test_discount_unknown_client(marketer):
    response = marketer.post("/api/v1/loyalty/calculate-discount", json={"phone": "+375 25 000-00-00", "check_amount": 10})
    assert response.status_code == 404
