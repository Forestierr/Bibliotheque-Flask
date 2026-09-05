import os
import random
import re
import secrets
import string
import time
from datetime import datetime, timezone
from threading import Thread

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_mail import Message
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from . import db, mail
from .models import Feedback, NewsletterCampaign, NewsletterDelivery, User

admin = Blueprint("admin", __name__)


@admin.route("/admin")
def index():
    # Fetch all users, order by ID descending (newest first)
    users = User.query.order_by(User.id.desc()).all()
    new_feedbacks_count = Feedback.query.filter_by(status="nouveau").count()
    return render_template(
        "admin/index.html", users=users, new_feedbacks_count=new_feedbacks_count
    )


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
    app,
    campaign_id,
    subject,
    sender,
    template_path,
    message_content,
    recipient_data,
    feedback_idea_url,
    feedback_bug_url,
    reglage_url,
):
    with app.app_context():
        campaign = (
            db.session.get(NewsletterCampaign, campaign_id) if campaign_id else None
        )
        # Send sequentially to avoid maxing out connections or triggering spam filters too fast
        for r in recipient_data:
            email = r["email"]
            unsubscribe_url = r["unsubscribe_url"]
            tracking_pixel_url = r.get("tracking_pixel_url")
            delivery_id = r.get("delivery_id")
            delivery = (
                db.session.get(NewsletterDelivery, delivery_id) if delivery_id else None
            )

            try:
                html_body = render_template(
                    template_path,
                    content=message_content,
                    subject=subject,
                    unsubscribe_url=unsubscribe_url,
                    feedback_idea_url=feedback_idea_url,
                    feedback_bug_url=feedback_bug_url,
                    reglage_url=reglage_url,
                    tracking_pixel_url=tracking_pixel_url,
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
                    f"Pour vous désabonner : {unsubscribe_url}\n"
                    f"Donner votre avis : {feedback_idea_url}\n"
                    f"Signaler un problème : {feedback_bug_url}"
                )

                # RFC 8058 standard headers for 1-click unsubscribe
                msg.extra_headers = {
                    "List-Unsubscribe": f"<{unsubscribe_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                }

                mail.send(msg)

                if delivery:
                    delivery.status = "sent"
                    delivery.sent_at = datetime.now(timezone.utc)
                if campaign:
                    campaign.sent_count = (campaign.sent_count or 0) + 1
                db.session.commit()

                time.sleep(1)  # Small delay between emails
            except Exception:
                if delivery:
                    try:
                        delivery.status = "failed"
                        db.session.commit()
                    except SQLAlchemyError:
                        db.session.rollback()
                app.logger.exception(
                    f"Erreur lors de l'envoi de la newsletter à {email}"
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
    campaigns = NewsletterCampaign.query.order_by(
        NewsletterCampaign.created_at.desc()
    ).all()
    active_tab = request.args.get("tab", "compose")

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

        base_url = (os.getenv("BASE_URL") or os.getenv("APP_URL") or "").rstrip("/")
        if base_url:
            feedback_idea_url = f"{base_url}{url_for('main.feedback', type='idea')}"
            feedback_bug_url = f"{base_url}{url_for('main.feedback', type='bug')}"
            reglage_url = f"{base_url}{url_for('auth.reglage')}"
        else:
            feedback_idea_url = url_for("main.feedback", type="idea", _external=True)
            feedback_bug_url = url_for("main.feedback", type="bug", _external=True)
            reglage_url = url_for("auth.reglage", _external=True)

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
                feedback_idea_url=feedback_idea_url,
                feedback_bug_url=feedback_bug_url,
                reglage_url=reglage_url,
                tracking_pixel_url=None,
                user_name="Enseignant Démo",
            )
            return html_body

        valid_users = [u for u in users if u.email]
        if not valid_users:
            flash("Aucun utilisateur ne correspond à la cible sélectionnée.", "warning")
            return redirect(url_for("admin.emails"))

        # 1. Create NewsletterCampaign record
        campaign = NewsletterCampaign(
            subject=subject,
            content=message_content,
            template=template_choice,
            target=target,
            total_recipients=len(valid_users),
            sent_count=0,
            open_count=0,
        )
        db.session.add(campaign)
        db.session.flush()

        recipient_data = []
        for u in valid_users:
            token = secrets.token_urlsafe(32)
            delivery = NewsletterDelivery(
                campaign_id=campaign.id,
                user_id=u.id,
                email=u.email,
                tracking_token=token,
                status="pending",
            )
            db.session.add(delivery)
            db.session.flush()

            if base_url:
                unsubscribe_url = f"{base_url}{url_for('auth.unsubscribe', token=u.get_unsubscribe_token(), user_id=u.id)}"
                tracking_pixel_url = (
                    f"{base_url}{url_for('main.email_track', token=token)}"
                )
            else:
                unsubscribe_url = url_for(
                    "auth.unsubscribe",
                    token=u.get_unsubscribe_token(),
                    user_id=u.id,
                    _external=True,
                )
                tracking_pixel_url = url_for(
                    "main.email_track",
                    token=token,
                    _external=True,
                )
            recipient_data.append(
                {
                    "id": u.id,
                    "delivery_id": delivery.id,
                    "email": u.email,
                    "name": u.name,
                    "unsubscribe_url": unsubscribe_url,
                    "tracking_pixel_url": tracking_pixel_url,
                }
            )

        db.session.commit()

        sender = os.getenv("MAIL_USERNAME")

        # Start background thread to send emails
        app = current_app._get_current_object()
        thr = Thread(
            target=send_newsletter_async,
            args=[
                app,
                campaign.id,
                subject,
                sender,
                template_path,
                message_content,
                recipient_data,
                feedback_idea_url,
                feedback_bug_url,
                reglage_url,
            ],
        )
        thr.start()

        flash(
            f"La campagne « {subject} » est en cours d'envoi à {len(recipient_data)} destinataire(s).",
            "success",
        )
        return redirect(url_for("admin.emails", tab="history"))

    return render_template(
        "admin/emails.html",
        stats=stats,
        recent_users=recent_users,
        campaigns=campaigns,
        active_tab=active_tab,
    )


@admin.route("/admin/campaigns/<int:campaign_id>")
def campaign_details(campaign_id):
    campaign = db.get_or_404(NewsletterCampaign, campaign_id)
    deliveries = (
        NewsletterDelivery.query.filter_by(campaign_id=campaign.id)
        .order_by(NewsletterDelivery.id.asc())
        .all()
    )
    base_url = (os.getenv("BASE_URL") or os.getenv("APP_URL") or "").rstrip("/")
    if base_url:
        feedback_idea_url = f"{base_url}{url_for('main.feedback', type='idea')}"
        feedback_bug_url = f"{base_url}{url_for('main.feedback', type='bug')}"
        reglage_url = f"{base_url}{url_for('auth.reglage')}"
        unsubscribe_url = (
            f"{base_url}{url_for('auth.unsubscribe', token='preview-token', user_id=0)}"
        )
    else:
        feedback_idea_url = url_for("main.feedback", type="idea", _external=True)
        feedback_bug_url = url_for("main.feedback", type="bug", _external=True)
        reglage_url = url_for("auth.reglage", _external=True)
        unsubscribe_url = url_for(
            "auth.unsubscribe",
            token="preview-token",
            user_id=0,
            _external=True,
        )
    rendered_email = render_template(
        f"email/{campaign.template}",
        content=campaign.content,
        subject=campaign.subject,
        unsubscribe_url=unsubscribe_url,
        feedback_idea_url=feedback_idea_url,
        feedback_bug_url=feedback_bug_url,
        reglage_url=reglage_url,
        tracking_pixel_url=None,
        user_name="Enseignant",
    )
    return jsonify(
        {
            "id": campaign.id,
            "subject": campaign.subject,
            "template": campaign.template,
            "target": campaign.target,
            "total_recipients": campaign.total_recipients,
            "sent_count": campaign.sent_count,
            "open_count": campaign.open_count,
            "open_rate": campaign.open_rate,
            "created_at": campaign.created_at.strftime("%d/%m/%Y à %H:%M"),
            "content": campaign.content,
            "rendered_email": rendered_email,
            "deliveries": [
                {
                    "email": d.email,
                    "status": d.status,
                    "sent_at": (
                        d.sent_at.strftime("%d/%m/%Y %H:%M") if d.sent_at else None
                    ),
                    "opened_at": (
                        d.opened_at.strftime("%d/%m/%Y %H:%M") if d.opened_at else None
                    ),
                    "open_count": d.open_count,
                }
                for d in deliveries
            ],
        }
    )


@admin.route("/admin/campaigns/<int:campaign_id>/delete", methods=["POST"])
def delete_campaign(campaign_id):
    campaign = db.get_or_404(NewsletterCampaign, campaign_id)
    subject = campaign.subject
    db.session.delete(campaign)
    db.session.commit()
    flash(
        f"La campagne « {subject} » et ses statistiques ont été supprimées.",
        "success",
    )
    return redirect(url_for("admin.emails", tab="history"))


@admin.route("/admin/feedbacks")
def feedbacks():
    status_filter = request.args.get("status", "all")
    category_filter = request.args.get("category", "all")

    query = Feedback.query

    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    if category_filter != "all":
        query = query.filter_by(category=category_filter)

    feedbacks_list = query.order_by(Feedback.id.desc()).all()

    counts = {
        "all": Feedback.query.count(),
        "nouveau": Feedback.query.filter_by(status="nouveau").count(),
        "en_cours": Feedback.query.filter_by(status="en_cours").count(),
        "traite": Feedback.query.filter_by(status="traite").count(),
    }

    return render_template(
        "admin/feedbacks.html",
        feedbacks=feedbacks_list,
        counts=counts,
        current_status=status_filter,
        current_category=category_filter,
    )


@admin.route("/admin/feedback/<int:feedback_id>/status", methods=["POST"])
def update_feedback_status(feedback_id):
    fb = db.get_or_404(Feedback, feedback_id)
    new_status = request.form.get("status")
    if new_status in ("nouveau", "en_cours", "traite", "archive"):
        fb.status = new_status
        db.session.commit()
        flash("Statut du retour mis à jour avec succès.", "success")
    return redirect(url_for("admin.feedbacks"))


@admin.route("/admin/feedback/<int:feedback_id>/delete", methods=["POST"])
def delete_feedback(feedback_id):
    fb = db.get_or_404(Feedback, feedback_id)
    db.session.delete(fb)
    db.session.commit()
    flash("Retour supprimé avec succès.", "success")
    return redirect(url_for("admin.feedbacks"))
