#!/usr/bin/env python3
"""Инициализация БД и демо-данных. Запуск: python scripts/init_db.py [--reset]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    User, Employee, Unit, Nomenclature, AssetInstance, Barcode, Location, Box,
    StockByLocation,
)
from app.services.auth import hash_password, hash_pin  # noqa: E402
from app.services.qr import make_qr_data  # noqa: E402

UNITS = [("шт", "Штука"), ("кг", "Килограмм"), ("м", "Метр"), ("уп", "Упаковка"),
         ("л", "Литр"), ("компл", "Комплект"), ("пара", "Пара"), ("рулон", "Рулон"),
         ("коробка", "Коробка")]


def reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        if db.query(User).count():
            print("БД уже содержит данные — пропускаю (используйте --reset для пересоздания).")
            return

        # Пользователи
        admin = User(username="admin", full_name="Администратор системы", role="admin",
                     password_hash=hash_password("admin123"), pin_code=hash_pin("0000"))
        ctrl = User(username="controller", full_name="Контролёров И.П.", role="controller",
                    password_hash=hash_password("ctrl123"), pin_code=hash_pin("1111"))
        w1 = User(username="ivanov", full_name="Иванов С.С.", role="worker",
                  password_hash=hash_password("work123"), pin_code=hash_pin("1234"))
        w2 = User(username="petrov", full_name="Петров А.А.", role="worker",
                  password_hash=hash_password("work123"), pin_code=hash_pin("2345"))
        db.add_all([admin, ctrl, w1, w2])
        db.flush()

        # Сотрудники
        e1 = Employee(full_name="Иванов С.С.", position="Электрик", department="Ремонтная служба",
                      user_id=w1.id)
        e2 = Employee(full_name="Петров А.А.", position="Наладчик", department="Цех №1",
                      user_id=w2.id)
        e3 = Employee(full_name="Сидоров В.В.", position="Сварщик", department="Цех №2")
        db.add_all([e1, e2, e3])
        db.flush()

        # Единицы измерения
        units = {}
        for code, name in UNITS:
            u = Unit(code=code, name=name)
            db.add(u)
            units[code] = u
        db.flush()

        # Номенклатура
        nom_data = [
            ("Дрель Bosch GSB 13 RE", "NOM-0001", "asset", "шт"),
            ("Перфоратор Makita HR2470", "NOM-0002", "asset", "шт"),
            ("Мультиметр Fluke 117", "NOM-0003", "asset", "шт"),
            ("Изолента ПВХ синяя", "NOM-0004", "consumable", "рулон"),
            ("Кабель ВВГнг 3х2.5", "NOM-0005", "consumable", "м"),
            ("Перчатки х/б с ПВХ", "NOM-0006", "consumable", "пара"),
            ("Болт М8х40 оцинк.", "NOM-0007", "consumable", "шт"),
            ("Краска эмаль ПФ-115 серая", "NOM-0008", "consumable", "л"),
        ]
        noms = {}
        for name, sku, tp, unit in nom_data:
            n = Nomenclature(name=name, sku=sku, type=tp, unit_id=units[unit].id,
                             description="")
            db.add(n)
            db.flush()
            n.photo_path = ""
            noms[sku] = n
            db.add(Barcode(code=f"BC{abs(hash(sku)) % 10**12}", entity_type="nomenclature",
                           entity_id=n.id))

        # Экземпляры оборудования
        assets = [
            (noms["NOM-0001"], "SN-BOSCH-0001", "ИНВ-000001"),
            (noms["NOM-0001"], "SN-BOSCH-0002", "ИНВ-000002"),
            (noms["NOM-0002"], "SN-MAKITA-0001", "ИНВ-000003"),
            (noms["NOM-0003"], "SN-FLUKE-0001", "ИНВ-000004"),
        ]
        for nom, sn, inv in assets:
            a = AssetInstance(nomenclature_id=nom.id, serial_number=sn, internal_code=inv,
                              status="in_stock")
            db.add(a)
            db.flush()
            db.add(Barcode(code=sn, entity_type="asset_instance", entity_id=a.id))

        # Места хранения: Склад → Стеллаж → Полка → Ячейка
        wh = Location(code="WH01", name="Основной склад", type="warehouse")
        db.add(wh); db.flush(); wh.qr_code = make_qr_data("LOC", wh.id)
        rack = Location(code="WH01-A", name="Стеллаж A", type="rack", parent_id=wh.id)
        db.add(rack); db.flush(); rack.qr_code = make_qr_data("LOC", rack.id)
        shelf = Location(code="WH01-A-1", name="Полка 1", type="shelf", parent_id=rack.id)
        db.add(shelf); db.flush(); shelf.qr_code = make_qr_data("LOC", shelf.id)
        cells = []
        for i in range(1, 5):
            c = Location(code=f"WH01-A-1-{i}", name=f"Ячейка 1-{i}", type="cell",
                         parent_id=shelf.id)
            db.add(c); db.flush(); c.qr_code = make_qr_data("LOC", c.id)
            cells.append(c)
        rack2 = Location(code="WH01-B", name="Стеллаж B (оборудование)", type="rack",
                         parent_id=wh.id)
        db.add(rack2); db.flush(); rack2.qr_code = make_qr_data("LOC", rack2.id)
        cell_b = Location(code="WH01-B-1", name="Ячейка оборудования", type="cell",
                          parent_id=rack2.id)
        db.add(cell_b); db.flush(); cell_b.qr_code = make_qr_data("LOC", cell_b.id)

        # Коробки + остатки
        box_specs = [
            ("BOX-0001", noms["NOM-0004"], cells[0], 50),
            ("BOX-0002", noms["NOM-0005"], cells[1], 120),
            ("BOX-0003", noms["NOM-0006"], cells[2], 30),
            ("BOX-0004", noms["NOM-0007"], cells[2], 500),
            ("BOX-0005", noms["NOM-0008"], cells[3], 20),
        ]
        for code, nom, loc, qty in box_specs:
            b = Box(code=code, nomenclature_id=nom.id, location_id=loc.id, current_qty=qty)
            db.add(b); db.flush(); b.qr_code = make_qr_data("BOX", b.id)
            st = StockByLocation(nomenclature_id=nom.id, location_id=loc.id, qty_stock=qty)
            db.add(st)
        db.commit()
        print("Демо-данные созданы:")
        print("  admin/admin123 (PIN 0000)")
        print("  controller/ctrl123 (PIN 1111)")
        print("  ivanov/work123 (PIN 1234), petrov/work123 (PIN 2345)")
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        print("Сброс схемы БД...")
        reset()
    else:
        Base.metadata.create_all(bind=engine)
    seed()
