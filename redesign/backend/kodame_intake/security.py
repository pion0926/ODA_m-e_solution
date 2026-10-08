from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re


PBKDF2_ITERATIONS = 600_000
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LOGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("올바른 이메일 주소를 입력해 주세요.")
    return email


def normalize_login_identity(value: str) -> str:
    identity = str(value or "").strip().lower()
    if LOGIN_ID_PATTERN.fullmatch(identity):
        return f"{identity}@kodame.local"
    return normalize_email(identity)


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 10:
        raise ValueError("비밀번호는 10자 이상이어야 합니다.")
    if len(password) > 256:
        raise ValueError("비밀번호가 너무 깁니다.")
    return password


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS, validate: bool = True) -> str:
    password = validate_password(password) if validate else str(password or "")
    if not password:
        raise ValueError("비밀번호를 입력해 주세요.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw + "=" * (-len(salt_raw) % 4))
        expected = base64.urlsafe_b64decode(digest_raw + "=" * (-len(digest_raw) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
