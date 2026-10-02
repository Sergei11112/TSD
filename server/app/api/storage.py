"""Веб-CRUD: Места хранения (иерархия), Коробки, Остатки."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Location, Box, Nomenclature, StockByLocation, AssetInstance,
                      IssuedItem, Employee)
from ..services.qr import make_qr_data, qr_png_bytes
from .web import templates, require_role, redir_login
from ..crud import parse_form, num, full_path

router = APIRouter(tags=["storage"])
ROLE = ("admin", "controller")
LOC_TYPES = {"warehouse": "Склад", "rack": "Стеллаж", "shelf": "Полка", "cell": "Ячейка"}


def _tree(db: Session):
    """Все места, сгруппированные по parent_id."""
    locs = db.query(Location).order_by(Location.code).all()
    by_parent: dict[int | None, list] = {}
    for l in locs:
        by_parent.setdefault(l.parent_id, []).append(l)
    return locs, by_parent


# ------------------------------------------------------------------ дерево мест
@router.get("/locations", response_class=HTMLResponse)
def locations_page(request: Request, sel: int | None = None, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    locs, by_parent = _tree(db)
    roots = by_parent.get(None, [])
    selected = db.get(Location, sel) if sel else (roots[0] if roots else None)
    # что лежит в выбранном месте (и вложенных)
    stock_rows, assets, boxes_list = [], [], []
    if selected:
        ids = _descendant_ids(selected, by_parent)
        stock_rows = (db.query(StockByLocation, Nomenclature, Location)
                      .join(Nomenclature, Nomenclature.id == StockByLocation.nomenclature_id)
                      .join(Location, Location.id == StockByLocation.location_id)
                      .filter(StockByLocation.location_id.in_(ids))
                      .filter(StockByLocation.qty_stock > 0)
                      .order_by(Nomenclature.name).all())
        boxes_list = (db.query(Box, Nomenclature)
                      .join(Nomenclature, Nomenclature.id == Box.nomenclature_id)
                      .filter(Box.location_id.in_(ids), Box.is_active == True)  # noqa: E712
                      .order_by(Box.code).all())
        assets = (db.query(AssetInstance, Nomenclature)
                  .join(Nomenclature, Nomenclature.id == AssetInstance.nomenclature_id)
                  .filter(AssetInstance.location_id.in_(ids)).all())
    parents = {l.id: l.parent_id for l in locs}
    return templates.TemplateResponse("locations.html", {
        "request": request, "user": u, "roots": roots, "by_parent": by_parent,
        "selected": selected, "stock_rows": stock_rows, "boxes_list": boxes_list,
        "assets": assets, "loc_types": LOC_TYPES, "parents": parents,
        "all_locs": locs, "path": full_path(selected) if selected else "",
        "app_title": "WMS Управление складом", "active": "locations"})


def _descendant_ids(loc: Location, by_parent) -> list[int]:
    ids = [loc.id]
    for ch in by_parent.get(loc.id, []):
        ids.extend(_descendant_ids(ch, by_parent))
    return ids


@router.post("/locations/save")
async def locations_save(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    lid = int(f.get("id") or 0)
    code = f.get("code", "").strip()
    name = f.get("name", "").strip()
    err = ""
    if not code or not name:
        err = "Заполните код и наименование"
    dup = db.query(Location).filter(Location.code == code).first()
    if not err and dup and dup.id != lid:
        err = f"Код «{code}» уже используется"
    if err:
        return RedirectResponse(f"/locations?error={err}", status_code=303)
    obj = db.get(Location, lid) if lid else Location()
    obj.code, obj.name = code, name
    obj.type = f.get("type", "cell")
    pid = f.get("parent_id")
    obj.parent_id = int(pid) if pid else None
    obj.is_active = f.get("is_active", "on") == "on"
    if not lid:
        obj.qr_code = ""  # заполним после flush
        db.add(obj)
        db.flush()
    obj.qr_code = make_qr_data("LOC", obj.id)
    db.commit()
    return RedirectResponse(f"/locations?sel={obj.id}", status_code=303)


@router.post("/locations/{lid}/delete")
def locations_delete(request: Request, lid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    loc = db.get(Location, lid)
    if loc:
        has_children = db.query(Location.id).filter(Location.parent_id == lid).first()
        has_stock = db.query(StockByLocation.id).filter(StockByLocation.location_id == lid,
                                                        StockByLocation.qty_stock > 0).first()
        has_boxes = db.query(Box.id).filter(Box.location_id == lid).first()
        if has_children or has_stock or has_boxes:
            loc.is_active = False  # занято — только деактивировать
        else:
            db.delete(loc)
        db.commit()
    return RedirectResponse("/locations", status_code=303)


@router.get("/locations/{lid}/qr.png")
def location_qr(request: Request, lid: int, dl: int = 0, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    loc = db.get(Location, lid)
    if not loc:
        return Response(status_code=404)
    png = qr_png_bytes(make_qr_data("LOC", lid), box_size=8,
                       caption=f"{loc.code} · {loc.name[:30]}")
    disp = "attachment" if dl else "inline"
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f"{disp}; filename=WMS_LOC_{lid}.png"})


# ------------------------------------------------------------------ коробки
@router.get("/boxes", response_class=HTMLResponse)
def boxes_page(request: Request, q: str = "", loc_id: int | None = None,
               db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    query = db.query(Box).join(Nomenclature, Nomenclature.id == Box.nomenclature_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Box.code.ilike(like)) | (Nomenclature.name.ilike(like)))
    if loc_id:
        query = query.filter(Box.location_id == loc_id)
    items = query.order_by(Box.code).all()
    cells = db.query(Location).filter(Location.type == "cell").order_by(Location.code).all()
    noms = db.query(Nomenclature).filter(Nomenclature.is_active == True).order_by(Nomenclature.name).all()  # noqa: E712
    edit = db.get(Box, int(q)) if q.isdigit() else None
    return templates.TemplateResponse("boxes.html", {
        "request": request, "user": u, "items": items, "q": "" if edit else q,
        "cells": cells, "noms": noms, "edit": edit, "loc_id": loc_id or "",
        "app_title": "WMS Управление складом", "active": "boxes"})


@router.get("/boxes/{bid}", response_class=HTMLResponse)
def box_card_page(request: Request, bid: int, db: Session = Depends(get_db)):
    return boxes_page(request, q=str(bid), db=db)


@router.post("/boxes/save")
async def boxes_save(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    bid = int(f.get("id") or 0)
    code = f.get("code", "").strip()
    qty = max(0.0, num(f.get("current_qty"), 0))
    nom_id = int(f["nomenclature_id"]) if f.get("nomenclature_id") else None
    loc_id = int(f["location_id"]) if f.get("location_id") else None
    err = ""
    if not code or not nom_id:
        err = "Укажите код коробки и номенклатуру"
    dup = db.query(Box).filter(Box.code == code).first()
    if not err and dup and dup.id != bid:
        err = f"Код коробки «{code}» уже существует"
    if err:
        return RedirectResponse(f"/boxes?error={err}", status_code=303)
    box = db.get(Box, bid) if bid else Box()
    old_loc, old_qty = box.location_id, box.current_qty
    box.code, box.nomenclature_id, box.location_id = code, nom_id, loc_id
    box.current_qty = qty
    box.is_active = f.get("is_active", "on") == "on"
    if not bid:
        db.add(box)
        db.flush()
    box.qr_code = make_qr_data("BOX", box.id)
    # синхронизация остатков стеллажа при изменении/создании
    if loc_id:
        delta = qty - (old_qty if bid else 0)
        if bid and old_loc != loc_id:
            _adjust(db, box.nomenclature_id, old_loc, -old_qty)
            delta = qty
        elif bid:
            pass
        _adjust(db, box.nomenclature_id, loc_id, delta)
    elif bid and old_loc:
        _adjust(db, box.nomenclature_id, old_loc, -old_qty)
    db.commit()
    return RedirectResponse(f"/boxes?q={box.id}&ok=1", status_code=303)


def _adjust(db, nom_id, loc_id, delta):
    if not loc_id or abs(delta) < 1e-9:
        return
    row = db.query(StockByLocation).filter_by(nomenclature_id=nom_id,
                                              location_id=loc_id).first()
    if not row:
        row = StockByLocation(nomenclature_id=nom_id, location_id=loc_id, qty_stock=0)
        db.add(row)
        db.flush()
    row.qty_stock = max(0.0, row.qty_stock + delta)


@router.get("/boxes/{bid}/qr.png")
def box_qr(request: Request, bid: int, dl: int = 0, db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    b = db.get(Box, bid)
    if not b:
        return Response(status_code=404)
    png = qr_png_bytes(make_qr_data("BOX", bid), box_size=8,
                       caption=f"{b.code} · {b.nomenclature.name[:30]}")
    disp = "attachment" if dl else "inline"
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f"{disp}; filename=WMS_BOX_{bid}.png"})


@router.post("/boxes/{bid}/qty")
async def box_qty(request: Request, bid: int, db: Session = Depends(get_db)):
    """Быстрое изменение количества в коробке (корректировка контролёром)."""
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    f = await parse_form(request)
    b = db.get(Box, bid)
    if b:
        new_qty = max(0.0, num(f.get("current_qty"), b.current_qty))
        _adjust(db, b.nomenclature_id, b.location_id, new_qty - b.current_qty)
        b.current_qty = new_qty
        db.commit()
    return RedirectResponse(f"/boxes?q={bid}&ok=1", status_code=303)


@router.post("/boxes/{bid}/delete")
def box_delete(request: Request, bid: int, db: Session = Depends(get_db)):
    u = require_role(request, db, ("admin",))
    if not u:
        return redir_login()
    b = db.get(Box, bid)
    if b:
        _adjust(db, b.nomenclature_id, b.location_id, -b.current_qty)
        b.is_active = False
        b.current_qty = 0
        db.commit()
    return RedirectResponse("/boxes", status_code=303)


# ------------------------------------------------------------------ остатки
@router.get("/stock", response_class=HTMLResponse)
def stock_page(request: Request, typ: str = "", loc_id: int | None = None, q: str = "",
               sort: str = "name", db: Session = Depends(get_db)):
    u = require_role(request, db, ROLE)
    if not u:
        return redir_login()
    noms = db.query(Nomenclature).filter(Nomenclature.is_active == True)  # noqa: E712
    if typ in ("consumable", "asset"):
        noms = noms.filter(Nomenclature.type == typ)
    if q:
        like = f"%{q}%"
        noms = noms.filter((Nomenclature.name.ilike(like)) | (Nomenclature.sku.ilike(like)))
    noms = noms.all()
    loc_filter = None
    if loc_id:
        _, by_parent = _tree(db)
        sel = db.get(Location, loc_id)
        if sel:
            loc_filter = set(_descendant_ids(sel, by_parent))
    rows = []
    stock_all = db.query(StockByLocation).all()
    issued_open = db.query(IssuedItem).filter(IssuedItem.status == "open").all()
    inst_map: dict[int, dict] = {}
    for a in db.query(AssetInstance).all():
        st = inst_map.setdefault(a.nomenclature_id, {"in_stock": 0, "issued": 0,
                                                     "repair": 0, "written_off": 0})
        st[a.status] = st.get(a.status, 0) + 1
    for n in noms:
        srows = [r for r in stock_all if r.nomenclature_id == n.id
                 and (not loc_filter or r.location_id in loc_filter)]
        on_wh = sum(r.qty_stock for r in srows)
        reserved = sum(r.qty_reserved for r in srows)
        inst = inst_map.get(n.id)
        if n.type == "asset":
            total = sum(inst.values()) if inst else 0
            in_work = inst.get("issued", 0) if inst else 0
            on_wh_disp = inst.get("in_stock", 0) if inst else on_wh
        else:
            in_work = sum(i.qty for i in issued_open if i.nomenclature_id == n.id)
            total = on_wh + in_work
            on_wh_disp = on_wh
        if total == 0 and on_wh == 0 and in_work == 0:
            continue
        rows.append({"n": n, "total": total, "wh": on_wh_disp, "work": in_work,
                     "reserved": reserved, "free": on_wh_disp - reserved})
    key = {"name": lambda r: r["n"].name, "sku": lambda r: r["n"].sku,
           "total": lambda r: -r["total"], "wh": lambda r: -r["wh"]}.get(sort)
    if key:
        rows.sort(key=key)
    cells = db.query(Location).filter(Location.type == "warehouse").order_by(Location.code).all()
    _, by_parent = _tree(db)
    all_locs = db.query(Location).order_by(Location.code).all()
    return templates.TemplateResponse("stock.html", {
        "request": request, "user": u, "rows": rows, "typ": typ, "q": q, "sort": sort,
        "loc_id": loc_id or "", "warehouses": all_locs, "by_parent": by_parent,
        "loc_name": db.get(Location, loc_id).name if loc_id else "",
        "app_title": "WMS Управление складом", "active": "stock"})
