import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

_PBKDF2_ITERATIONS = 120_000
_SALT_BYTES = 16
_PASSWORD_HASH = PasswordHash.recommended()


def _hash_secret_pbkdf2(value: str) -> str:
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _verify_pbkdf2(value: str, hashed_value: str) -> bool:
    try:
        algorithm, salt, expected_digest = hashed_value.split("$", maxsplit=2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return hmac.compare_digest(digest.hex(), expected_digest)


def hash_password(value: str) -> str:
    return _PASSWORD_HASH.hash(value)


def verify_password(value: str, hashed_value: str) -> bool:
    if hashed_value.startswith("pbkdf2_sha256$"):
        return _verify_pbkdf2(value, hashed_value)
    return _PASSWORD_HASH.verify(value, hashed_value)


def password_needs_rehash(hashed_value: str) -> bool:
    return hashed_value.startswith("pbkdf2_sha256$")


def hash_secret(value: str) -> str:
    return _hash_secret_pbkdf2(value)
