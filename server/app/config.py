"""Конфигурация WMS-сервера.

По умолчанию работает на SQLite (для быстрой разработки без PostgreSQL).
Для боевого развертывания задайте переменную окружения DATABASE_URL, например:
    DATABASE_URL=postgresql+psycopg2://wms:wms@localhost:5432/wms
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("WMS_DATABASE_URL", "sqlite:///" + os.path.join(DATA_DIR, "wms.db"))

SECRET_KEY = os.environ.get("WMS_SECRET_KEY", "change-me-in-production-0123456789abcdef")
SESSION_COOKIE_NAME = "wms_session"
SESSION_MAX_AGE = 12 * 3600  # 12 часов

APP_TITLE = "WMS Управление складом"
APP_VERSION = "0.1.0"

HOST = os.environ.get("WMS_HOST", "0.0.0.0")
PORT = int(os.environ.get("WMS_PORT", "8000"))
