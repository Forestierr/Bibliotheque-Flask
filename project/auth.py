# auth.py

import os

import requests
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .email import (
    send_email_reset_password,
    send_email_verification,
)
from .models import User

auth = Blueprint("auth", __name__)


@auth.route("/login")
def login():
    return render_template(
        "auth/login.html",
        hcaptcha_site_key=os.getenv("HCAPTCHA_SITE_KEY", ""),
    )


@auth.route("/login", methods=["POST"])
def login_post():
    email = request.form.get("email")
    password = request.form.get("password")
    remember = bool(request.form.get("remember"))

    # Vérification hCaptcha (ignorée si la clé n'est pas configurée)
    hcaptcha_secret = os.getenv("HCAPTCHA_SECRET_KEY", "")
    if hcaptcha_secret:
        captcha_token = request.form.get("h-captcha-response", "")
        if not captcha_token:
            flash("Veuillez compléter le CAPTCHA.", "error")
            return redirect(url_for("auth.login"))
        verify_response = requests.post(
            "https://api.hcaptcha.com/siteverify",
            data={"secret": hcaptcha_secret, "response": captcha_token},
            timeout=5,
        )
        if not verify_response.json().get("success", False):
            flash("CAPTCHA invalide. Veuillez réessayer.", "error")
            return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()

    # check if user actually exists
    # take the user supplied password, hash it, and compare it to the hashed password in database
    if not user or not check_password_hash(user.password, password):
        flash("Vérifier si votre email et votre mot de passe sont correcte.")
        return redirect(
            url_for("auth.login")
        )  # if user doesn't exist or password is wrong, reload the page

    if not user.is_verified:
        flash("Veuillez vérifier votre adresse e-mail avant de vous connecter.")
        return redirect(url_for("auth.login"))

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    return redirect(url_for("main.dashboard"))


@auth.route("/signup")
def signup():
    return render_template(
        "auth/signup.html",
        hcaptcha_site_key=os.getenv("HCAPTCHA_SITE_KEY", ""),
    )


@auth.route("/signup", methods=["POST"])
def signup_post():
    email = request.form.get("email")
    name = request.form.get("name")
    password = request.form.get("password")

    # Vérification hCaptcha (ignorée si la clé n'est pas configurée)
    hcaptcha_secret = os.getenv("HCAPTCHA_SECRET_KEY", "")
    if hcaptcha_secret:
        captcha_token = request.form.get("h-captcha-response", "")
        if not captcha_token:
            flash("Veuillez compléter le CAPTCHA.", "error")
            return redirect(url_for("auth.signup"))
        verify_response = requests.post(
            "https://api.hcaptcha.com/siteverify",
            data={"secret": hcaptcha_secret, "response": captcha_token},
            timeout=5,
        )
        if not verify_response.json().get("success", False):
            flash("CAPTCHA invalide. Veuillez réessayer.", "error")
            return redirect(url_for("auth.signup"))

    user = User.query.filter_by(
        email=email
    ).first()  # if this returns a user, then the email already exists in database

    if user:  # if a user is found, we want to redirect back to signup page so user can try again
        flash("Cette email est déjà utilisé.")
        return redirect(url_for("auth.signup"))

    # create new user with the form data. Hash the password so plaintext version isn't saved.
    new_user = User(
        email=email,
        name=name,
        password=generate_password_hash(password, method="pbkdf2:sha256"),
    )

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    # envoi d'un email de bienvenue à l'utilisateur
    # sans bloquer l'application
    send_email_verification(new_user)

    flash(
        "Un e-mail de vérification vous a été envoyé. Veuillez vérifier votre boîte de réception.",
        "success",
    )
    return redirect(url_for("auth.login"))


@auth.route("/verify_email/<token>/<int:user_id>")
def verify_email(token, user_id):
    user = User.validate_verification_token(token, user_id)
    if not user:
        flash("Le lien de vérification est invalide ou a expiré.", "error")
        return redirect(url_for("auth.login"))

    if user.is_verified:
        flash("Votre compte est déjà vérifié.", "info")
        return redirect(url_for("auth.login"))

    user.is_verified = True
    db.session.commit()
    flash(
        "Votre adresse e-mail a été vérifiée avec succès. Vous pouvez maintenant vous connecter.",
        "success",
    )
    return redirect(url_for("auth.login"))


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@auth.route("/reset_password", methods=["GET", "POST"])
def reset_password_request():
    if request.method == "POST":
        email = request.form.get("email")
        if not email:
            flash("Vous devez indiquer votre email.", "error")
            return redirect(url_for("auth.reset_password_request"))

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Aucun utilisateur trouvé avec cet email.", "error")
            return redirect(url_for("auth.reset_password_request"))

        flash(
            "Un email avec les instructions de réinitialisation de mot de passe a été envoyé.",
            "success",
        )
        send_email_reset_password(user)

        return redirect(url_for("auth.reset_password_request"))

    return render_template("auth/reset_password_request.html")


@auth.route("/reset_password/<token>/<int:user_id>", methods=["GET", "POST"])
def reset_password(token, user_id):
    user = User.validate_reset_password_token(token, user_id)
    if not user:
        flash(
            "Le lien de réinitialisation de mot de passe est invalide ou a expiré.",
            "error",
        )
        return redirect(url_for("auth.reset_password_request"))

    if request.method == "POST":
        password = request.form.get("password")
        password2 = request.form.get("password2")

        if not password or not password2:
            flash("Vous devez indiquer un nouveau mot de passe.", "error")
            return redirect(
                url_for("auth.reset_password", token=token, user_id=user_id)
            )

        if password != password2:
            flash("Les mots de passe ne correspondent pas.", "error")
            return redirect(
                url_for("auth.reset_password", token=token, user_id=user_id)
            )

        user.password = generate_password_hash(password, method="pbkdf2:sha256")
        db.session.commit()
        flash("Votre mot de passe a été réinitialisé avec succès.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")


@auth.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    # db.session.query(User).filter(User.id == current_user.id).delete()
    # db.session.commit()
    # logout_user()

    # return redirect(url_for('main.index'))
    print("delete account !!!!")

    return redirect(url_for("auth.reglage"))


@auth.route("/reglage", methods=["GET", "POST"])
@login_required
def reglage():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        new_password = request.form.get("new_password")

        user = db.session.query(User).filter(User.id == current_user.id).first()

        if not name:
            flash("Vous devez indiquer votre nom.", "error")
            return redirect(url_for("auth.reglage"))

        if not email:
            flash("Vous devez indiquer votre email.", "error")
            return redirect(url_for("auth.reglage"))

        if user.email != email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash("Cette adresse email est déjà utilisée.", "error")
                return redirect(url_for("auth.reglage"))
            user.email = email
            user.is_verified = False
            send_email_verification(user)
            flash(
                "Un e-mail de vérification a été envoyé à votre nouvelle adresse.",
                "info",
            )

        if user.name != name:
            user.name = name

        if password:
            if not check_password_hash(user.password, password):
                flash("Votre mot de passe est incorrect.", "error")
                return redirect(url_for("auth.reglage"))
            if not new_password:
                flash("Vous devez indiquer un nouveau mot de passe.", "error")
                return redirect(url_for("auth.reglage"))
            user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
        else:
            if new_password:
                flash("Vous devez indiquer votre mot de passe actuel.", "error")
                return redirect(url_for("auth.reglage"))

        db.session.commit()
        flash("Vos informations ont été mises à jour.", "success")

    user = (
        db.session.query(User)
        .with_entities(User.name, User.email)
        .filter(User.id == current_user.id)
        .first()
    )

    return render_template("user/reglage.html", user=user)
