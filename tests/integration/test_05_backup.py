"""Резервное копирование и восстановление базы данных (UC-11)."""
from conftest import ROOT, psql


def test_backup_create_and_restore(admin):
    created = admin.post("/api/v1/backups")
    assert created.status_code == 201, created.text
    item = created.json()
    path = ROOT / "backups" / item["file_name"]
    assert path.is_file() and path.stat().st_size == item["size_bytes"]
    assert not path.read_bytes().startswith(b"PGDMP"), "копия должна храниться в зашифрованном виде"

    clients_before = psql("SELECT COUNT(*) FROM clients")
    psql("INSERT INTO loyalty_rules (rule_name, reward_type, reward_value, days_valid) VALUES ('Временное', 'баллы', 1, 1)")
    restored = admin.post(f"/api/v1/backups/{item['file_name']}/restore")
    assert restored.status_code == 200, restored.text
    assert psql("SELECT COUNT(*) FROM loyalty_rules WHERE rule_name = 'Временное'") == "0"
    assert psql("SELECT COUNT(*) FROM clients") == clients_before
    overview = admin.get("/api/v1/backups").json()
    kinds = {b["kind"] for b in overview["backups"]}
    assert {"ручная", "перед восстановлением"} <= kinds


def test_backup_settings(admin):
    saved = admin.put("/api/v1/backups/settings", json={"enabled": True, "run_hour": 3, "retention_count": 10})
    assert saved.status_code == 200 and saved.json()["run_hour"] == 3
    assert admin.put("/api/v1/backups/settings", json={"enabled": True, "run_hour": 30, "retention_count": 10}).status_code == 422


def test_restore_unknown_file(admin):
    assert admin.post("/api/v1/backups/missing.dump.enc/restore").status_code == 404
