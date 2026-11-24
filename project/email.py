import logging
import os
from threading import Thread

from flask import current_app, render_template, url_for
from flask_babel import force_locale
from flask_babel import gettext as _
from flask_mail import Message

from . import mail

logger = logging.getLogger(__name__)


def send_email_async(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:
            logger.exception("Erreur lors de l'envoi d'email async")


def send_email(subject, sender, recipients, text_body):
    app = current_app._get_current_object()
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    thr = Thread(target=send_email_async, args=[app, msg])
    thr.start()
    return thr


def send_email_to_me(subject, text_body):
    sender = os.getenv("MAIL_USERNAME")
    recipients = [os.getenv("MAIL_USERNAME")]
    send_email(subject, sender, recipients, text_body)


def send_html_email(subject, sender, recipients, html_body):
    app = current_app._get_current_object()
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.html = html_body
    thr = Thread(target=send_email_async, args=[app, msg])
    thr.start()
    return thr


def send_email_with_attachment(subject, sender, recipients, text_body, attachment):
    app = current_app._get_current_object()
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.attach(attachment)
    thr = Thread(target=send_email_async, args=[app, msg])
    thr.start()
    return thr


def send_email_confirmation(name, firstname, email):
    subject = "Confirmation de votre message"
    sender = os.getenv("MAIL_USERNAME")
    recipients = [email]
    html_body = render_template(
        "email/email_confirmation.html", name=name, firstname=firstname
    )
    send_html_email(subject, sender, recipients, html_body)


def send_email_bienvenue(name, email):
    subject = "Bienvenue sur LivresEnClasse"
    sender = os.getenv("MAIL_USERNAME")
    recipients = [email]
    html_body = render_template("email/email_bienvenue.html", name=name)
    send_html_email(subject, sender, recipients, html_body)


def send_email_verification(user):
    subject = "Vérification de votre compte LivresEnClasse"
    sender = os.getenv("MAIL_USERNAME")
    recipients = [user.email]

    verification_url = url_for(
        "auth.verify_email",
        token=user.get_verification_token(),
        user_id=user.id,
        _external=True,
    )

    html_body = render_template(
        "email/email_verification.html", user=user, verification_url=verification_url
    )
    send_html_email(subject, sender, recipients, html_body)
    logger.info(f"Email de vérification envoyé à {user.email}")


def send_email_reset_password(user):
    subject = "Réinitialisation de votre mot de passe"
    sender = os.getenv("MAIL_USERNAME")
    recipients = [user.email]

    reset_password_url = url_for(
        "auth.reset_password",
        token=user.get_reset_password_token(),
        user_id=user.id,
        _external=True,
    )

    html_body = render_template(
        "email/email_reset_password.html", reset_password_url=reset_password_url
    )
    send_html_email(subject, sender, recipients, html_body)
    logger.info(f"Email de réinitialisation de mot de passe envoyé à {user.email}")


def send_email_scan_limit_reached(user):
    """Envoie l'e-mail de remerciement et offre promo (-30%) lorsque l'utilisateur atteint 30 scans pour la première fois."""
    user_lang = getattr(user, "preferred_language", "fr") or "fr"
    with force_locale(user_lang):
        subject = _(
            "Merci ! Votre bibliothèque de classe tourne à plein régime (+ un cadeau)"
        )
        sender = os.getenv("MAIL_USERNAME")
        recipients = [user.email]

        firstname = (
            user.name.strip().split()[0] if user.name and user.name.strip() else None
        )

        try:
            tarifs_url = url_for("subscription.tarifs", _external=True)
        except RuntimeError:
            tarifs_url = "https://livresenclasse.com/tarifs"

        html_body = render_template(
            "email/email_scan_limit_reached.html",
            user=user,
            firstname=firstname,
            tarifs_url=tarifs_url,
        )
        send_html_email(subject, sender, recipients, html_body)
        logger.info(
            f"Email offre promo premier scan limit (30 scans) envoyé à {user.email}"
        )


def send_email_book_milestone(user, book_count=80):
    """Envoie l'e-mail de félicitations et offre promo lorsque la bibliothèque atteint le palier des 80 livres."""
    user_lang = getattr(user, "preferred_language", "fr") or "fr"
    with force_locale(user_lang):
        subject = _(
            "Votre bibliothèque de classe compte déjà plus de 80 livres — Livres en Classe"
        )
        sender = os.getenv("MAIL_USERNAME")
        recipients = [user.email]

        firstname = (
            user.name.strip().split()[0] if user.name and user.name.strip() else None
        )

        try:
            tarifs_url = url_for("subscription.tarifs", _external=True)
        except RuntimeError:
            tarifs_url = "https://livresenclasse.com/tarifs"

        html_body = render_template(
            "email/email_book_milestone.html",
            user=user,
            firstname=firstname,
            book_count=book_count,
            tarifs_url=tarifs_url,
        )
        send_html_email(subject, sender, recipients, html_body)
        logger.info(
            f"Email palier 80 livres ({book_count} livres) envoyé à {user.email}"
        )


def send_email_subscription_renewal_reminder(user, days_left=None):
    """Envoie l'e-mail de rappel de renouvellement à J-30 avant l'échéance des 365 jours."""
    user_lang = getattr(user, "preferred_language", "fr") or "fr"
    with force_locale(user_lang):
        days = days_left if days_left is not None else user.subscription_days_left
        subject = _(
            "Renouvellement annuel de votre abonnement Livres en Classe (échéance dans %(days)s jours)",
            days=days,
        )
        sender = os.getenv("MAIL_USERNAME")
        recipients = [user.email]

        end_date_str = ""
        if user.subscription_end_at:
            end_date_str = user.subscription_end_at.strftime("%d/%m/%Y")

        try:
            tarifs_url = url_for("subscription.tarifs", _external=True)
        except RuntimeError:
            tarifs_url = "https://livresenclasse.com/tarifs"

        try:
            facture_ecole_url = url_for("subscription.facture_ecole", _external=True)
        except RuntimeError:
            facture_ecole_url = "https://livresenclasse.com/subscription/facture-ecole"

        html_body = render_template(
            "email/email_subscription_renewal_reminder.html",
            user=user,
            days_left=days,
            end_date_str=end_date_str,
            tarifs_url=tarifs_url,
            facture_ecole_url=facture_ecole_url,
        )
        send_html_email(subject, sender, recipients, html_body)
        logger.info(
            f"Email rappel renouvellement (échéance sous {days} jours) envoyé à {user.email}"
        )
