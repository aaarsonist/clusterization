import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend_core"))
os.environ.update({
    "POSTGRES_PASSWORD": "test", "POSTGRES_SSL": "false",
    "JWT_SECRET_KEY": "unit-test-secret-key-0123456789abcdef",
    "PII_ENCRYPTION_KEY": base64.b64encode(b"k" * 32).decode(),
    "PII_HMAC_KEY": base64.b64encode(b"h" * 32).decode(),
    "BACKUP_ENCRYPTION_KEY": base64.b64encode(b"b" * 32).decode(),
})
