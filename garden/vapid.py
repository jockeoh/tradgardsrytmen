import base64
import fcntl
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def get_vapid_keys():
    key_path = Path(os.environ.get("TRADGARDSRYTMEN_VAPID_KEY_PATH", settings.DATA_DIR / "vapid_private.pem"))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = key_path.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if key_path.exists():
            private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        else:
            private_key = ec.generate_private_key(ec.SECP256R1())
            key_path.write_bytes(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            key_path.chmod(0o600)
    numbers = private_key.public_key().public_numbers()
    public = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    private_number = private_key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(public), _b64url(private_number)

