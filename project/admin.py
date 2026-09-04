import os
import random
import re
import string
import time
from threading import Thread

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_mail import Message
from werkzeug.security import generate_password_hash

from . import db, mail
from .models import User

admin = Blueprint("admin", __name__)


@admin.route("/admin")
def index():
    # Fetch all users, order by ID descending (newest first)
    users = User.query.order_by(User.id.desc()).all()
    return render_template("admin/index.html", users=users)


@admin.route("/admin/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    user = db.get_or_404(User, user_id)

    # Generate a random 10-character password
    characters = string.ascii_letters + string.digits
    new_password = "".join(random.choice(characters) for i in range(10))

    # Update the user's password
    user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()

    flash(
        f"Le mot de passe pour {user.email} a été réinitialisé. Nouveau mot de passe : {new_password}",
        "success",
    )
    return redirect(url_for("admin.index"))


@admin.route("/admin/verify_user/<int:user_id>", methods=["POST"])
def verify_user(user_id):
    user = db.get_or_404(User, user_id)
    if not user.is_verified:
        user.is_verified = True
        db.session.commit()
        flash(f"L'utilisateur {user.email} a été marqué comme vérifié.", "success")
    else:
        flash(f"L'utilisateur {user.email} est déjà vérifié.", "info")
    return redirect(url_for("admin.index"))


@admin.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash(
        f"Le compte {email} et toutes ses données associées ont été supprimés.",
        "success",
    )
    return redirect(url_for("admin.index"))


def send_newsletter_async(
    app, subject, sender, template_path, message_content, recipient_data
):
    with app.app_context():
        # Send sequentially to avoid maxing out connections or triggering spam filters too fast
        for r in recipient_data:
            email = r["email"]
            try:
                unsubscribe_url = url_for(
                    "auth.unsubscribe",
                    token=r["token"],
                    user_id=r["id"],
                    _external=True,
                )
                html_body = render_template(
                    template_path,
                    content=message_content,
                    subject=subject,
                    unsubscribe_url=unsubscribe_url,
                    user_name=r.get("name") or "",
                )
                msg = Message(
                    subject, sender=sender, recipients=[email], reply_to=sender
                )
                msg.html = html_body

                # Text body fallback
                text_body = re.sub(r"<[^>]+>", " ", message_content)
                text_body = re.sub(r"\s+", " ", text_body).strip()
                msg.body = (
                    f"{subject}\n\n{text_body}\n\n"
                    f"Pour vous désabonner : {unsubscribe_url}"
                )

                # RFC 8058 standard headers for 1-click unsubscribe
                msg.extra_headers = {
                    "List-Unsubscribe": f"<{unsubscribe_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                }

                mail.send(msg)
                time.sleep(1)  # Small delay between emails
            except OSError as e:
                app.logger.error(
                    f"Erreur lors de l'envoi de la newsletter à {email}: {e}"
                )


@admin.route("/admin/emails", methods=["GET", "POST"])
def emails():
    # Stats for audience counters and health dashboard
    total_users = User.query.count()
    verified_users = User.query.filter_by(is_verified=True).count()
    subscribed_users = User.query.filter_by(newsletter_subscribed=True).count()
    verified_subscribed_users = User.query.filter_by(
        is_verified=True, newsletter_subscribed=True
    ).count()
    unsubscribed_users = total_users - subscribed_users

    active_rate = (
        round((subscribed_users / total_users * 100), 1) if total_users > 0 else 100.0
    )
    quality_rate = (
        round((verified_users / total_users * 100), 1) if total_users > 0 else 100.0
    )

    stats = {
        "total": total_users,
        "verified": verified_users,
        "subscribed": subscribed_users,
        "unsubscribed": unsubscribed_users,
        "verified_subscribed": verified_subscribed_users,
        "active_rate": active_rate,
        "quality_rate": quality_rate,
    }

    recent_users = User.query.order_by(User.id.desc()).limit(8).all()

    if request.method == "POST":
        subject = request.form.get("subject")
        target = request.form.get("target", "verified_subscribed")
        message_content = request.form.get("message")
        template_choice = request.form.get("template_choice", "newsletter.html")

        if not subject or not message_content:
            flash("Veuillez remplir le sujet et le message.", "error")
            return redirect(url_for("admin.emails"))

        # Build recipient list based on target selection
        if target in ("verified_subscribed", "verified"):
            users = User.query.filter_by(
                is_verified=True, newsletter_subscribed=True
            ).all()
        elif target in ("all_subscribed", "all"):
            users = User.query.filter_by(newsletter_subscribed=True).all()
        elif target == "system_all":
            users = User.query.all()
        else:
            users = User.query.filter_by(
                is_verified=True, newsletter_subscribed=True
            ).all()

        recipient_data = [
            {
                "id": u.id,
                "email": u.email,
                "token": u.get_unsubscribe_token(),
                "name": u.name,
            }
            for u in users
            if u.email
        ]

        template_path = f"email/{template_choice}"

        action = request.form.get("action")
        if action == "preview":
            preview_unsubscribe_url = url_for(
                "auth.unsubscribe",
                token="demo-preview-token",
                user_id=0,
                _external=True,
            )
            html_body = render_template(
                template_path,
                content=message_content,
                subject=subject,
                unsubscribe_url=preview_unsubscribe_url,
                user_name="Enseignant Démo",
            )
            return html_body

        if not recipient_data:
            flash("Aucun utilisateur ne correspond à la cible sélectionnée.", "warning")
            return redirect(url_for("admin.emails"))

        sender = os.getenv("MAIL_USERNAME")

        # Start background thread to send emails
        app = current_app._get_current_object()
        thr = Thread(
            target=send_newsletter_async,
            args=[app, subject, sender, template_path, message_content, recipient_data],
        )
        thr.start()

        flash(
            f"La newsletter est en cours d'envoi à {len(recipient_data)} utilisateur(s) en arrière-plan.",
            "success",
        )
        return redirect(url_for("admin.index"))

    return render_template("admin/emails.html", stats=stats, recent_users=recent_users)
