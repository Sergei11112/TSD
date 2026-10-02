"""Веб-интерфейс: Сотрудники, Задания (создание/отправка/мониторинг), Документы, Отчёты."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Employee, User, Task, TaskLine, TaskScan, Document, StockMovement,
                      Nomenclature, Location, AssetInstance, Box, IssuedItem,
                      StockByLocation)
from .web import templates, require_role, redir_login
from ..crud import parse_form, num
from ..services.task_logic import next_task_number

router = APIRouter(tags=["ops"])
ROLE = ("admin", "controller")

ACTION_NAMES = {
    "ISSUE_ASSET": "Выдача оборудования",
    "ISSUE_CONSUMABLE": "Выдача расходника",
    "RETURN_ASSET": "Возврат оборудования",
    "RETURN_CONSUMABLE": "Возврат расходника",
    "FINAL_WRITEOFF": "Финальное списание (в работе)",
    "DIRECT_WRITEOFF": "Прямое списание со склада",
}
DOC_TYPE_NAMES = {"ISSUE": "Выдача", "RETURN": "Возврат", "WRITEOFF": "Списание", "MOVE": "Перемещение"}
STATUS_NAMES = {"draft": "Черновик", "sent": "Отправлено", "in_progress": "В работе",
                "completed": "Выполнено", "cancelled": "Отменено", "posted": "Проведён",
                "pending": "Ожидает", "error": "Ошибка"}


def _cells(db):
    return db.query(Location).filter(Location.type == "cell").order_by(Location.code).all()


# ================================================================== сотрудники
@router.get("/employees", response_class=HTMLResponse)
def employees_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    query = db.query(Employee)
    if q:
        query = query.filter(Employee.full_name.ilike(f"%{q}%"))
    emps = query.order_by(Employee.full_name).all()
    open_items = db.query(IssuedItem).filter(IssuedItem.status == "open").all()
    per_emp: dict[int, list] = {}
    for it in open_items:
        per_emp.setdefault(it.employee_id, []).append(it)
    edit = None
    if q.isdigit():
        edit = db.get(Employee, int(q))
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("employees.html", {
        "request": request, "user": u, "items": emps, "per_emp": per_emp,
        "q": "" if edit else q, "edit": edit, "users": users,
        "app_title": "WMS Управление складом", "active": "employees"})


@router.post("/employees/save")
async def employees_save(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    eid = int(f.get("id") or 0)
    name = f.get("full_name", "").strip()
    if name:
        obj = db.get(Employee, eid) if eid else Employee()
        obj.full_name = name
        obj.position = f.get("position", "")
        obj.department = f.get("department", "")
        obj.is_active = f.get("is_active", "on") == "on"
        uid = f.get("user_id")
        obj.user_id = int(uid) if uid else None
        if not eid:
            db.add(obj)
        db.commit()
    return RedirectResponse("/employees", status_code=303)


@router.get("/employees/{eid}/card", response_class=HTMLResponse)
def employee_card(request: Request, eid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    emp = db.get(Employee, eid)
    if not emp:
        return RedirectResponse("/employees", status_code=303)
    open_items = (db.query(IssuedItem).filter_by(employee_id=eid, status="open")
                  .order_by(IssuedItem.issued_at.desc()).all())
    history = (db.query(StockMovement).filter_by(employee_id=eid)
               .order_by(StockMovement.created_at.desc()).limit(300).all())
    assets = db.query(AssetInstance).filter_by(employee_id=eid, status="issued").all()
    return templates.TemplateResponse("employee_card.html", {
        "request": request, "user": u, "emp": emp, "open_items": open_items,
        "history": history, "assets": assets,
        "app_title": "WMS Управление складом", "active": "employees"})


# ================================================================== задания
@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, status: str = "", q: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    query = db.query(Task)
    if status in STATUS_NAMES:
        query = query.filter(Task.status == status)
    if q:
        query = query.filter((Task.number.ilike(f"%{q}%")) | (Task.notes.ilike(f"%{q}%")))
    tasks = query.order_by(Task.created_at.desc()).limit(300).all()
    return templates.TemplateResponse("tasks.html", {
        "request": request, "user": u, "items": tasks, "status": status, "q": q,
        "status_names": STATUS_NAMES, "app_title": "WMS Управление складом",
        "active": "tasks"})


@router.get("/tasks/new", response_class=HTMLResponse)
def task_new(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    return _task_form_ctx(request, u, db, new=True)


@router.get("/tasks/{tid}/edit", response_class=HTMLResponse)
def task_edit(request: Request, tid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    t = db.get(Task, tid)
    if not t or t.status not in ("draft",):
        return RedirectResponse(f"/tasks/{tid}", status_code=303)
    return _task_form_ctx(request, u, db, new=False, task=t)


def _task_form_ctx(request, u, db, new=True, task=None):
    emps = db.query(Employee).filter(Employee.is_active == True) \
        .order_by(Employee.full_name).all()  # noqa: E712
    noms = db.query(Nomenclature).filter(Nomenclature.is_active == True) \
        .order_by(Nomenclature.name).all()  # noqa: E712
    return templates.TemplateResponse("task_form.html", {
        "request": request, "user": u, "task": task, "employees": emps, "noms": noms,
        "cells": _cells(db), "actions": ACTION_NAMES, "assets": db.query(AssetInstance)
        .order_by(AssetInstance.serial_number).all(),
        "boxes": db.query(Box).filter(Box.is_active == True).order_by(Box.code).all(),  # noqa: E712
        "app_title": "WMS Управление складом", "active": "tasks"})


@router.post("/tasks/save")
async def task_save(request: Request, send: str = "", back_url: str = "/tasks",
                    db: Session = Depends(get_db)):
    """Сохранение задания; строки табличной части приходят как tl_* списки (одинаковой длины)."""
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    form = await request.form()
    tid = int(form.get("id") or 0)
    task = db.get(Task, tid) if tid else Task(number=next_task_number(db))
    emp_id = form.get("employee_id")
    task.employee_id = int(emp_id) if emp_id else None
    task.notes = form.get("notes", "")
    task.type = "mixed"
    if not tid:
        task.created_by = u.id
        db.add(task)
        db.flush()
    # обновляем строки только для черновика
    if task.status == "draft":
        idx = 0
        while f"tl_action_{idx}" in form:
            action = form[f"tl_action_{idx}"]
            nom_id = form.get(f"tl_nom_{idx}")
            if action and nom_id:
                line_id = form.getlist("tl_line_id")[idx] if idx < len(form.getlist("tl_line_id")) else ""
                line = db.get(TaskLine, int(line_id)) if line_id else TaskLine(task_id=task.id)
                line.action_type = action
                line.nomenclature_id = int(nom_id)
                line.required_qty = max(0.0, num(form.get(f"tl_qty_{idx}"), 1))
                loc = form.get(f"tl_loc_{idx}")
                line.location_id = int(loc) if loc else None
                mode = form.get(f"tl_mode_{idx}") or "specific"
                line.asset_mode = mode
                ai = form.get(f"tl_asset_{idx}")
                line.asset_instance_id = int(ai) if ai and mode == "specific" else None
                bx = form.get(f"tl_box_{idx}")
                line.box_id = int(bx) if bx else None
                line.sort_order = idx
                if not line_id:
                    db.add(line)
            idx += 1
        # удалить снятые строки
        removed = form.get("removed_lines", "")
        for rid in [r for r in removed.split(",") if r.strip().isdigit()]:
            ln = db.get(TaskLine, int(rid))
            if ln and ln.task_id == task.id:
                db.delete(ln)
    if send == "1" and task.status == "draft":
        db.flush()
        db.refresh(task)
        if not task.lines:
            db.rollback()
            return RedirectResponse(f"/tasks?error=nolines", status_code=303)
        task.status = "sent"
        task.sent_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.post("/tasks/{tid}/cancel")
def task_cancel(request: Request, tid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    t = db.get(Task, tid)
    if t and t.status in ("draft", "sent", "in_progress"):
        t.status = "cancelled"
        db.commit()
    return RedirectResponse(f"/tasks/{tid}", status_code=303)


@router.post("/tasks/{tid}/send")
def task_send(request: Request, tid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    t = db.get(Task, tid)
    if t and t.status == "draft" and t.lines:
        t.status = "sent"
        t.sent_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/tasks/{tid}", status_code=303)


@router.get("/tasks/{tid}", response_class=HTMLResponse)
def task_detail(request: Request, tid: int, error: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    t = db.get(Task, tid)
    if not t:
        return RedirectResponse("/tasks", status_code=303)
    scans = (db.query(TaskScan).filter_by(task_id=tid)
             .order_by(TaskScan.created_at.desc()).limit(100).all())
    docs = db.query(Document).filter_by(task_id=tid).all()
    return templates.TemplateResponse("task_detail.html", {
        "request": request, "user": u, "t": t, "scans": scans, "docs": docs,
        "actions": ACTION_NAMES, "status_names": STATUS_NAMES, "error": error,
        "app_title": "WMS Управление складом", "active": "tasks"})


# ================================================================== документы
@router.get("/documents", response_class=HTMLResponse)
def documents_page(request: Request, typ: str = "", status: str = "", q: str = "",
                   db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    query = db.query(Document)
    if typ in DOC_TYPE_NAMES:
        query = query.filter(Document.type == typ)
    if status in ("draft", "posted", "cancelled"):
        query = query.filter(Document.status == status)
    if q:
        query = query.filter(Document.number.ilike(f"%{q}%"))
    docs = query.order_by(Document.created_at.desc()).limit(300).all()
    return templates.TemplateResponse("documents.html", {
        "request": request, "user": u, "items": docs, "typ": typ, "status": status,
        "q": q, "doc_types": DOC_TYPE_NAMES, "status_names": STATUS_NAMES,
        "app_title": "WMS Управление складом", "active": "documents"})


@router.get("/documents/{did}", response_class=HTMLResponse)
def document_detail(request: Request, did: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    doc = db.get(Document, did)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    moves = (db.query(StockMovement).filter_by(document_id=did)
             .order_by(StockMovement.id).all())
    return templates.TemplateResponse("document_detail.html", {
        "request": request, "user": u, "doc": doc, "moves": moves,
        "doc_types": DOC_TYPE_NAMES, "status_names": STATUS_NAMES,
        "app_title": "WMS Управление складом", "active": "documents"})


@router.post("/documents/{did}/cancel")
def document_cancel(request: Request, did: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    from ..services.task_logic import cancel_document
    doc = db.get(Document, did)
    if doc and doc.status == "posted":
        cancel_document(db, doc, u)
    return RedirectResponse(f"/documents/{did}", status_code=303)


# ================================================================== отчёты
@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, report: str = "movements",
                 date_from: str = "", date_to: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    ctx = {"request": request, "user": u, "report": report, "date_from": date_from,
           "date_to": date_to, "app_title": "WMS Управление складом", "active": "reports",
           "doc_types": DOC_TYPE_NAMES}
    df = _parse_date(date_from)
    dt = _parse_date(date_to, end=True)
    if report == "movements":
        q = db.query(StockMovement)
        if df:
            q = q.filter(StockMovement.created_at >= df)
        if dt:
            q = q.filter(StockMovement.created_at <= dt)
        ctx["moves"] = q.order_by(StockMovement.created_at.desc()).limit(500).all()
    elif report == "stock":
        ctx["rows"] = _stock_snapshot(db)
    elif report == "abc":
        since = datetime.utcnow() - timedelta(days=90)
        agg: dict[int, dict] = {}
        for m in db.query(StockMovement).filter(StockMovement.created_at >= since).all():
            a = agg.setdefault(m.nomenclature_id, {"cnt": 0, "vol": 0.0})
            a["cnt"] += 1
            a["vol"] += abs(m.qty)
        ranked = sorted(agg.items(), key=lambda kv: -(kv[1]["cnt"] * kv[1]["vol"]))
        total = sum(v["cnt"] for _, v in ranked) or 1
        abc_rows, cum = [], 0
        nom_cache = {n.id: n for n in db.query(Nomenclature).all()}
        for nid, v in ranked:
            cum += v["cnt"]
            group = "A" if cum <= total * 0.8 else ("B" if cum <= total * 0.95 else "C")
            n = nom_cache.get(nid)
            if n:
                abc_rows.append({"n": n, "cnt": v["cnt"], "vol": v["vol"], "group": group})
        ctx["abc_rows"] = abc_rows[:60]
    elif report == "errors":
        ctx["errs"] = (db.query(TaskScan).filter(TaskScan.result == "error")
                       .order_by(TaskScan.created_at.desc()).limit(300).all())
    elif report == "issued":
        q = db.query(IssuedItem)
        if df:
            q = q.filter(IssuedItem.issued_at >= df)
        if dt:
            q = q.filter(IssuedItem.issued_at <= dt)
        ctx["items"] = q.order_by(IssuedItem.issued_at.desc()).limit(500).all()
    else:
        ctx["todo"] = True
    return templates.TemplateResponse("reports.html", ctx)


def _parse_date(s: str, end: bool = False):
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d + timedelta(days=1) - timedelta(seconds=1) if end else d
    except ValueError:
        return None


def _stock_snapshot(db):
    rows = []
    stock_all = db.query(StockByLocation).all()
    issued_open = db.query(IssuedItem).filter(IssuedItem.status == "open").all()
    for n in db.query(Nomenclature).filter(Nomenclature.is_active == True).all():  # noqa: E712
        on_wh = sum(r.qty_stock for r in stock_all if r.nomenclature_id == n.id)
        in_work = sum(i.qty for i in issued_open if i.nomenclature_id == n.id)
        if on_wh or in_work:
            rows.append({"n": n, "wh": on_wh, "work": in_work, "total": on_wh + in_work})
    return rows
