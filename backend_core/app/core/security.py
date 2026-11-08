"""Криптографические примитивы: пароли, токены, шифрование и хеш-индексы персональных данных."""
import base64
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

ENC_PREFIX = "enc:v1:"
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-zА-Яа-яЁё])(?=.*\d).{8,128}$")


def _key(b64: str) -> bytes:
    key = base64.b64decode(b64)
    if len(key) != 32:
        raise ValueError("Ключ должен иметь длину 256 бит (32 байта)")
    return key


_PII_KEY = _key(settings.PII_ENCRYPTION_KEY)
_HMAC_KEY = base64.b64decode(settings.PII_HMAC_KEY)


# --- пароли -----------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def password_is_strong(password: str) -> bool:
    """Политика паролей: не менее 8 символов, хотя бы одна буква и одна цифра."""
    return bool(PASSWORD_RE.match(password))


# --- JWT ----------------------------------------------------------------------
def create_access_token(user_id: int, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# --- AES-256-GCM ---------------------------------------------------------------
def encrypt_bytes(data: bytes, key: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt_bytes(blob: bytes, key: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def encrypt_pii(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    blob = encrypt_bytes(value.encode("utf-8"), _PII_KEY, b"pii")
    return ENC_PREFIX + base64.b64encode(blob).decode("ascii")


def decrypt_pii(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(ENC_PREFIX):
        return value
    blob = base64.b64decode(value[len(ENC_PREFIX):])
    return decrypt_bytes(blob, _PII_KEY, b"pii").decode("utf-8")


def blind_index(value: str) -> str:
    """Детерминированный хеш-индекс HMAC-SHA-256 для поиска по зашифрованным значениям."""
    return hmac.new(_HMAC_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()


# --- телефоны и e-mail --------------------------------------------------------
def phone_digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_phone(raw: str | None) -> str | None:
    """Приведение номера Республики Беларусь к формату E.164 (+375XXXXXXXXX)."""
    digits = phone_digits(raw)
    if digits.startswith("80") and len(digits) == 11:
        digits = "375" + digits[2:]
    elif len(digits) == 9:
        digits = "375" + digits
    if not (digits.startswith("375") and len(digits) == 12):
        return None
    return "+" + digits


def phone_hash(e164: str) -> str:
    return blind_index("phone:" + phone_digits(e164))


def phone_tail_hash(raw: str) -> str:
    return blind_index("tail:" + phone_digits(raw)[-7:])


def email_hash(email: str) -> str:
    return blind_index("email:" + email.strip().lower())
