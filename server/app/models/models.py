"""Все модели БД WMS (15 таблиц)."""
from datetime import datetime

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


# 1. users — Пользователи системы
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), default="")
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="worker")  # admin/controller/worker
    pin_code: Mapped[str] = mapped_column(String(8), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="user", uselist=False)


# 2. employees — Справочник сотрудников
class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), index=True)
    position: Mapped[str] = mapped_column(String(128), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="employee")


# 3. units — Единицы измерения
class Unit(Base):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(64))


# 4. nomenclature — Номенклатура
class Nomenclature(Base):
    __tablename__ = "nomenclature"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(16), default="consumable")  # consumable/asset
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    description: Mapped[str] = mapped_column(Text, default="")
    photo_path: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)

    unit = relationship("Unit")
    instances = relationship("AssetInstance", back_populates="nomenclature")


# 5. asset_instances — Экземпляры оборудования
class AssetInstance(Base):
    __tablename__ = "asset_instances"
    id: Mapped[int] = mapped_column(primary_key=True)
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    internal_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(16), default="in_stock", index=True)
    # in_stock / issued / repair / written_off
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    photo_path: Mapped[str] = mapped_column(String(256), default="")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    nomenclature = relationship("Nomenclature", back_populates="instances")
    employee = relationship("Employee")
    location = relationship("Location")


# 6. barcodes — Заводские штрихкоды
class Barcode(Base):
    __tablename__ = "barcodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # nomenclature/asset_instance
    entity_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_barcode_entity", "entity_type", "entity_id"),)


# 7. locations — Места хранения (иерархия)
class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16), default="cell")
    # warehouse/rack/shelf/cell
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    qr_code: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    parent = relationship("Location", remote_side=[id], backref="children")


# 8. boxes — Коробки с QR
class Box(Base):
    __tablename__ = "boxes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    qr_code: Mapped[str] = mapped_column(String(64), default="")
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    current_qty: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    nomenclature = relationship("Nomenclature")
    location = relationship("Location")


# 9. stock_by_location — Остатки по местам
class StockByLocation(Base):
    __tablename__ = "stock_by_location"
    id: Mapped[int] = mapped_column(primary_key=True)
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    qty_stock: Mapped[float] = mapped_column(Float, default=0.0)
    qty_reserved: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)

    nomenclature = relationship("Nomenclature")
    location = relationship("Location")

    __table_args__ = (UniqueConstraint("nomenclature_id", "location_id",
                                       name="uq_stock_nom_loc"),)


# 10. issued_items — Выданное в работу
class IssuedItem(Base):
    __tablename__ = "issued_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"), index=True)
    asset_instance_id: Mapped[int | None] = mapped_column(ForeignKey("asset_instances.id"), nullable=True)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open/closed
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    employee = relationship("Employee")
    nomenclature = relationship("Nomenclature")
    asset_instance = relationship("AssetInstance")


# 11. tasks — Задания для ТСД
class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32), default="mixed")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    # draft/sent/in_progress/completed/cancelled
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_device: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lines = relationship("TaskLine", back_populates="task", cascade="all, delete-orphan",
                         order_by="TaskLine.sort_order")
    employee = relationship("Employee")
    created_by_user = relationship("User")


# 12. task_lines — Строки заданий
class TaskLine(Base):
    __tablename__ = "task_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    # ISSUE_ASSET/ISSUE_CONSUMABLE/RETURN_ASSET/RETURN_CONSUMABLE/FINAL_WRITEOFF/DIRECT_WRITEOFF
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"))
    asset_instance_id: Mapped[int | None] = mapped_column(ForeignKey("asset_instances.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"), nullable=True)
    required_qty: Mapped[float] = mapped_column(Float, default=0.0)
    scanned_qty: Mapped[float] = mapped_column(Float, default=0.0)
    asset_mode: Mapped[str] = mapped_column(String(16), default="specific")  # specific/any
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/completed/error
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    task = relationship("Task", back_populates="lines")
    nomenclature = relationship("Nomenclature")
    asset_instance = relationship("AssetInstance")
    location = relationship("Location")
    box = relationship("Box")


# 13. task_scans — История сканирований
class TaskScan(Base):
    __tablename__ = "task_scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    task_line_id: Mapped[int | None] = mapped_column(ForeignKey("task_lines.id"), nullable=True)
    scanned_code: Mapped[str] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(16))  # ok/error
    error_reason: Mapped[str] = mapped_column(Text, default="")
    device_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task = relationship("Task")


# 14. documents — Проведенные документы
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32))  # ISSUE/WRITEOFF/RETURN/MOVE
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="posted")  # draft/posted/cancelled
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task = relationship("Task")


# 15. stock_movements — История движений
class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), index=True)
    nomenclature_id: Mapped[int] = mapped_column(ForeignKey("nomenclature.id"), index=True)
    asset_instance_id: Mapped[int | None] = mapped_column(ForeignKey("asset_instances.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    movement_type: Mapped[str] = mapped_column(String(16), index=True)
    # RECEIPT/ISSUE/RETURN/WRITEOFF/MOVE
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document = relationship("Document")
    nomenclature = relationship("Nomenclature")
    employee = relationship("Employee")
    location = relationship("Location")
