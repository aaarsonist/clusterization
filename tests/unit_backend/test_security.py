"""Модульные тесты криптографических функций и нормализации персональных данных."""
import jwt
from cryptography.exceptions import InvalidTag
import pytest

from app.core import security


def test_pii_encryption_roundtrip_and_randomized_nonce():
    a = security.encrypt_pii("+375291234567")
    b = security.encrypt_pii("+375291234567")
    assert a.startswith("enc:v1:") and b.startswith("enc:v1:")
    assert a != b
    assert security.decrypt_pii(a) == "+375291234567"


def test_tampered_ciphertext_is_rejected():
    token = security.encrypt_pii("секрет")
    broken = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidTag):
        security.decrypt_pii(broken)


def test_blind_index_is_deterministic():
    assert security.phone_hash("+375291234567") == security.phone_hash("+375 (29) 123-45-67")
    assert security.phone_hash("+375291234567") != security.phone_hash("+375291234568")
    assert security.phone_tail_hash("1234567") == security.phone_tail_hash("+375291234567")


@pytest.mark.parametrize("raw, expected", [
    ("+375 (29) 123-45-67", "+375291234567"),
    ("80291234567", "+375291234567"),
    ("291234567", "+375291234567"),
    ("375441112233", "+375441112233"),
    ("12345", None),
    ("+7 999 123-45-67", None),
])
def test_normalize_phone(raw, expected):
    assert security.normalize_phone(raw) == expected


@pytest.mark.parametrize("password, ok", [
    ("Admin#2026", True), ("password1", True), ("короткий1", True),
    ("short1", False), ("onlyletters", False), ("12345678", False),
])
def test_password_policy(password, ok):
    assert security.password_is_strong(password) is ok


def test_password_hashing():
    hashed = security.hash_password("Marketer#2026")
    assert hashed.startswith("$2b$12$")
    assert security.verify_password("Marketer#2026", hashed)
    assert not security.verify_password("wrong", hashed)
    assert not security.verify_password("x", "not-a-hash")


def test_jwt_roundtrip_and_expiry(monkeypatch):
    token = security.create_access_token(7, "marketer", "маркетолог")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "7" and payload["role"] == "маркетолог"
    monkeypatch.setattr(security.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
    expired = security.create_access_token(7, "marketer", "маркетолог")
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(expired)


def test_jwt_signature_forgery_rejected():
    forged = jwt.encode({"sub": "1", "role": "администратор"}, "другой-ключ-подписи-0123456789abcdef", algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        security.decode_access_token(forged)


def test_aes_gcm_aad_binding():
    blob = security.encrypt_bytes(b"dump", b"k" * 32, b"backup_1.dump.enc")
    assert security.decrypt_bytes(blob, b"k" * 32, b"backup_1.dump.enc") == b"dump"
    with pytest.raises(InvalidTag):
        security.decrypt_bytes(blob, b"k" * 32, b"backup_2.dump.enc")
