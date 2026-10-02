"""Общие помощники CRUD для веб-интерфейса контролёра."""
from fastapi import Form, Request
from sqlalchemy.orm import Session

from .models import User
from .config import SESSION_COOKIE_NAME, SESSION_MAX_AGE


def get_form(request: Request, name: str, default: str = "") -> str:
    """Поле формы (multipart или urlencoded)."""
    try:
        v = request.form.get(name)
    except Exception:
        v = None
    if v is None:
        v = request.query_params.get(name, default)
    return (v or "").strip() if v is not None else default


async def parse_form(request: Request) -> dict:
    f = await request.form()
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in f.items()}


def num(value, default=0.0):
    try:
        s = str(value).replace(",", ".").strip()
        return float(s) if s != "" else default
    except (ValueError, TypeError):
        return default


def set_session(resp, user: User):
    from .services.auth import make_session_token
    resp.set_cookie(SESSION_COOKIE_NAME, make_session_token({"uid": user.id}),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


def loc_label(loc) -> str:
    return f"{loc.code} · {loc.name}" if loc else "—"


def full_path(loc) -> str:
    """Цепочка склад/стеллаж/полка/ячейка."""
    parts = []
    seen = 0
    cur = loc
    while cur is not None and seen < 10:
        parts.append(cur.code)
        cur = cur.parent
        seen += 1
    return " → ".join(reversed(parts)) if parts else "—"
