"""Аутентификация, ролевой контроль доступа и управление учетными записями (UC-1, UC-10)."""
import uuid

import pytest
from conftest import ADMIN, MARKETER, login


def test_login_success_returns_role(anon):
    for (username, password), role in ((MARKETER, "маркетолог"), (ADMIN, "администратор")):
        body = anon.post("/api/v1/auth/login", json={"username": username, "password": password}).json()
        assert body["role"] == role and body["token_type"] == "bearer" and body["expires_in"] == 480 * 60


def test_login_wrong_password(anon):
    response = anon.post("/api/v1/auth/login", json={"username": "marketer", "password": "неверный1"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный логин или пароль."


def test_requests_without_token_are_rejected(anon):
    assert anon.get("/api/v1/summary").status_code == 401
    assert anon.get("/api/v1/clients").status_code == 401


MARKETER_ONLY = [("GET", "/api/v1/clients"), ("GET", "/api/v1/segmentation/current"), ("GET", "/api/v1/loyalty/rules"),
                 ("GET", "/api/v1/segmentation/migration"), ("GET", "/api/v1/segmentation/export")]
ADMIN_ONLY = [("GET", "/api/v1/users"), ("GET", "/api/v1/backups"), ("GET", "/api/v1/audit"),
              ("POST", "/api/v1/sync/demo/reset-zero-state")]
BOTH = [("GET", "/api/v1/summary"), ("GET", "/api/v1/sync/status"), ("GET", "/api/v1/auth/me")]


@pytest.mark.parametrize("method, path", MARKETER_ONLY)
def test_admin_has_no_access_to_customer_data(admin, method, path):
    assert admin.request(method, path).status_code == 403


@pytest.mark.parametrize("method, path", ADMIN_ONLY)
def test_marketer_has_no_access_to_administration(marketer, method, path):
    assert marketer.request(method, path).status_code == 403


@pytest.mark.parametrize("method, path", BOTH)
def test_common_functions(admin, marketer, method, path):
    assert admin.request(method, path).status_code == 200
    assert marketer.request(method, path).status_code == 200


def test_user_lifecycle(admin, anon):
    username = f"test_{uuid.uuid4().hex[:6]}"
    weak = admin.post("/api/v1/users", json={"username": username, "password": "12345678", "role": "маркетолог"})
    assert weak.status_code == 422
    created = admin.post("/api/v1/users", json={"username": username, "password": "Test#2026a", "role": "маркетолог"})
    assert created.status_code == 201
    user_id = created.json()["id"]
    duplicate = admin.post("/api/v1/users", json={"username": username, "password": "Test#2026a", "role": "маркетолог"})
    assert duplicate.status_code == 409
    assert login(username, "Test#2026a").get("/api/v1/clients").status_code == 200

    assert admin.patch(f"/api/v1/users/{user_id}", json={"role": "администратор"}).json()["role"] == "администратор"
    assert admin.post(f"/api/v1/users/{user_id}/password", json={"password": "New#2026pass"}).status_code == 200
    assert admin.patch(f"/api/v1/users/{user_id}", json={"is_active": False}).json()["is_active"] is False
    denied = anon.post("/api/v1/auth/login", json={"username": username, "password": "New#2026pass"})
    assert denied.status_code == 403


def test_admin_cannot_deactivate_self(admin):
    me = admin.get("/api/v1/auth/me").json()
    assert admin.patch(f"/api/v1/users/{me['id']}", json={"is_active": False}).status_code == 409


def test_bruteforce_lockout(admin, anon):
    username = f"lock_{uuid.uuid4().hex[:6]}"
    admin.post("/api/v1/users", json={"username": username, "password": "Lock#2026a", "role": "маркетолог"})
    codes = [anon.post("/api/v1/auth/login", json={"username": username, "password": "wrong-pass1"}).status_code
             for _ in range(5)]
    assert codes == [401] * 5
    locked = anon.post("/api/v1/auth/login", json={"username": username, "password": "Lock#2026a"})
    assert locked.status_code == 429


def test_audit_records_logins(admin):
    page = admin.get("/api/v1/audit", params={"action": "Вход в систему", "limit": 200}).json()
    assert page["total"] > 0
    assert any(not item["success"] for item in page["items"])
