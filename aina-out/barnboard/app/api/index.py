"""Vercel serverless entrypoint — exposes the FastAPI ASGI app.

Vercel's @vercel/python runtime serves the module-level `app` object. Templates
and static files are bundled via `includeFiles` in vercel.json; the SQLite DB
lives in /tmp (ephemeral) so this is a self-reseeding demo, not a stateful host.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.main import app  # noqa: E402  (ASGI app served by Vercel)
