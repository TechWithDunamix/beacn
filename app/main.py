"""ASGI entry point:  uvicorn app.main:app --port 8000"""

from __future__ import annotations

from app.bootstrap import create_app

app = create_app()
