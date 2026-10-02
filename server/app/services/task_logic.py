"""Бизнес-логика заданий: создание, сканирование (защита от дурaка), проведение документов."""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Task, TaskLine, TaskScan, Document, StockMovement, Nomenclature, AssetInstance,
    Box, Location, StockByLocation, IssuedItem, Employee, User, Barcode,
)

DOC_PREFIX = {
    "ISSUE": "ВЫД",
    "WRITEOFF": "СПИ",
    "RETURN": "ВРН",
    "MOVE": "ПЕР",
}


class ScanError(Exception):
    """Ошибка валидации сканирования с пояснением 'ожидалось/получено'."""

    def __init__(self, reason: str, expected: str = "", got: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.expected = expected
        self.got = got


def next_doc_number(db: Session, doc_type: str) -> str:
    year = datetime.utcnow().year
    prefix = f"{DOC_PREFIX.get(doc_type, 'ДОК')}-{year}-"
    count = db.query(func.count(Document.id)).filter(Document.number.like(prefix + "%")).scalar() or 0
    while True:
        count += 1
        number = f"{prefix}{count:06d}"
        if not db.query(Document.id).filter(Document.number == number).first():
            return number


def next_task_number(db: Session) -> str:
    year = datetime.utcnow().year
    prefix = f"ЗАД-{year}-"
    count = db.query(func.count(Task.id)).filter(Task.number.like(prefix + "%")).scalar() or 0
    while True:
        count += 1
        number = f"{prefix}{count:06d}"
        if not db.query(Task.id).filter(Task.number == number).first():
            return number


# ---------------------------------------------------------------- resolution of scanned codes

def resolve_code(db: Session, code: str):
    """Возвращает (entity_type, entity) по коду: QR (WMS:ITEM/BOX/LOC) или заводской штрихкод."""
    code = code.strip()
    if code.startswith("WMS:"):
        parts = code.split(":")
        if len(parts) == 3:
            kind, sid = parts[1], parts[2]
            try:
                oid = int(sid)
            except ValueError:
                raise ScanError("Некорректный QR-код", got=code)
            if kind == "ITEM":
                obj = db.get(Nomenclature, oid)
                if not obj:
                    raise ScanError("Номенклатура не найдена в системе", got=code)
                return "nomenclature", obj
            if kind == "BOX":
                obj = db.get(Box, oid)
                if not obj:
                    raise ScanError("Коробка не найдена в системе", got=code)
                return "box", obj
            if kind == "LOC":
                obj = db.get(Location, oid)
                if not obj:
                    raise ScanError("Место хранения не найдено", got=code)
                return "location", obj
        raise ScanError("Неизвестный формат QR-кода", got=code)
    # заводской штрихкод
    bc = db.query(Barcode).filter(Barcode.code == code).first()
    if bc:
        if bc.entity_type == "nomenclature":
            obj = db.get(Nomenclature, bc.entity_id)
            if obj:
                return "nomenclature", obj
        elif bc.entity_type == "asset_instance":
            obj = db.get(AssetInstance, bc.entity_id)
            if obj:
                return "asset", obj
    ai = db.query(AssetInstance).filter(AssetInstance.serial_number == code).first()
    if ai:
        return "asset", ai
    ai = db.query(AssetInstance).filter(AssetInstance.internal_code == code).first()
    if ai:
        return "asset", ai
    bx = db.query(Box).filter(Box.code == code).first()
    if bx:
        return "box", bx
    loc = db.query(Location).filter(Location.code == code).first()
    if loc:
        return "location", loc
    raise ScanError("Код не найден в системе", got=code)


# ---------------------------------------------------------------- scan validation ("anti-fool")

def process_scan(db: Session, task_id: int, code: str, qty: float | None = None,
                 device_id: str = "", user_id: int | None = None,
                 current_location_id: int | None = None) -> dict:
    """Обработка сканирования на ТСД с полной защитой от дурака.

    Текущее место задаётся отдельным сканом локации (адресное хранение:
    сначала скан места, затем товара/коробки). Возвращает dict с результатом.
    Бросает ScanError при любой ошибке валидации.
    """
    task = db.get(Task, task_id)
    if not task:
        raise ScanError("Задание не найдено")
    # 8. Задание не завершено
    if task.status in ("completed", "cancelled"):
        raise ScanError(f"Задание {task.number} уже завершено/отменено")

    etype, entity = resolve_code(db, code)

    if etype == "location":
        # Скан места хранения — запоминаем как текущее
        _log_scan(db, task, None, code, "ok", "", device_id, user_id)
        return {"result": "location_ok", "location_id": entity.id,
                "location_name": f"{entity.code} {entity.name}"}

    # Ищем подходящую незакрытую строку задания
    candidate_lines = [l for l in task.lines if l.status != "completed"]
    matched_line = None
    for line in candidate_lines:
        if _line_matches(line, etype, entity):
            matched_line = line
            break
    if matched_line is None:
        expected_desc = _expected_summary(task)
        _log_scan(db, task, None, code, "error", "Код не относится к заданию", device_id, user_id)
        raise ScanError("Код не относится к данному заданию",
                        expected=expected_desc, got=_describe(etype, entity))

    line = matched_line

    # 3. Код относится к нужному месту (для операций со склада)
    location_required = line.action_type in ("ISSUE_CONSUMABLE", "DIRECT_WRITEOFF", "RETURN_ASSET", "RETURN_CONSUMABLE")
    if line.location_id and location_required:
        if current_location_id is None:
            _log_scan(db, task, line.id, code, "error", "Сначала отсканируйте место хранения", device_id, user_id)
            raise ScanError("Адресное хранение: сначала отсканируйте место хранения (ячейку)",
                            expected=f"место {line.location.code}", got="место не задано")
        if current_location_id != line.location_id:
            _log_scan(db, task, line.id, code, "error", "Сканирование не в том месте", device_id, user_id)
            cur = db.get(Location, current_location_id)
            raise ScanError("Отсканировано не то место хранения",
                            expected=f"место {line.location.code} ({line.location.name})",
                            got=f"место {cur.code if cur else current_location_id}")

    # Валидация по типу операции
    scan_qty = qty if qty is not None else 1.0

    if etype == "asset":
        _validate_asset(db, task, line, entity)
    elif etype == "box":
        _validate_box(db, line, entity, scan_qty)
    elif etype == "nomenclature":
        # скан номенклатуры без коробок допустим только для расходников any-режима
        if line.nomenclature_id != entity.id:
            raise ScanError("Номенклатура не соответствует строке задания",
                            expected=line.nomenclature.name, got=entity.name)

    # 4. Не превышено количество
    remaining = line.required_qty - line.scanned_qty
    if scan_qty > remaining + 1e-9:
        _log_scan(db, task, line.id, code, "error", "Превышение количества", device_id, user_id)
        raise ScanError("Превышено требуемое количество",
                        expected=f"осталось {remaining:g}", got=f"отсканировано {scan_qty:g}")

    # Применяем скан
    applied = _apply_scan(db, task, line, etype, entity, scan_qty)

    # Частичное выполнение запрещено: строка закрывается только когда scanned==required
    if abs(line.scanned_qty - line.required_qty) < 1e-9:
        line.status = "completed"
    _log_scan(db, task, line.id, code, "ok", "", device_id, user_id)

    all_done = all(l.status == "completed" for l in task.lines)
    if all_done and task.status != "completed":
        task.status = "in_progress"  # ensure
        post_task_document(db, task, user_id)

    db.commit()
    db.refresh(line)
    return {
        "result": "ok",
        "action_type": line.action_type,
        "line_id": line.id,
        "nomenclature": line.nomenclature.name,
        "scanned_qty": line.scanned_qty,
        "required_qty": line.required_qty,
        "line_status": line.status,
        "task_status": db.get(Task, task_id).status,
        "applied": applied,
    }


def _validate_asset(db: Session, task: Task, line: TaskLine, asset: AssetInstance):
    if line.asset_mode == "specific":
        if line.asset_instance_id != asset.id:
            raise ScanError("Отсканирован не тот экземпляр оборудования",
                            expected=f"экземпляр {line.asset_instance.serial_number if line.asset_instance else '?'}",
                            got=f"экземпляр {asset.serial_number}")
    else:
        if asset.nomenclature_id != line.nomenclature_id:
            raise ScanError("Оборудование другой номенклатуры",
                            expected=line.nomenclature.name, got=asset.nomenclature.name)
    # 5/6. Повтор и доступность
    if line.action_type == "ISSUE_ASSET":
        if asset.status == "issued":
            raise ScanError("Экземпляр уже выдан", got=f"серийный {asset.serial_number}")
        if asset.status == "written_off":
            raise ScanError("Экземпляр списан")
        already = db.query(IssuedItem).filter(
            IssuedItem.asset_instance_id == asset.id, IssuedItem.status == "open").first()
        if already:
            raise ScanError("Этот экземпляр уже числится выданным",
                            got=f"серийный {asset.serial_number}")
    if line.action_type == "RETURN_ASSET":
        # 7. Возврат только тем, кто брал
        issued = db.query(IssuedItem).filter(
            IssuedItem.asset_instance_id == asset.id,
            IssuedItem.status == "open").first()
        if not issued:
            raise ScanError("Экземпляр не числится выданным",
                            got=f"серийный {asset.serial_number}")
        if task.employee_id and issued.employee_id != task.employee_id:
            emp = db.get(Employee, issued.employee_id)
            raise ScanError("Возврат возможен только тем сотрудником, который получал",
                            expected=f"выдан сотруднику: {emp.full_name if emp else '?'}",
                            got=f"возвращает: {task.employee.full_name if task.employee else '?'}")
    if line.action_type == "FINAL_WRITEOFF":
        issued = db.query(IssuedItem).filter(
            IssuedItem.asset_instance_id == asset.id,
            IssuedItem.status == "open").first()
        if not issued:
            raise ScanError("Списываемый экземпляр не числится в работе")


def _validate_box(db: Session, line: TaskLine, box: Box, qty: float):
    if box.nomenclature_id != line.nomenclature_id:
        raise ScanError("В коробке другая номенклатура",
                        expected=line.nomenclature.name, got=box.nomenclature.name)
    if line.location_id and box.location_id and box.location_id != line.location_id:
        loc = db.get(Location, box.location_id)
        raise ScanError("Коробка находится в другом месте хранения",
                        expected=line.location.code, got=loc.code if loc else str(box.location_id))
    if qty > box.current_qty + 1e-9:
        raise ScanError("В коробке меньше товара, чем указано",
                        expected=f"не более {box.current_qty:g}", got=f"указано {qty:g}")


def _apply_scan(db: Session, task: Task, line: TaskLine, etype: str, entity, qty: float) -> str:
    line.scanned_qty = (line.scanned_qty or 0) + qty
    at = line.action_type

    if at == "ISSUE_ASSET":
        asset = entity
        asset.status = "issued"
        asset.employee_id = task.employee_id
        asset.issued_at = datetime.utcnow()
        db.add(IssuedItem(employee_id=task.employee_id, nomenclature_id=asset.nomenclature_id,
                          asset_instance_id=asset.id, qty=1))
        if line.asset_instance_id is None:
            line.asset_instance_id = asset.id
        return "asset_issued"

    if at == "RETURN_ASSET":
        asset = entity
        ii = db.query(IssuedItem).filter(IssuedItem.asset_instance_id == asset.id,
                                         IssuedItem.status == "open").first()
        if ii:
            ii.status = "closed"
            ii.closed_at = datetime.utcnow()
        asset.status = "in_stock"
        asset.employee_id = None
        asset.returned_at = datetime.utcnow()
        if line.location_id:
            asset.location_id = line.location_id
        return "asset_returned"

    if at == "ISSUE_CONSUMABLE":
        if etype == "box":
            entity.current_qty -= qty
            if entity.location_id:
                _stock_change(db, line.nomenclature_id, entity.location_id, -qty)
        db.add(IssuedItem(employee_id=task.employee_id, nomenclature_id=line.nomenclature_id,
                          qty=qty))
        return "consumable_issued"

    if at == "RETURN_CONSUMABLE":
        # закрыть открытые выдачи сотрудника
        open_items = db.query(IssuedItem).filter(
            IssuedItem.employee_id == task.employee_id,
            IssuedItem.nomenclature_id == line.nomenclature_id,
            IssuedItem.asset_instance_id.is_(None),
            IssuedItem.status == "open").all()
        left = qty
        for it in open_items:
            take = min(it.qty, left)
            it.qty -= take
            left -= take
            if it.qty <= 1e-9:
                it.status = "closed"
                it.closed_at = datetime.utcnow()
            if left <= 1e-9:
                break
        if line.location_id:
            _stock_change(db, line.nomenclature_id, line.location_id, qty)
        return "consumable_returned"

    if at == "DIRECT_WRITEOFF":
        if etype == "box":
            entity.current_qty -= qty
        if line.location_id:
            _stock_change(db, line.nomenclature_id, line.location_id, -qty)
        return "direct_writeoff"

    if at == "FINAL_WRITEOFF":
        if etype == "asset":
            asset = entity
            ii = db.query(IssuedItem).filter(IssuedItem.asset_instance_id == asset.id,
                                             IssuedItem.status == "open").first()
            if ii:
                ii.status = "closed"
                ii.closed_at = datetime.utcnow()
            asset.status = "written_off"
        else:
            items = db.query(IssuedItem).filter(
                IssuedItem.employee_id == task.employee_id,
                IssuedItem.nomenclature_id == line.nomenclature_id,
                IssuedItem.asset_instance_id.is_(None),
                IssuedItem.status == "open").all()
            left = qty
            for it in items:
                take = min(it.qty, left)
                it.qty -= take
                left -= take
                if it.qty <= 1e-9:
                    it.status = "closed"
                    it.closed_at = datetime.utcnow()
                if left <= 1e-9:
                    break
        return "final_writeoff"

    return "recorded"


def _stock_change(db: Session, nom_id: int, loc_id: int, delta: float):
    row = db.query(StockByLocation).filter_by(nomenclature_id=nom_id, location_id=loc_id).first()
    if not row:
        row = StockByLocation(nomenclature_id=nom_id, location_id=loc_id, qty_stock=0)
        db.add(row)
        db.flush()
    row.qty_stock += delta
    if row.qty_stock < -1e-9:
        row.qty_stock = 0


def _line_matches(line: TaskLine, etype: str, entity) -> bool:
    if etype == "nomenclature":
        return line.nomenclature_id == entity.id and etype != "location"
    if etype == "box":
        return line.nomenclature_id == entity.nomenclature_id
    if etype == "asset":
        if line.nomenclature_id != entity.nomenclature_id:
            return False
        if line.asset_mode == "specific":
            return line.asset_instance_id == entity.id
        return True
    return False


def _describe(etype: str, entity) -> str:
    if etype == "asset":
        return f"экземпляр {entity.serial_number}"
    if etype == "box":
        return f"коробка {entity.code} ({entity.nomenclature.name})"
    return f"номенклатура {entity.name}"


def _expected_summary(task: Task) -> str:
    parts = []
    for l in task.lines:
        if l.status == "completed":
            continue
        d = l.nomenclature.name
        if l.asset_mode == "specific" and l.asset_instance:
            d += f" [{l.asset_instance.serial_number}]"
        parts.append(d)
    return "ожидался один из ТМЦ: " + ("; ".join(parts) if parts else "—")


def _log_scan(db: Session, task: Task, line_id, code, result, reason, device_id, user_id):
    db.add(TaskScan(task_id=task.id, task_line_id=line_id, scanned_code=code,
                    result=result, error_reason=reason, device_id=device_id, user_id=user_id))


# ---------------------------------------------------------------- posting documents

ACTION_TO_DOC = {
    "ISSUE_ASSET": "ISSUE",
    "ISSUE_CONSUMABLE": "ISSUE",
    "RETURN_ASSET": "RETURN",
    "RETURN_CONSUMABLE": "RETURN",
    "FINAL_WRITEOFF": "WRITEOFF",
    "DIRECT_WRITEOFF": "WRITEOFF",
}

ACTION_TO_MOVEMENT = {
    "ISSUE_ASSET": "ISSUE",
    "ISSUE_CONSUMABLE": "ISSUE",
    "RETURN_ASSET": "RETURN",
    "RETURN_CONSUMABLE": "RETURN",
    "FINAL_WRITEOFF": "WRITEOFF",
    "DIRECT_WRITEOFF": "WRITEOFF",
}


def post_task_document(db: Session, task: Task, user_id: int | None = None):
    """Автоматическое проведение документов по завершённому заданию.

    Создаёт по одному документу на тип операции (выдача/возврат/списание),
    фиксирует движения ТМЦ. Изменения остатков уже применены в _apply_scan.
    """
    now = datetime.utcnow()
    groups: dict[str, list[TaskLine]] = {}
    for line in task.lines:
        if line.status != "completed":
            continue
        doc_type = ACTION_TO_DOC.get(line.action_type, "MOVE")
        groups.setdefault(doc_type, []).append(line)

    for doc_type, lines in groups.items():
        doc = Document(number=next_doc_number(db, doc_type), type=doc_type,
                       task_id=task.id, status="posted", created_by=user_id,
                       created_at=now, posted_at=now)
        db.add(doc)
        db.flush()
        for line in lines:
            db.add(StockMovement(
                document_id=doc.id, nomenclature_id=line.nomenclature_id,
                asset_instance_id=line.asset_instance_id, location_id=line.location_id,
                employee_id=task.employee_id, qty=line.scanned_qty,
                movement_type=ACTION_TO_MOVEMENT[line.action_type], created_at=now))
            # привязать выданные позиции к документу
            for ii in db.query(IssuedItem).filter_by(document_id=None).all():
                if ii.nomenclature_id == line.nomenclature_id and ii.status in ("open", "closed"):
                    ii.document_id = doc.id

    task.status = "completed"
    task.completed_at = now


def cancel_document(db: Session, doc: Document, user: User):
    """Отмена документа (только admin). Прямая отмена движений не выполняется —
    фиксируется статус отменён; корректировка остатков — задача контролёра (2-й этап)."""
    doc.status = "cancelled"
    db.commit()
