"""
wsgi.py — Gunicorn entry point
================================
Gunicorn imports the 'application' object from this module.

Usage:
    gunicorn wsgi:application --bind 0.0.0.0:8000 --workers 3

WHY a separate wsgi.py?
- Gunicorn needs a module-level WSGI callable.
- Keeping it separate from app.py avoids running the dev
  server accidentally in production.
"""

import os
from app.app import create_app

# Use production config by default when running via Gunicorn
config_name = os.environ.get("FLASK_ENV", "production")
application = create_app(config_name)
