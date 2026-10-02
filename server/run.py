#!/usr/bin/env python3
"""Запуск WMS-сервера: python run.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uvicorn
from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
