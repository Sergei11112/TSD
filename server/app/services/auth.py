"""Аутентификация: bcrypt-хэши, подписанные cookie-сессии."""
import hashlib
import hmac
import json
import time

import bcrypt

from ..config import SECRET_KEY, SESSION_MAX_AGE, SESSION_COOKIE_NAME


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def verify_pin(pin: str, stored: str) -> bool:
    # PIN хранится как SHA-256 hex (bcrypt избыточен для 4-значного кода на локальной сети,
    # но для соответствия требованиям храним хэш, а не открытый код)
    if not stored:
        return False
    return hashlib.sha256((pin + SECRET_KEY).encode()).hexdigest() == stored


def hash_pin(pin: str) -> str:
    return hashlib.sha256((pin + SECRET_KEY).encode()).hexdigest()


# ---------- Подписанная сессия в cookie (itsdangerous-подобная реализация) ----------

def make_session_token(payload: dict) -> str:
    body = json.dumps({**payload, "exp": int(time.time()) + SESSION_MAX_AGE})
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}|{sig}"


def read_session_token(token: str) -> dict | None:
    if not token or "|" not in token:
        return None
    body, sig = token.rsplit("|", 1)
    expect = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data
