import hashlib
import secrets

_PBKDF2_ITERATIONS = 120_000
_SALT_BYTES = 16


def hash_secret(value: str) -> str:
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${salt}${digest.hex()}"
