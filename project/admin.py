import os
import random
import re
import secrets
import string
import time
from datetime import datetime, timedelta, timezone
from threading import Thread

import markupsafe
import stripe
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
from flask_babel import force_locale
from flask_babel import gettext as _
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


@admin.route("/admin/set_plan/<int:user_id>", methods=["POST"])
def set_plan(user_id):
    user = db.get_or_404(User, user_id)
    new_plan = request.form.get("plan")
    trial_days = request.form.get("trial_days", "").strip()
    reset_scans = request.form.get("reset_scans") == "1"

    if new_plan in ["free", "founder", "premium"]:
        user.plan = new_plan
        if new_plan == "premium":
            user.stripe_subscription_status = "active"
        elif new_plan in ["free", "founder"]:
            user.stripe_subscription_status = None
            # On efface toujours trial_ends_at pour garantir un accès pleinement gratuit,
            # sauf si trial_days est fourni et > 0 (traité ci-dessous).
            user.trial_ends_at = None
    elif new_plan == "trial":
        user.plan = "free"
        days = int(trial_days) if trial_days.isdigit() else 30
        if days > 0:
            user.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=days)
        else:
            # trial_days = 0 → gratuit immédiat, on efface la date d'essai
            user.trial_ends_at = None
        user.trial_reminder_sent = False

    # Surcharge de trial_ends_at pour les plans free/founder si trial_days > 0
    if new_plan in ["free", "founder"] and trial_days.isdigit() and int(trial_days) > 0:
        user.trial_ends_at = datetime.now(timezone.utc) + timedelta(
            days=int(trial_days)
        )

    if reset_scans:
        user.free_scans_used = 0

    db.session.commit()
    flash(
        f"Le plan de {user.email} a été mis à jour avec succès (Plan: {user.plan}, Effectif: {user.effective_plan}).",
        "success",
    )
    return redirect(url_for("admin.index"))


@admin.route("/admin/coupons", methods=["GET", "POST"])
def coupons():
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_key:
        flash(
            "La variable STRIPE_SECRET_KEY n'est pas configurée dans l'environnement.",
            "warning",
        )
        return render_template(
            "admin/coupons.html",
            coupons=[],
            promo_codes=[],
            stripe_configured=False,
        )

    stripe.api_key = stripe_key

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        discount_type = request.form.get("discount_type", "percent")
        discount_val = request.form.get("discount_value")
        duration = request.form.get("duration", "once")
        duration_in_months = request.form.get("duration_in_months")
        max_redemptions = request.form.get("max_redemptions")

        try:
            coupon_args = {"duration": duration, "name": f"Code {code}"}
            if discount_type == "percent":
                coupon_args["percent_off"] = float(discount_val)
            else:
                coupon_args["amount_off"] = int(float(discount_val) * 100)
                coupon_args["currency"] = "chf"

            if duration == "repeating" and duration_in_months:
                coupon_args["duration_in_months"] = int(duration_in_months)

            coupon = stripe.Coupon.create(**coupon_args)

            promo_args = {"code": code}
            if max_redemptions and max_redemptions.isdigit():
                promo_args["max_redemptions"] = int(max_redemptions)

            try:
                # API Stripe moderne (2024+) : promotion est un objet typé {'type': 'coupon', 'coupon': id}
                stripe.PromotionCode.create(
                    promotion={"type": "coupon", "coupon": coupon.id},
                    **promo_args,
                )
            except stripe.error.InvalidRequestError as exc:
                # Rétrocompatibilité avec les versions d'API antérieures attendant coupon direct
                if "unknown parameter: promotion" in str(exc).lower():
                    stripe.PromotionCode.create(coupon=coupon.id, **promo_args)
                else:
                    raise

            flash(
                f"Code promotionnel '{code}' créé avec succès sur Stripe !",
                "success",
            )
        except Exception as e:  # noqa: BLE001
            flash(f"Erreur lors de la création sur Stripe : {e}", "danger")

        return redirect(url_for("admin.coupons"))

    coupons_list = []
    promos_list = []
    try:
        coupons_list = stripe.Coupon.list(limit=50).data
        try:
            promos_list = stripe.PromotionCode.list(
                limit=50, expand=["data.promotion.coupon"]
            ).data
        except stripe.error.StripeError:
            promos_list = stripe.PromotionCode.list(limit=50).data

        # Rétrocompatibilité d'accès au coupon pour l'affichage dans le template
        for p in promos_list:
            if (
                not getattr(p, "coupon", None)
                and hasattr(p, "promotion")
                and hasattr(p.promotion, "coupon")
            ):
                p.coupon = p.promotion.coupon
    except Exception as e:  # noqa: BLE001
        flash(f"Impossible de charger les données Stripe : {e}", "warning")

    return render_template(
        "admin/coupons.html",
        coupons=coupons_list,
        promo_codes=promos_list,
        stripe_configured=True,
    )


PSEUDO_PATTERN = re.compile(
    r"\[pseudo\]|\{pseudo\}|\[nom\]|\{nom\}|\[name\]|\{name\}", re.IGNORECASE
)


def get_user_pseudo(user_or_dict, fallback: str = "Enseignant") -> str:
    if isinstance(user_or_dict, dict):
        name = user_or_dict.get("name")
        email = user_or_dict.get("email", "")
    else:
        name = getattr(user_or_dict, "name", None)
        email = getattr(user_or_dict, "email", "")

    if name and str(name).strip():
        return str(name).strip()
    if email and "@" in email:
        return email.split("@")[0]
    return fallback


def replace_pseudo(text: str, pseudo: str, is_html: bool = False) -> str:
    if not text:
        return text
    val = str(markupsafe.escape(pseudo) if is_html else pseudo)
    return PSEUDO_PATTERN.sub(lambda _: val, text)


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
            recipient_lang = r.get("lang") or "fr"
            delivery = (
                db.session.get(NewsletterDelivery, delivery_id) if delivery_id else None
            )

            pseudo = get_user_pseudo(r)
            personalized_subject = replace_pseudo(subject, pseudo, is_html=False)
            personalized_html_content = replace_pseudo(
                message_content, pseudo, is_html=True
            )

            try:
                with force_locale(recipient_lang):
                    html_body = render_template(
                        template_path,
                        content=personalized_html_content,
                        subject=personalized_subject,
                        unsubscribe_url=unsubscribe_url,
                        feedback_idea_url=feedback_idea_url,
                        feedback_bug_url=feedback_bug_url,
                        reglage_url=reglage_url,
                        tracking_pixel_url=tracking_pixel_url,
                        user_name=pseudo,
                    )
                    msg = Message(
                        personalized_subject,
                        sender=sender,
                        recipients=[email],
                        reply_to=sender,
                    )
                    msg.html = html_body

                    # Text body fallback
                    text_body = re.sub(r"<[^>]+>", " ", personalized_html_content)
                    text_body = re.sub(r"\s+", " ", text_body).strip()
                    unsub_label = _("Pour vous désabonner :")
                    feedback_label = _("Donner votre avis :")
                    bug_label = _("Signaler un problème :")

                    msg.body = (
                        f"{personalized_subject}\n\n{text_body}\n\n"
                        f"{unsub_label} {unsubscribe_url}\n"
                        f"{feedback_label} {feedback_idea_url}\n"
                        f"{bug_label} {feedback_bug_url}"
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

    # Counts by language for interactive selector matrix
    subscribed_fr = User.query.filter_by(
        newsletter_subscribed=True, preferred_language="fr"
    ).count()
    subscribed_en = User.query.filter_by(
        newsletter_subscribed=True, preferred_language="en"
    ).count()
    subscribed_de = User.query.filter_by(
        newsletter_subscribed=True, preferred_language="de"
    ).count()

    verified_sub_fr = User.query.filter_by(
        is_verified=True, newsletter_subscribed=True, preferred_language="fr"
    ).count()
    verified_sub_en = User.query.filter_by(
        is_verified=True, newsletter_subscribed=True, preferred_language="en"
    ).count()
    verified_sub_de = User.query.filter_by(
        is_verified=True, newsletter_subscribed=True, preferred_language="de"
    ).count()

    all_fr = User.query.filter_by(preferred_language="fr").count()
    all_en = User.query.filter_by(preferred_language="en").count()
    all_de = User.query.filter_by(preferred_language="de").count()

    counts_matrix = {
        "verified_subscribed": {
            "all": verified_subscribed_users,
            "fr": verified_sub_fr,
            "en": verified_sub_en,
            "de": verified_sub_de,
        },
        "all_subscribed": {
            "all": subscribed_users,
            "fr": subscribed_fr,
            "en": subscribed_en,
            "de": subscribed_de,
        },
        "system_all": {
            "all": total_users,
            "fr": all_fr,
            "en": all_en,
            "de": all_de,
        },
    }

    lang_distribution = {
        "fr": {
            "count": subscribed_fr,
            "pct": (
                round(subscribed_fr / subscribed_users * 100, 1)
                if subscribed_users
                else 0
            ),
        },
        "en": {
            "count": subscribed_en,
            "pct": (
                round(subscribed_en / subscribed_users * 100, 1)
                if subscribed_users
                else 0
            ),
        },
        "de": {
            "count": subscribed_de,
            "pct": (
                round(subscribed_de / subscribed_users * 100, 1)
                if subscribed_users
                else 0
            ),
        },
    }

    stats = {
        "total": total_users,
        "verified": verified_users,
        "subscribed": subscribed_users,
        "unsubscribed": unsubscribed_users,
        "verified_subscribed": verified_subscribed_users,
        "active_rate": active_rate,
        "quality_rate": quality_rate,
        "counts_matrix": counts_matrix,
        "lang_distribution": lang_distribution,
    }

    # Handle campaign duplication via query params
    duplicate_campaign = None
    duplicate_id = request.args.get("duplicate_id")
    target_lang_prefill = request.args.get("target_lang", "all")
    if duplicate_id:
        try:
            duplicate_campaign = db.session.get(NewsletterCampaign, int(duplicate_id))
        except (ValueError, TypeError):
            pass

    recent_users = User.query.order_by(User.id.desc()).limit(8).all()
    campaigns = NewsletterCampaign.query.order_by(
        NewsletterCampaign.created_at.desc()
    ).all()
    active_tab = request.args.get("tab", "compose")

    if request.method == "POST":
        subject = request.form.get("subject")
        target = request.form.get("target", "verified_subscribed")
        target_lang = request.form.get("target_lang", "all")
        message_content = request.form.get("message")
        template_choice = request.form.get("template_choice", "newsletter.html")

        if not subject or not message_content:
            flash("Veuillez remplir le sujet et le message.", "error")
            return redirect(url_for("admin.emails"))

        # Build recipient query based on target selection
        query = User.query
        if target in ("verified_subscribed", "verified"):
            query = query.filter_by(is_verified=True, newsletter_subscribed=True)
        elif target in ("all_subscribed", "all"):
            query = query.filter_by(newsletter_subscribed=True)
        elif target == "system_all":
            pass
        else:
            query = query.filter_by(is_verified=True, newsletter_subscribed=True)

        if target_lang in ("fr", "en", "de"):
            query = query.filter_by(preferred_language=target_lang)

        users = query.all()

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
            demo_pseudo = "Alexandre"
            prev_sub = replace_pseudo(subject, demo_pseudo, is_html=False)
            prev_msg = replace_pseudo(message_content, demo_pseudo, is_html=True)
            prev_lang = target_lang if target_lang in ("fr", "en", "de") else "fr"
            with force_locale(prev_lang):
                html_body = render_template(
                    template_path,
                    content=prev_msg,
                    subject=prev_sub,
                    unsubscribe_url=preview_unsubscribe_url,
                    feedback_idea_url=feedback_idea_url,
                    feedback_bug_url=feedback_bug_url,
                    reglage_url=reglage_url,
                    tracking_pixel_url=None,
                    user_name=demo_pseudo,
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
            target_lang=target_lang,
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
                    "lang": getattr(u, "preferred_language", "fr") or "fr",
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
        duplicate_campaign=duplicate_campaign,
        target_lang_prefill=target_lang_prefill,
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

    demo_lang = (
        campaign.target_lang
        if getattr(campaign, "target_lang", None) in ("fr", "en", "de")
        else "fr"
    )
    demo_pseudo = "Alexandre"
    prev_sub = replace_pseudo(campaign.subject, demo_pseudo, is_html=False)
    prev_msg = replace_pseudo(campaign.content, demo_pseudo, is_html=True)
    with force_locale(demo_lang):
        rendered_email = render_template(
            f"email/{campaign.template}",
            content=prev_msg,
            subject=prev_sub,
            unsubscribe_url=unsubscribe_url,
            feedback_idea_url=feedback_idea_url,
            feedback_bug_url=feedback_bug_url,
            reglage_url=reglage_url,
            tracking_pixel_url=None,
            user_name=demo_pseudo,
        )
    return jsonify(
        {
            "id": campaign.id,
            "subject": campaign.subject,
            "template": campaign.template,
            "target": campaign.target,
            "target_lang": getattr(campaign, "target_lang", "all"),
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
