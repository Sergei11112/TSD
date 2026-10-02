"""JSON API для тонкого клиента ТСД: авторизация по PIN, задания, сканирования."""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Task, IssuedItem, AssetInstance, Employee
from ..services.auth import verify_pin, make_session_token, read_session_token
from ..services.task_logic import process_scan, ScanError, next_task_number
from ..config import SESSION_COOKIE_NAME, SESSION_MAX_AGE

router = APIRouter(prefix="/api/terminal", tags=["tcd"])


class LoginReq(BaseModel):
    user_id: int
    pin: str


class ScanReq(BaseModel):
    task_id: int
    code: str
    qty: float | None = None
    device_id: str = ""
    current_location_id: int | None = None


def _terminal_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    data = read_session_token(token or "")
    if not data:
        return None
    return db.get(User, data.get("uid"))


@router.get("/users")
def list_terminal_users(db: Session = Depends(get_db)):
    """Список пользователей для экрана авторизации ТСД (worker/controller)."""
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    return [{"id": u.id, "full_name": u.full_name or u.username, "role": u.role}
            for u in users]


@router.post("/login")
def login(req: LoginReq, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, req.user_id)
    if not user or not user.is_active:
        return {"ok": False, "error": "Пользователь не найден"}
    if not verify_pin(req.pin, user.pin_code):
        return {"ok": False, "error": "Неверный PIN-код"}
    from fastapi.responses import JSONResponse
    resp = JSONResponse({"ok": True, "user_id": user.id, "full_name": user.full_name,
                         "role": user.role})
    resp.set_cookie(SESSION_COOKIE_NAME, make_session_token({"uid": user.id}),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@router.get("/tasks")
def my_tasks(request: Request, db: Session = Depends(get_db)):
    user = _terminal_user(request, db)
    if not user:
        return {"ok": False, "error": "Не авторизован"}
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    q = db.query(Task).filter(Task.status.in_(["sent", "in_progress"]))
    if user.role != "admin":
        if emp:
            q = q.filter(Task.employee_id == emp.id)
        else:
            q = q.filter(Task.assigned_device == "")
    tasks = q.order_by(Task.created_at.desc()).all()
    return [{
        "id": t.id, "number": t.number, "type": t.type, "status": t.status,
        "notes": t.notes,
        "lines_total": len(t.lines),
        "lines_done": sum(1 for l in t.lines if l.status == "completed"),
    } for t in tasks]


@router.get("/tasks/{task_id}")
def task_detail(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = _terminal_user(request, db)
    if not user:
        return {"ok": False, "error": "Не авторизован"}
    t = db.get(Task, task_id)
    if not t:
        return {"ok": False, "error": "Задание не найдено"}
    lines = []
    for l in t.lines:
        lines.append({
            "id": l.id, "action_type": l.action_type,
            "nomenclature": l.nomenclature.name, "nomenclature_id": l.nomenclature_id,
            "serial": l.asset_instance.serial_number if l.asset_instance else "",
            "asset_mode": l.asset_mode,
            "location": l.location.code if l.location else "",
            "location_id": l.location_id,
            "required_qty": l.required_qty, "scanned_qty": l.scanned_qty,
            "status": l.status,
        })
    if t.status == "sent":
        t.status = "in_progress"
        db.commit()
    return {"ok": True, "id": t.id, "number": t.number, "status": t.status,
            "notes": t.notes, "lines": lines}


@router.post("/scan")
def scan(req: ScanReq, request: Request, db: Session = Depends(get_db)):
    user = _terminal_user(request, db)
    if not user:
        return {"ok": False, "result": "error", "error": "Сессия истекла, войдите заново"}
    try:
        res = process_scan(db, req.task_id, req.code, qty=req.qty,
                           device_id=req.device_id, user_id=user.id,
                           current_location_id=req.current_location_id)
        return {"ok": True, **res}
    except ScanError as e:
        return {"ok": False, "result": "error", "error": e.reason,
                "expected": e.expected, "got": e.got}


class QuickReturnReq(BaseModel):
    item_id: int
    location_code: str


@router.post("/quick_return")
def quick_return(req: QuickReturnReq, request: Request, db: Session = Depends(get_db)):
    """Быстрый возврат на склад вне задания (скан выданной позиции + место)."""
    user = _terminal_user(request, db)
    if not user:
        return {"ok": False, "error": "Не авторизован"}
    ii = db.get(IssuedItem, req.item_id)
    if not ii or ii.status != "open":
        return {"ok": False, "error": "Позиция не найдена или уже закрыта"}
    from ..models import Location, StockByLocation, Barcode
    loc = db.query(Location).filter(Location.code == req.location_code).first()
    if not loc and req.location_code.startswith("WMS:LOC:"):
        loc = db.get(Location, int(req.location_code.split(":")[2]))
    if not loc:
        return {"ok": False, "error": "Место хранения не найдено"}
    ii.status = "closed"
    ii.closed_at = datetime.utcnow()
    if ii.asset_instance_id:
        a = db.get(AssetInstance, ii.asset_instance_id)
        if a:
            a.status = "in_stock"
            a.employee_id = None
            a.returned_at = datetime.utcnow()
            a.location_id = loc.id
    stock = db.query(StockByLocation).filter_by(nomenclature_id=ii.nomenclature_id,
                                                location_id=loc.id).first()
    if not stock:
        stock = StockByLocation(nomenclature_id=ii.nomenclature_id, location_id=loc.id, qty_stock=0)
        db.add(stock)
    if not ii.asset_instance_id:
        stock.qty_stock += ii.qty
    db.commit()
    return {"ok": True, "message": "Возврат выполнен"}


@router.get("/my_issued")
def my_issued(request: Request, db: Session = Depends(get_db)):
    """Что числится за текущим пользователем (для быстрого возврата)."""
    user = _terminal_user(request, db)
    if not user:
        return {"ok": False, "error": "Не авторизован"}
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        return {"ok": True, "items": []}
    items = db.query(IssuedItem).filter(IssuedItem.employee_id == emp.id,
                                        IssuedItem.status == "open").all()
    out = []
    for it in items:
        serial = it.asset_instance.serial_number if it.asset_instance else ""
        out.append({"id": it.id, "nomenclature": it.nomenclature.name, "qty": it.qty,
                    "serial": serial, "issued_at": it.issued_at.isoformat() if it.issued_at else ""})
    return {"ok": True, "items": out}
