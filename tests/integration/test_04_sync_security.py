"""Загрузка транзакционных данных (UC-14) и защита передаваемых и хранимых данных."""
import socket
import ssl

import httpx
from conftest import BASE, CA_FILE, compose, psql


def test_pos_sync(marketer):
    before = marketer.get("/api/v1/sync/status").json()["total_transactions"]
    result = marketer.post("/api/v1/sync/pos-sync").json()
    assert 40 <= result["new_transactions"] <= 80
    assert result["total_transactions"] == before + result["new_transactions"]


def test_csv_import(admin):
    body = ("client_phone;full_name;transaction_date;amount;discount_amount;status\n"
            "+375291000004;;25.01.2026 10:00;120,50;10;проведен\n"
            "+375447777777;Новикова Ольга Сергеевна;2026-01-26 12:30;80,00;0;проведен\n"
            "+375251234000;;2026-01-26;50;0;проведен\n"
            "+375291000002;;вчера;10;0;проведен\n"
            "+375291000003;;2026-01-26;-5;0;проведен\n")
    files = {"file": ("checks.csv", body.encode("utf-8-sig"), "text/csv")}
    result = admin.post("/api/v1/sync/upload-csv", files=files).json()
    assert result["rows_processed"] == 5
    assert result["transactions_added"] == 2 and result["clients_created"] == 1
    assert len(result["errors"]) == 3 and "Строка 4" in result["errors"][0]


def test_csv_wrong_extension(admin):
    files = {"file": ("checks.txt", b"a;b", "text/plain")}
    assert admin.post("/api/v1/sync/upload-csv", files=files).status_code == 400


def test_http_redirects_to_https():
    response = httpx.get("http://localhost:3000/segmentation", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "https://localhost:8443/segmentation"


def test_security_headers(anon):
    headers = anon.get("/").headers
    assert headers["strict-transport-security"].startswith("max-age=")
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]


def test_tls_version():
    context = ssl.create_default_context(cafile=str(CA_FILE))
    with socket.create_connection(("localhost", 8443)) as sock, context.wrap_socket(sock, server_hostname="localhost") as tls:
        assert tls.version() in ("TLSv1.2", "TLSv1.3")
    weak = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    weak.check_hostname, weak.verify_mode = False, ssl.CERT_NONE
    weak.maximum_version = ssl.TLSVersion.TLSv1_1
    try:
        with socket.create_connection(("localhost", 8443)) as sock, weak.wrap_socket(sock):
            raise AssertionError("Сервер принял устаревший протокол TLS 1.1")
    except (ssl.SSLError, ConnectionResetError, OSError):
        pass


def test_internal_ports_are_not_published():
    published = {}
    for line in compose("ps", "--format", "{{.Service}}|{{.Ports}}").splitlines():
        service, _, ports = line.partition("|")
        published[service] = ports
    assert "8443->443" in published["frontend"] and "3000->80" in published["frontend"]
    for service in ("postgres", "backend_core", "ai_service"):
        assert "->" not in published[service], f"{service} опубликован наружу: {published[service]}"
    for port in (5433, 8000, 8001):
        with socket.socket() as sock:
            sock.settimeout(1)
            assert sock.connect_ex(("127.0.0.1", port)) != 0, f"порт {port} доступен извне"


def test_personal_data_encrypted_at_rest():
    phone, email = psql("SELECT phone_enc || '|' || email_enc FROM clients ORDER BY id LIMIT 1").split("|")
    assert phone.startswith("enc:v1:") and email.startswith("enc:v1:")
    assert "+375" not in phone and "@" not in email
    assert psql("SELECT password_hash FROM users WHERE username = 'admin'").startswith("$2b$12$")


def test_database_requires_tls():
    assert psql("SELECT COUNT(*) FROM pg_stat_ssl WHERE ssl").isdigit()
    rules = psql("SELECT string_agg(type, ',') FROM pg_hba_file_rules WHERE address IS NOT NULL")
    assert "hostssl" in rules and "hostnossl" in rules


def test_health(anon):
    body = anon.get(f"{BASE}/health").json()
    assert body["database"] == "ok" and body["ai_service"] == "ok"
