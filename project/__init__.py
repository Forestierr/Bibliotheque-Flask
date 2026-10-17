# init.py

import locale
import logging
import os
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    g,
    has_request_context,
    redirect,
    request,
    session,
    url_for,
)
from flask_babel import Babel, format_date, format_datetime
from flask_babel import get_locale as babel_get_locale
from flask_login import LoginManager, current_user
from flask_mail import Mail, Message  # noqa: F401
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from .email_error import MailCriticalHandler

# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()

mail = Mail()
csrf = CSRFProtect()
babel = Babel()

LANGUAGES = ["fr", "en", "de"]

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / ".env")

# logging configuration
# Définir le chemin du fichier de log
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Vérifier et créer le répertoire si nécessaire
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = "logs/app.log"
handler = RotatingFileHandler(LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=10)
handler.setLevel(logging.ERROR)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logging.getLogger().addHandler(handler)


def create_app(test_config=None):
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "SQLALCHEMY_DATABASE_URI", "sqlite:///db.sqlite"
    )

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = 465
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_USE_TLS"] = False
    app.config["MAIL_USE_SSL"] = True

    # Configuration de la durée et sécurité des sessions / cookies
    is_prod = os.getenv("FLASK_ENV") == "production"
    app.config["SESSION_COOKIE_SECURE"] = is_prod
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = is_prod
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
    app.config["REMEMBER_COOKIE_REFRESH_EACH_REQUEST"] = True

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    Migrate(app, db)
    mail.init_app(app)

    def get_locale():
        """Détermine la langue active : URL path (g.lang_code) > session > utilisateur connecté > navigateur > fr par défaut."""
        if not has_request_context():
            return "fr"
        if getattr(g, "lang_code", None) in LANGUAGES:
            return g.lang_code
        if "lang" in session and session["lang"] in LANGUAGES:
            return session["lang"]
        if current_user and current_user.is_authenticated:
            pref = getattr(current_user, "preferred_language", None)
            if pref in LANGUAGES:
                return pref
        return request.accept_languages.best_match(LANGUAGES, default="fr")

    babel.init_app(app, locale_selector=get_locale)

    OG_LOCALES = {
        "fr": "fr_FR",
        "en": "en_US",
        "de": "de_DE",
    }

    def lang_url(target_lang, external=False):
        """Génère l'URL canonique ou alternative dans la langue spécifiée."""
        if not has_request_context():
            return f"/{target_lang}/"
        endpoint = request.endpoint
        if not endpoint or endpoint == "static" or endpoint.startswith("core."):
            return url_for("main.index", lang_code=target_lang, _external=external)
        view_args = dict(request.view_args or {})
        view_args["lang_code"] = target_lang
        args = {k: v for k, v in request.args.items() if k != "lang"}
        args.update(view_args)
        args["_external"] = external
        try:
            return url_for(endpoint, **args)
        except Exception:  # noqa: BLE001
            parts = request.path.strip("/").split("/")
            if parts and parts[0] in LANGUAGES:
                parts[0] = target_lang
                new_path = "/" + "/".join(parts)
            else:
                new_path = f"/{target_lang}{request.path}"
            if external:
                base = request.host_url.rstrip("/")
                return f"{base}{new_path}"
            return new_path

    # Rend get_locale, languages, lang_url, og:locale, format_date et format_datetime disponibles dans tous les templates Jinja2
    app.jinja_env.globals["get_locale"] = lambda: str(babel_get_locale() or "fr")
    app.jinja_env.globals["languages"] = LANGUAGES
    app.jinja_env.globals["lang_url"] = lang_url
    app.jinja_env.globals["get_og_locale"] = lambda: OG_LOCALES.get(
        str(babel_get_locale() or "fr"), "fr_FR"
    )
    app.jinja_env.globals["get_og_locale_alternates"] = lambda: [
        v for k, v in OG_LOCALES.items() if k != str(babel_get_locale() or "fr")
    ]
    app.jinja_env.globals["format_date"] = format_date
    app.jinja_env.globals["format_datetime"] = format_datetime
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime

    @app.context_processor
    def inject_plan_constants():
        from .config_plans import (
            FREE_HISTORY_MONTHS,
            MAX_FREE_BOOKS,
            MAX_FREE_SCANS,
            MAX_FREE_STUDENTS,
            PRICE_MONTHLY_AMOUNT,
            PRICE_YEARLY_AMOUNT,
        )

        return {
            "max_students": MAX_FREE_STUDENTS,
            "max_books": MAX_FREE_BOOKS,
            "max_scans": MAX_FREE_SCANS,
            "history_months": FREE_HISTORY_MONTHS,
            "price_monthly": int(PRICE_MONTHLY_AMOUNT),
            "price_yearly": int(PRICE_YEARLY_AMOUNT),
        }

    app.logger.addHandler(handler)
    mail_handler = MailCriticalHandler(
        mail_instance=mail, app=app, recipients=os.getenv("MAIL_USERNAME")
    )
    app.logger.addHandler(mail_handler)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    # set the locale to french for the date format
    try:
        locale.setlocale(locale.LC_TIME, "C.UTF-8")
    except locale.Error:
        print("Locale not supported, falling back to default.")
        locale.setlocale(locale.LC_TIME, "")

    # import data base models
    from .models import (  # noqa: F401
        Book,
        Feedback,
        Loan,
        NewsletterCampaign,
        NewsletterDelivery,
        Student,
        User,
    )

    # Initialisation de la base de données :
    # En test ou en développement local, db.create_all() garantit l'existence des tables.
    # En production (Gunicorn / multi-workers), cette étape est ignorée car les tables
    # sont créées et migrées en amont via Alembic (flask db upgrade).
    is_production = (
        os.getenv("FLASK_ENV") == "production"
        or os.getenv("ENV") == "production"
        or os.getenv("SKIP_DB_CREATE_ALL", "false").lower() in ("true", "1", "yes")
    )
    if app.config.get("TESTING") or not is_production:
        with app.app_context():
            db.create_all()

    # Nettoyage quotidien des comptes non vérifiés (max 1x/jour)
    _last_cleanup = {"ts": None}

    @app.before_request
    def cleanup_unverified_accounts():
        """Supprime les comptes non vérifiés âgés de plus de 7 jours, une fois par jour."""
        if app.config.get("TESTING"):
            return
        now = datetime.now(UTC)
        if _last_cleanup["ts"] is None or now - _last_cleanup["ts"] > timedelta(days=1):
            _last_cleanup["ts"] = now
            from .query import delete_unverified_users

            count = delete_unverified_users()
            if count:
                app.logger.info(
                    "Nettoyage automatique : %d compte(s) non vérifié(s) supprimé(s).",
                    count,
                )

    @login_manager.user_loader
    def load_user(user_id):
        # since the user_id is just the primary key of our user table, use it in the query for the user
        return db.session.get(User, int(user_id))

    @app.url_value_preprocessor
    def pull_lang_code(endpoint, values):
        if values is not None:
            lang = values.pop("lang_code", None)
            if lang:
                if lang not in LANGUAGES:
                    abort(404)
                g.lang_code = lang
                if hasattr(g, "_flask_babel"):
                    delattr(g, "_flask_babel")
                session["lang"] = lang
                if (
                    current_user
                    and current_user.is_authenticated
                    and getattr(current_user, "preferred_language", None) != lang
                ):
                    current_user.preferred_language = lang
                    try:
                        db.session.commit()
                    except Exception:  # noqa: BLE001
                        db.session.rollback()

    @app.url_defaults
    def add_language_code(endpoint, values):
        if "lang_code" in values:
            return
        lang = getattr(g, "lang_code", None) or session.get("lang") or "fr"
        if app.url_map.is_endpoint_expecting(endpoint, "lang_code"):
            values["lang_code"] = lang

    INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "1452be41003e41c59435f150f75f55d8")
    EXEMPT_PREFIXES = ("/static", "/api", "/webhook", "/email/track")
    EXEMPT_PATHS = {
        "/sitemap.xml",
        "/sitemap",
        "/robots.txt",
        "/robot.txt",
        "/robots",
        "/robot",
        "/llms.txt",
        "/llms",
        "/favicon.ico",
        "/manifest.json",
        "/sw.js",
        "/1452be41003e41c59435f150f75f55d8.txt",
        f"/{INDEXNOW_KEY}.txt",
    }

    @app.before_request
    def handle_language_routing():
        """Gère le routage et les redirections vers les URLs avec préfixe de langue."""
        if app.config.get("TESTING") and not app.config.get("TEST_REDIRECTS"):
            return

        # Chemins techniques exemptés
        if (
            request.path.startswith(EXEMPT_PREFIXES)
            or request.path in EXEMPT_PATHS
            or (request.path.endswith(".txt") and request.path.count("/") == 1)
        ):
            return

        # Si l'URL comporte un paramètre explicite ?lang=xx (anciennes URLs indexées)
        lang_arg = request.args.get("lang")
        if lang_arg in LANGUAGES:
            path_parts = request.path.strip("/").split("/")
            if path_parts and path_parts[0] in LANGUAGES:
                path_parts[0] = lang_arg
                clean_path = "/" + "/".join(path_parts)
            else:
                clean_path = f"/{lang_arg}{request.path}"
            rem_args = {k: v for k, v in request.args.items() if k != "lang"}
            from urllib.parse import urlencode

            qs = f"?{urlencode(rem_args)}" if rem_args else ""
            return redirect(f"{clean_path}{qs}", code=301)

        # Si l'URL a déjà un préfixe de langue valide
        path_parts = request.path.strip("/").split("/")
        first_segment = path_parts[0] if path_parts and path_parts[0] else ""
        if first_segment in LANGUAGES:
            return

        # Pour les requêtes non-GET/HEAD (POST, PUT, DELETE...), ne pas rediriger en 302
        # car les navigateurs transforment la requête en GET et perdent le corps de données.
        # Les alias de routes non-préfixés enregistrés sur app.url_map traiteront la requête.
        if request.method not in ("GET", "HEAD"):
            return

        # Négociation de contenu dynamique (302 temporaire + en-tête Vary)
        target_lang = (
            session.get("lang")
            or (
                getattr(current_user, "preferred_language", None)
                if current_user.is_authenticated
                else None
            )
            or request.accept_languages.best_match(LANGUAGES, default="fr")
            or "fr"
        )
        if target_lang not in LANGUAGES:
            target_lang = "fr"

        target_path = f"/{target_lang}{request.path}"
        if request.query_string:
            target_path += "?" + request.query_string.decode("utf-8")

        response = redirect(target_path, code=302)
        response.headers["Vary"] = "Accept-Language, Cookie"
        return response

    # Blueprint registrations
    from .admin import admin as admin_blueprint
    from .auth import auth as auth_blueprint
    from .eleve import eleve as eleve_blueprint
    from .emprunt import emprunt as emprunt_blueprint
    from .export import export as export_blueprint
    from .livre import livre as livre_blueprint
    from .main import core as core_blueprint
    from .main import main as main_blueprint
    from .ressource import ressource as ressource_blueprint
    from .subscription import (
        subscription as subscription_blueprint,
    )
    from .subscription import (
        webhook_bp as webhook_blueprint,
    )

    # Register root / un-prefixed technical blueprints
    app.register_blueprint(core_blueprint)
    app.register_blueprint(webhook_blueprint)

    localized_blueprints = [
        auth_blueprint,
        export_blueprint,
        livre_blueprint,
        eleve_blueprint,
        emprunt_blueprint,
        main_blueprint,
        admin_blueprint,
        ressource_blueprint,
        subscription_blueprint,
    ]
    for bp in localized_blueprints:
        app.register_blueprint(bp, url_prefix="/<lang_code>")

    # Register unprefixed aliases for backward-compatibility & testing
    for rule in list(app.url_map.iter_rules()):
        if "<lang_code>" in rule.rule:
            unprefixed_rule = rule.rule.replace("/<lang_code>", "") or "/"
            app.add_url_rule(
                unprefixed_rule,
                endpoint=rule.endpoint,
                view_func=app.view_functions[rule.endpoint],
                methods=rule.methods,
            )

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if os.getenv("FLASK_ENV") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    # Démarre le thread de maintenance serveur en arrière-plan (hors mode test)
    if not app.config.get("TESTING"):
        from .scheduler import start_background_scheduler

        start_background_scheduler(app)

    return app
