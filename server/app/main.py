"""FastAPI-приложение WMS. Запуск: python -m app  (из каталога server) или run.py."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_TITLE, APP_VERSION, STATIC_DIR, UPLOAD_DIR
from .database import Base, engine
from .api import web, terminal
from .services.task_logic import ScanError

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.exception_handler(ScanError)
async def scan_error_handler(request: Request, exc: ScanError):
    return JSONResponse(status_code=400, content={"ok": False, "error": exc.reason,
                                                  "expected": exc.expected, "got": exc.got})


app.include_router(web.router)
app.include_router(terminal.router)

from .api import dicts, storage, ops  # noqa: E402

app.include_router(dicts.router)
app.include_router(storage.router)
app.include_router(ops.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": APP_TITLE, "version": APP_VERSION}
