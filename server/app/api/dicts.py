"""Веб-CRUD: Номенклатура (+вкладки карточки, QR, штрихкоды, фото), Единицы измерения."""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Nomenclature, Unit, Barcode, AssetInstance, StockByLocation, Box,
                      IssuedItem, StockMovement, Location)
from ..services.qr import make_qr_data, qr_png_bytes
from .web import templates, require_role, redir_login
from ..crud import parse_form

router = APIRouter(tags=["dicts"])

ROLE = ("admin", "controller")


def _units(db):
    return db.query(Unit).order_by(Unit.code).all()


# ------------------------------------------------------------------ список
@router.get("/nomenclature", response_class=HTMLResponse)
def nomenclature_list(request: Request, q: str = "", typ: str = "", only_active: str = "",
                      sort: str = "name", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    query = db.query(Nomenclature)
    if q:
        like = f"%{q}%"
        query = query.filter((Nomenclature.name.ilike(like)) | (Nomenclature.sku.ilike(like)))
    if typ in ("consumable", "asset"):
        query = query.filter(Nomenclature.type == typ)
    if only_active:
        query = query.filter(Nomenclature.is_active == True)  # noqa: E712
    col = {"name": Nomenclature.name, "sku": Nomenclature.sku, "type": Nomenclature.type}.get(
        sort, Nomenclature.name)
    items = query.order_by(col).all()
    return templates.TemplateResponse(request, "nomenclature_list.html", {
        "user": u, "items": items, "q": q, "typ": typ,
        "only_active": only_active, "sort": sort, "app_title": "WMS Управление складом",
        "active": "nomenclature"})


# ------------------------------------------------------------------ карточка с вкладками
@router.get("/nomenclature/{nid}", response_class=HTMLResponse)
def nomenclature_card(request: Request, nid: int, tab: str = "main", msg: str = "",
                      db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    n = db.get(Nomenclature, nid)
    if not n:
        return RedirectResponse("/nomenclature", status_code=303)
    ctx = {"request": request, "user": u, "n": n, "tab": tab, "msg": msg,
           "app_title": "WMS Управление складом", "active": "nomenclature",
           "units": _units(db),
           "cells": db.query(Location).filter(Location.type == "cell").order_by(Location.code).all()}
    if tab == "stock":
        rows = (db.query(StockByLocation).filter_by(nomenclature_id=nid)
                .order_by(StockByLocation.qty_stock.desc()).all())
        stock_wh = sum(r.qty_stock for r in rows)
        reserved = sum(r.qty_reserved for r in rows)
        in_work = sum(it.qty for it in db.query(IssuedItem).filter_by(
            nomenclature_id=nid, status="open").all())
        instats = db.query(AssetInstance).filter_by(nomenclature_id=nid).all()
        ctx.update({"rows": rows, "stock_wh": stock_wh, "reserved": reserved,
                    "in_work": in_work, "free": stock_wh - reserved, "instances": instats})
    elif tab == "barcodes":
        ctx["codes"] = (db.query(Barcode).filter_by(entity_type="nomenclature", entity_id=nid)
                        .order_by(Barcode.code).all())
    elif tab == "photo":
        ctx["boxes"] = db.query(Box).filter_by(nomenclature_id=nid).count()
    elif tab == "history":
        ctx["moves"] = (db.query(StockMovement).filter_by(nomenclature_id=nid)
                        .order_by(StockMovement.created_at.desc()).limit(200).all())
    return templates.TemplateResponse(request, "nomenclature_card.html", ctx)


# ------------------------------------------------------------------ создание/редактирование
@router.get("/nomenclature/new/form", response_class=HTMLResponse)
def nomenclature_new(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    return templates.TemplateResponse(request, "nomenclature_form.html", {
        "user": u, "n": None, "form": {}, "error": "",
        "units": _units(db), "app_title": "WMS Управление складом", "active": "nomenclature"})


@router.post("/nomenclature/save")
async def nomenclature_save(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    nid = int(f.get("id") or 0)
    err = ""
    name, sku = f.get("name", ""), f.get("sku", "")
    if not name or not sku:
        err = "Заполните наименование и артикул"
    dup = db.query(Nomenclature).filter(Nomenclature.sku == sku).first()
    if not err and dup and dup.id != nid:
        err = f"Артикул «{sku}» уже используется"
    if err:
        return templates.TemplateResponse(request, "nomenclature_form.html", {
            "user": u, "n": db.get(Nomenclature, nid) if nid else None,
            "form": f, "error": err, "units": _units(db),
            "app_title": "WMS Управление складом", "active": "nomenclature"}, status_code=400)
    obj = db.get(Nomenclature, nid) if nid else Nomenclature()
    obj.name, obj.sku = name, sku
    obj.type = f.get("type", "consumable")
    obj.unit_id = int(f["unit_id"]) if f.get("unit_id") else None
    obj.description = f.get("description", "")
    obj.is_active = f.get("is_active") == "on"
    obj.updated_at = datetime.utcnow()
    if not nid:
        db.add(obj)
    db.commit()
    return RedirectResponse(f"/nomenclature/{obj.id}", status_code=303)


@router.get("/nomenclature/{nid}/edit", response_class=HTMLResponse)
def nomenclature_edit(request: Request, nid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    n = db.get(Nomenclature, nid)
    if not n:
        return RedirectResponse("/nomenclature", status_code=303)
    return templates.TemplateResponse(request, "nomenclature_form.html", {
        "user": u, "n": n, "form": {}, "error": "",
        "units": _units(db), "app_title": "WMS Управление складом", "active": "nomenclature"})


@router.post("/nomenclature/{nid}/delete")
def nomenclature_delete(request: Request, nid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    n = db.get(Nomenclature, nid)
    if n:
        if db.query(StockMovement).filter_by(nomenclature_id=nid).first():
            n.is_active = False  # есть движения — только пометить неактивной
        else:
            db.query(Barcode).filter_by(entity_type="nomenclature", entity_id=nid).delete()
            db.delete(n)
    db.commit()
    return RedirectResponse("/nomenclature", status_code=303)


# ------------------------------------------------------------------ QR
@router.get("/nomenclature/{nid}/qr.png")
def nomenclature_qr(request: Request, nid: int, dl: int = 0,
                    db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    n = db.get(Nomenclature, nid)
    if not n:
        return Response(status_code=404)
    png = qr_png_bytes(make_qr_data("ITEM", nid), box_size=8,
                       caption=f"{n.sku} · {n.name[:36]}")
    disp = "attachment" if dl else "inline"
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f"{disp}; filename=WMS_ITEM_{nid}.png"})


# ------------------------------------------------------------------ штрихкоды
@router.post("/nomenclature/{nid}/barcode/add")
async def barcode_add(request: Request, nid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    code = f.get("code", "").strip()
    msg = ""
    if code:
        if db.query(Barcode).filter(Barcode.code == code).first():
            msg = f"Штрихкод {code} уже привязан к другому объекту"
        else:
            db.add(Barcode(code=code, entity_type="nomenclature", entity_id=nid))
            db.commit()
    return RedirectResponse(f"/nomenclature/{nid}?tab=barcodes", status_code=303)


@router.post("/barcode/{bc_id}/delete")
def barcode_delete(request: Request, bc_id: int, back: str = "/nomenclature",
                   db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    bc = db.get(Barcode, bc_id)
    dest = f"/nomenclature/{bc.entity_id}?tab=barcodes" if bc and bc.entity_type == "nomenclature" else back
    if bc:
        db.delete(bc)
        db.commit()
    return RedirectResponse(dest, status_code=303)


# ------------------------------------------------------------------ фото
@router.post("/nomenclature/{nid}/photo")
async def nomenclature_photo(request: Request, nid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    form = await request.form()
    file = form.get("photo")
    if file is not None and hasattr(file, "read"):
        content = await file.read()
        if content:
            from ..config import UPLOAD_DIR
            ext = os.path.splitext(file.filename or "")[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                ext = ".jpg"
            fname = f"nom_{nid}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
            with open(os.path.join(UPLOAD_DIR, fname), "wb") as fh:
                fh.write(content)
            n = db.get(Nomenclature, nid)
            if n:
                n.photo_path = "/uploads/" + fname
                db.commit()
    return RedirectResponse(f"/nomenclature/{nid}?tab=photo", status_code=303)


# ------------------------------------------------------------------ экземпляры оборудования
@router.post("/nomenclature/{nid}/instance/add")
async def instance_add(request: Request, nid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    sn = f.get("serial_number", "").strip()
    if sn and not db.query(AssetInstance).filter(AssetInstance.serial_number == sn).first():
        loc_id = int(f["location_id"]) if f.get("location_id") else None
        db.add(AssetInstance(nomenclature_id=nid, serial_number=sn,
                             internal_code=f.get("internal_code", "").strip(),
                             location_id=loc_id))
        db.commit()
    return RedirectResponse(f"/nomenclature/{nid}?tab=stock", status_code=303)


# ------------------------------------------------------------------ единицы измерения
@router.get("/units", response_class=HTMLResponse)
def units_page(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    items = _units(db)
    return templates.TemplateResponse(request, "units.html", {
        "user": u, "items": items,
        "counts": {un.id: db.query(Nomenclature).filter_by(unit_id=un.id).count()
                   for un in items},
        "app_title": "WMS Управление складом", "active": "units"})


@router.post("/units/save")
async def units_save(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    f = await parse_form(request)
    uid = int(f.get("id") or 0)
    code, name = f.get("code", "").upper(), f.get("name", "")
    if code and name:
        dup = db.query(Unit).filter(Unit.code == code).first()
        if not (dup and dup.id != uid):
            obj = db.get(Unit, uid) if uid else Unit()
            obj.code, obj.name = code, name
            if not uid:
                db.add(obj)
            db.commit()
    return RedirectResponse("/units", status_code=303)


@router.post("/units/{uid}/delete")
def units_delete(request: Request, uid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    if not db.query(Nomenclature).filter_by(unit_id=uid).first():
        un = db.get(Unit, uid)
        if un:
            db.delete(un)
            db.commit()
    return RedirectResponse("/units", status_code=303)
