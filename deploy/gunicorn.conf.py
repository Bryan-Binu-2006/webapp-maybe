# ============================================================================
# Gunicorn Configuration for CertIssuer
# ============================================================================
# Usage:
#     gunicorn -c deploy/gunicorn.conf.py wsgi:application
#
# WHY these settings?
# - workers = (2 × CPU cores) + 1 is a good baseline for I/O-bound apps.
# - bind to localhost:8000 because Nginx handles external connections.
# - timeout = 120 gives time for large batch generation.
# - accesslog/errorlog go to stdout so systemd/journalctl captures them.
# ============================================================================

import os

# ── Bind address ────────────────────────────────────────────────────
# Only listen on localhost — Nginx will proxy from port 80/443.
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# ── Workers ─────────────────────────────────────────────────────────
# More workers = more concurrent requests, but more memory.
# t2.micro default: 2 workers keeps memory usage predictable.
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))

# Small thread pool improves throughput for short I/O waits.
threads = int(os.environ.get("GUNICORN_THREADS", "2"))

# ── Worker class ────────────────────────────────────────────────────
# 'sync' is the default and simplest.  Good for this app since
# certificate generation is CPU-bound (Pillow), not async I/O.
worker_class = "sync"

# ── Timeout ─────────────────────────────────────────────────────────
# Seconds before a worker is killed and restarted.
# 120s allows batch generation of up to 300 certificates.
timeout = 120
graceful_timeout = 30
keepalive = 5

# ── Logging ─────────────────────────────────────────────────────────
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True

# Worker recycling limits long-running memory growth.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# ── Security ────────────────────────────────────────────────────────
# Limit request sizes at the Gunicorn level too (defence in depth).
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# ── Preload ─────────────────────────────────────────────────────────
# Preload the app before forking workers.  Saves memory via
# copy-on-write and catches startup errors early.
preload_app = True

# Use shared memory for temporary worker files when available.
worker_tmp_dir = "/dev/shm"
