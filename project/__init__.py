# init.py

from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os

import locale

# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()

mail = Mail()

load_dotenv()

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI")

    app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
    app.config['MAIL_PORT'] = 465
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
    app.config['MAIL_USE_TLS'] = False
    app.config['MAIL_USE_SSL'] = True

    db.init_app(app)
    migrate = Migrate(app, db)
    mail.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    # set the locale to french for the date format
    try:
        locale.setlocale(locale.LC_TIME, 'C.UTF-8')
    except locale.Error:
        print("Locale not supported, falling back to default.")
        locale.setlocale(locale.LC_TIME, '')

    # import data base models
    from .models import User, Book, Student, Loan

    # create database
    with app.app_context():
        db.create_all()

    @login_manager.user_loader
    def load_user(user_id):
        # since the user_id is just the primary key of our user table, use it in the query for the user
        return User.query.get(int(user_id))

    # blueprint for auth routes in our app
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

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

    return app
