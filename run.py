"""
run.py — Development entry point
==================================
Run from the project root:
    python run.py
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env file BEFORE importing the app

from app.app import create_app

application = create_app("development")
application.run(host="127.0.0.1", port=5000, debug=True)
