# init.py

import locale
import logging
import os
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_mail import Mail, Message  # noqa: F401
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from .email_error import MailCriticalHandler

# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()

mail = Mail()

load_dotenv()

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


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = 465
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_USE_TLS"] = False
    app.config["MAIL_USE_SSL"] = True

    db.init_app(app)

    csrf = CSRFProtect()
    csrf.init_app(app)
    Migrate(app, db)
    mail.init_app(app)

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
    from .models import Book, Loan, Student, User  # noqa: F401

    # create database
    with app.app_context():
        db.create_all()

    # Nettoyage quotidien des comptes non vérifiés (max 1x/jour)
    _last_cleanup = {"ts": None}

    @app.before_request
    def cleanup_unverified_accounts():
        """Supprime les comptes non vérifiés âgés de plus de 7 jours, une fois par jour."""
        if app.config.get("TESTING"):
            return
        now = datetime.now(timezone.utc)
        if _last_cleanup["ts"] is None or now - _last_cleanup["ts"] > timedelta(days=1):
            _last_cleanup["ts"] = now
            from .query import delete_unverified_users

            count = delete_unverified_users()
            if count:
                app.logger.info(
                    "Nettoyage automatique : %d compte(s) non vérifié(s) supprimé(s).", count
                )

    @login_manager.user_loader
    def load_user(user_id):
        # since the user_id is just the primary key of our user table, use it in the query for the user
        return User.query.get(int(user_id))

    # blueprint for auth routes in our app
    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint)

    from .export import export as export_blueprint

    app.register_blueprint(export_blueprint)

    # blueprint for livre parts of app
    from .livre import livre as livre_blueprint

    app.register_blueprint(livre_blueprint)

    # blueprint for eleve parts of app
    from .eleve import eleve as eleve_blueprint

    app.register_blueprint(eleve_blueprint)

    # blueprint for emprunt parts of app
    from .emprunt import emprunt as emprunt_blueprint

    app.register_blueprint(emprunt_blueprint)

    # blueprint for non-auth parts of app
    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)

    # blueprint for admin
    from .admin import admin as admin_blueprint

    app.register_blueprint(admin_blueprint)

    return app
