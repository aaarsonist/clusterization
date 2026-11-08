"""Проверка обработки некорректных запросов без обращения к СУБД (сообщения на русском языке)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_validation_messages_are_russian():
    response = client.post("/api/v1/auth/login", json={"username": ""})
    assert response.status_code == 422
    messages = {e["field"]: e["msg"] for e in response.json()["detail"]}
    assert messages["password"] == "обязательное поле"
    assert "минимум" in messages["username"]


def test_protected_endpoint_requires_token():
    response = client.get("/api/v1/clients")
    assert response.status_code == 401
    assert response.json()["detail"] == "Требуется аутентификация в системе."


def test_invalid_token_rejected():
    response = client.get("/api/v1/clients", headers={"Authorization": "Bearer abc.def.ghi"})
    assert response.status_code == 401
    assert "токен" in response.json()["detail"]
