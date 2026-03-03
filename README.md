# CertIssuer — Secure Certificate Generation Web App

A production-ready Flask application for generating, managing, and verifying certificates.

## Architecture

```
Browser → Nginx (port 80/443) → Gunicorn (port 8000) → Flask → PostgreSQL
                                                              → Local filesystem
```

## Features

- **User authentication** — Register, login, logout with bcrypt password hashing
- **Certificate generation** — Upload a PNG template + Excel of names → batch-generate certificates
- **Text placement** — Configure position (x, y), font size, and colour
- **Verification system** — Each certificate gets a unique UUID; anyone can verify at `/verify/<uuid>`
- **Secure by default** — CSRF protection, session security, input validation, ownership checks

## Project Structure

```
├── app/
│   ├── config.py            # All configuration (env vars)
│   ├── app.py               # Flask application factory
│   ├── models/
│   │   ├── database.py      # SQLAlchemy instance
│   │   ├── user.py          # User model (bcrypt passwords)
│   │   └── certificate.py   # CertificateBatch & Certificate models
│   ├── routes/
│   │   ├── auth.py          # Register, login, logout
│   │   ├── certificates.py  # Upload, configure, generate, download
│   │   └── verify.py        # Public verification endpoint
│   ├── utils/
│   │   ├── security.py      # login_required decorator, ownership checks
│   │   ├── file_helpers.py  # Safe file handling, MIME validation
│   │   ├── excel_helpers.py # Excel column extraction
│   │   ├── image_helpers.py # Pillow-based certificate rendering
│   │   └── logging_config.py
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS
├── deploy/
│   ├── nginx.conf           # Nginx reverse proxy config
│   ├── gunicorn.conf.py     # Gunicorn WSGI server config
│   ├── certissuer.service   # systemd service file
│   └── setup.sh             # EC2 setup script
├── wsgi.py                  # Gunicorn entry point
├── requirements.txt
├── .env.example
└── .gitignore
```

## Local Development

### Prerequisites

- Python 3.10+
- PostgreSQL running locally

### Setup

```bash
# 1. Clone the repo
git clone <your-repo> certissuer
cd certissuer

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create PostgreSQL database
psql -U postgres -c "CREATE USER certapp WITH PASSWORD 'certapp';"
psql -U postgres -c "CREATE DATABASE certapp OWNER certapp;"

# 5. Copy env file
cp .env.example .env

# 6. Run
python app/app.py
```

Visit `http://127.0.0.1:5000`

### Running with Gunicorn (Linux/Mac)

```bash
gunicorn -c deploy/gunicorn.conf.py wsgi:application
```

## EC2 Deployment

```bash
# On a fresh Ubuntu EC2 instance:
sudo chmod +x deploy/setup.sh
sudo APP_DOMAIN=your-domain.com LETSENCRYPT_EMAIL=you@example.com ./deploy/setup.sh
```

The script now provisions PostgreSQL credentials, runtime secrets, systemd, Nginx, and Let's Encrypt HTTPS automatically.

## Security Features

| Feature | Implementation | Risk Prevented |
|---------|---------------|----------------|
| Password hashing | bcrypt (12 rounds) | Credential theft |
| Session cookies | HttpOnly, Secure, SameSite=Strict | XSS, CSRF, sniffing |
| CSRF tokens | Flask-WTF CSRFProtect | Cross-site request forgery |
| File validation | Extension + magic bytes | Malicious file upload |
| UUID filenames | Generated server-side | Path traversal |
| Ownership checks | Every route validates user_id | Horizontal privilege escalation |
| Input validation | Server-side, all endpoints | Injection, DoS |
| Error handling | Custom handlers, no stack traces | Information leakage |
| Parameterised queries | SQLAlchemy ORM | SQL injection |
| Template autoescaping | Jinja2 default | Reflected XSS |

## Database Schema

- **users** — id (UUID), username, password_hash, created_at
- **certificate_batches** — id (UUID), user_id (FK), template_filename, created_at
- **certificates** — id (UUID), batch_id (FK), user_id (FK), participant_name, file_path, verification_code (UUID), created_at

## Configuration

All settings are controlled via environment variables. See `.env.example` for the full list.

## License

MIT
