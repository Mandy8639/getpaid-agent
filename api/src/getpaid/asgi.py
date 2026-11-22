"""ASGI entry point: `uvicorn getpaid.asgi:app`. Built from settings at import time."""

from getpaid.main import _app_from_settings

app = _app_from_settings()
