"""
models/database.py — SQLAlchemy database instance
==================================================
We create the SQLAlchemy object here in its own module so that
models, routes, and the app factory can all import it without
circular-import issues.
"""

from flask_sqlalchemy import SQLAlchemy

# This object is initialised with the Flask app later via db.init_app(app).
db = SQLAlchemy()
