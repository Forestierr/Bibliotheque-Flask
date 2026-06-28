import string
import random
import time
from threading import Thread
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from werkzeug.security import generate_password_hash
from flask_mail import Message
from .models import User
from . import db, mail

admin = Blueprint("admin", __name__)

@admin.route("/admin")
def index():
    # Fetch all users, order by ID descending (newest first)
    users = User.query.order_by(User.id.desc()).all()
    return render_template("admin/index.html", users=users)

@admin.route("/admin/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    
    # Generate a random 10-character password
    characters = string.ascii_letters + string.digits
    new_password = ''.join(random.choice(characters) for i in range(10))
    
    # Update the user's password
    user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()
    
    flash(f"Le mot de passe pour {user.email} a été réinitialisé. Nouveau mot de passe : {new_password}", "success")
    return redirect(url_for("admin.index"))

@admin.route("/admin/verify_user/<int:user_id>", methods=["POST"])
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    if not user.is_verified:
        user.is_verified = True
        db.session.commit()
        flash(f"L'utilisateur {user.email} a été marqué comme vérifié.", "success")
    else:
        flash(f"L'utilisateur {user.email} est déjà vérifié.", "info")
    return redirect(url_for("admin.index"))

@admin.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash(f"Le compte {email} et toutes ses données associées ont été supprimés.", "success")
    return redirect(url_for("admin.index"))

def send_newsletter_async(app, subject, sender, recipients, html_body):
    with app.app_context():
        # Send sequentially to avoid maxing out connections or triggering spam filters too fast
        for email in recipients:
            try:
                msg = Message(subject, sender=sender, recipients=[email])
                msg.html = html_body
                mail.send(msg)
                time.sleep(1) # Small delay between emails
            except Exception as e:
                app.logger.error(f"Erreur lors de l'envoi de la newsletter à {email}: {e}")

@admin.route("/admin/emails", methods=["GET", "POST"])
def emails():
    if request.method == "POST":
        subject = request.form.get("subject")
        target = request.form.get("target")
        message_content = request.form.get("message")
        template_choice = request.form.get("template_choice", "newsletter.html")

        if not subject or not message_content:
            flash("Veuillez remplir le sujet et le message.", "error")
            return redirect(url_for("admin.emails"))

        # Build recipient list
        if target == "verified":
            users = User.query.filter_by(is_verified=True).all()
        else:
            users = User.query.all()
            
        recipients = [u.email for u in users if u.email]

        if not recipients:
            flash("Aucun utilisateur ne correspond à la cible sélectionnée.", "warning")
            return redirect(url_for("admin.emails"))

        import os
        sender = os.getenv("MAIL_USERNAME")
        
        # Determine which template to render
        template_path = f"email/{template_choice}"
        
        # Render the final HTML email using the chosen template
        html_body = render_template(template_path, content=message_content, subject=subject)

        action = request.form.get("action")
        if action == "preview":
            return html_body

        # Start background thread to send emails
        app = current_app._get_current_object()
        thr = Thread(target=send_newsletter_async, args=[app, subject, sender, recipients, html_body])
        thr.start()

        flash(f"La newsletter est en cours d'envoi à {len(recipients)} utilisateur(s) en arrière-plan.", "success")
        return redirect(url_for("admin.index"))

    return render_template("admin/emails.html")
