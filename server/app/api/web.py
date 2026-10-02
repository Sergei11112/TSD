"""Веб-интерфейс контролёра (Jinja2, стиль 1С:WMS). Базовые страницы + вход."""
import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Nomenclature, Location, Box, Task, Document, Employee
from ..services.auth import verify_password, make_session_token, read_session_token
from ..config import SESSION_COOKIE_NAME, SESSION_MAX_AGE, APP_TITLE

router = APIRouter(tags=["web"])
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/terminal", include_in_schema=False)
def terminal_page():
    """Экран ТСД (тонкий клиент): WebView-обёртка открывает этот адрес."""
    return FileResponse(os.path.join(STATIC_DIR, "terminal.html"))


def redir_login():
    return RedirectResponse("/login", status_code=303)


def current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    data = read_session_token(token or "")
    if not data:
        return None
    u = db.get(User, data.get("uid"))
    return u if u and u.is_active else None


def require_role(request: Request, db: Session, roles=("admin", "controller")):
    u = current_user(request, db)
    if not u or u.role not in roles:
        return None
    return u


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error,
                                                     "app_title": APP_TITLE})


@router.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...),
               db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == username).first()
    if not u or not u.is_active or not verify_password(password, u.password_hash):
        return login_page(request, error="Неверный логин или пароль")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE_NAME, make_session_token({"uid": u.id}),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)
    stats = {
        "nomenclature": db.query(Nomenclature).count(),
        "locations": db.query(Location).count(),
        "boxes": db.query(Box).count(),
        "tasks_open": db.query(Task).filter(Task.status.in_(["draft", "sent", "in_progress"])).count(),
        "docs": db.query(Document).filter(Document.status == "posted").count(),
        "employees": db.query(Employee).filter(Employee.is_active == True).count(),  # noqa: E712
    }
    recent_docs = db.query(Document).order_by(Document.created_at.desc()).limit(10).all()
    recent_tasks = db.query(Task).order_by(Task.created_at.desc()).limit(10).all()
    return templates.TemplateResponse("dashboard.html",
                                      {"request": request, "user": u, "stats": stats,
                                       "recent_docs": recent_docs, "recent_tasks": recent_tasks,
                                       "app_title": APP_TITLE, "active": "dashboard"})
