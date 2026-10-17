# LivresEnClasse.com — Classroom Library Management

[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/flask-3.0-lightgrey.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-green.svg)](LICENSE.md)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Testing](https://img.shields.io/badge/tests-pytest-yellow.svg)](project/test/)

[Version française](README.md)

**LivresEnClasse.com** (Bibliothèque-Flask) is a web application designed specifically for teachers to easily manage their classroom library, track student book loans, and enrich their catalog using barcode scanning.

---

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Local Quickstart](#local-quickstart)
- [Technical Documentation](#technical-documentation)
- [Code Quality & Tests](#code-quality--tests)
- [License](#license)

---

## Key Features

- **Barcode scanning & multi-API enrichment**: Instant recognition via webcam/smartphone (HTML5-QRCode) with fallback search across the **Bibliothèque nationale de France (BnF SRU Dublin Core)**, **Google Books**, and **Open Library**.
- **Student & loan management**: One-click loans and returns, reading history, overdue book indicators.
- **Classroom tools & printing**: Generation of printable vector barcode sheets and themed storage bin labels.
- **Freemium SaaS Model & Stripe**: Free quotas (40 students, 500 books, 30 scans/week), 30-day trial period, lifetime Founder status, and unlimited Premium subscription powered by Stripe Checkout and the Stripe Customer Portal.
- **Multilingual & International SEO**: Full support for French 🇫🇷, English 🇬🇧, and German 🇩🇪 with dedicated URLs (`/fr/`, `/en/`, `/de/`) and `hreflang` tags.
- **Security & Privacy**: Secure authentication (Werkzeug/Scrypt), anti-bot & anti-spam protection (hCaptcha), strict data isolation per teacher, and no data destruction policy.

---

## Tech Stack

- **Backend**: Python 3.12, Flask 3, Flask-Login, Flask-WTF, Flask-Babel 4
- **ORM & Database**: SQLAlchemy, Flask-Migrate (Alembic), SQLite (stored in `instance/db.sqlite`)
- **Frontend**: Jinja2, Semantic HTML5, Responsive CSS3 (fluid design system), Vanilla JavaScript
- **Production & Containerization**: Gunicorn, Traefik (reverse proxy & Let's Encrypt TLS), Authelia (2FA /admin), Docker Compose, Cloudflare Tunnel

---

## Local Quickstart

To launch the project in a local development environment in 5 steps:

```bash
# 1. Clone the repository and enter the directory
git clone https://github.com/Forestierr/Bibliotheque-Flask.git
cd Bibliotheque-Flask

# 2. Create and activate a Python 3.12 virtual environment
python -m venv venv
# On Linux / macOS: source venv/bin/activate
# On Windows (PowerShell): .\venv\Scripts\Activate.ps1

# 3. Install application and tooling dependencies
pip install --upgrade pip
pip install -r project/requirements.txt
pip install ruff pytest

# 4. Set up environment variables
cp .env.example .env

# 5. Apply database migrations and run the development server
export FLASK_APP=project   # Windows PowerShell: $env:FLASK_APP="project"
flask db upgrade
flask run -p 5000 -h 127.0.0.1
```

Then visit the application in your browser at: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

> **Camera / HTTPS Note:** Modern browsers restrict webcam access to secure contexts (HTTPS or localhost). To test barcode scanning on a mobile device connected to your local network, launch the server with:
> ```bash
> flask run -p 5000 -h 0.0.0.0 --cert adhoc
> ```

---

## Technical Documentation

To delve deeper into the architecture, deployment, and maintenance of the project, consult the detailed guides in the [`/docs`](docs/) directory:

| Document | Description |
| :--- | :--- |
| [**Software Architecture**](docs/architecture.md) | 11 Blueprints modular design, Mermaid HTTP request lifecycle, Jinja2 filters, middlewares, and multi-worker scheduler. |
| [**Database**](docs/base-de-donnees.md) | Complete Entity-Relationship diagram (`erDiagram`), detail of the 9 tables, Alembic migrations management, and SQLite backup strategy. |
| [**Production Deployment**](docs/deploiement.md) | Step-by-step guide for production servers, Traefik stack, Authelia, Cloudflare Tunnel, GHCR images, and data persistence. |
| [**External APIs & Integrations**](docs/apis-externes.md) | Specifications for BnF SRU (Dublin Core), Google Books, Open Library queries, Stripe webhooks, and hCaptcha (including BnF legal obligations). |
| [**Configuration & Environment**](docs/configuration.md) | Comprehensive dictionary of `.env` variables, pricing constants (`config_plans.py`), session cookies, and environment flags. |
| [**Operations & Maintenance**](docs/maintenance.md) | CLI script utilities (`scripts/`), manual quota management, Founder account administration, and common troubleshooting. |

---

## Code Quality & Tests

The project enforces automated validation checks on GitHub Actions ([`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)):

- **Formatting & Linting**:
  ```bash
  ruff format project/
  ruff check project/
  ```
- **Automated Tests**:
  ```bash
  pytest project/test/
  ```
- **Internationalization (i18n)**:  
  Before committing changes affecting localized text, compiled binary `.mo` files must be updated:
  ```bash
  pybabel compile -d project/translations
  ```

See [**CONTRIBUTING.md**](CONTRIBUTING.md) for full contribution guidelines.

---

## License

This project is licensed under the **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)** (Source-Available) — see [LICENSE.md](LICENSE.md).

- **Permitted**: Personal, educational, classroom, academic use, and non-commercial open-source contributions.
- **Prohibited**: Commercial exploitation, direct/indirect monetization, reselling, or competing SaaS hosting without prior written consent.
