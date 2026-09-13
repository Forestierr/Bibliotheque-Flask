import importlib.metadata
import os
import random
import re
import secrets
import string
import sys
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
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from . import config_plans, db, mail
from .models import (
    Book,
    Feedback,
    Loan,
    NewsletterCampaign,
    NewsletterDelivery,
    Student,
    User,
)

admin = Blueprint("admin", __name__)


@admin.context_processor
def inject_admin_globals():
    try:
        new_feedbacks = Feedback.query.filter_by(status="nouveau").count()
        total_users = User.query.count()
    except SQLAlchemyError:
        new_feedbacks = 0
        total_users = 0
    return {
        "new_feedbacks_count": new_feedbacks,
        "total_users_count": total_users,
    }


@admin.route("/admin")
def index():
    now = datetime.now(timezone.utc)
    total_users = User.query.count()
    active_users = User.query.filter_by(is_verified=True).count()
    unconfirmed_users = max(0, total_users - active_users)
    premium_users = User.query.filter_by(plan="premium").count()
    founder_users = User.query.filter_by(plan="founder").count()
    paying_or_founder_users = premium_users + founder_users
    trial_users = User.query.filter(User.trial_ends_at > now).count()
    free_users = max(0, total_users - paying_or_founder_users - trial_users)
    newsletter_subscribers = User.query.filter_by(newsletter_subscribed=True).count()

    total_books = Book.query.count()
    total_students = Student.query.count()
    total_loans = Loan.query.count()
    total_scans = db.session.query(func.sum(User.free_scans_used)).scalar() or 0

    new_feedbacks = Feedback.query.filter_by(status="nouveau").count()
    total_feedbacks = Feedback.query.count()

    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    recent_feedbacks = Feedback.query.order_by(Feedback.id.desc()).limit(5).all()

    # Évolution des inscriptions sur les 30 derniers jours
    today = datetime.now(timezone.utc).date()
    days_labels = []
    days_map = {}
    for i in range(29, -1, -1):
        day_date = today - timedelta(days=i)
        days_labels.append(day_date.strftime("%d/%m"))
        days_map[day_date] = 0

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_users_30d = User.query.filter(User.created_at >= thirty_days_ago).all()
    for u in recent_users_30d:
        if u.created_at:
            u_date = (
                u.created_at.date() if hasattr(u.created_at, "date") else u.created_at
            )
            if u_date in days_map:
                days_map[u_date] += 1

    chart_signups_data = [
        days_map[today - timedelta(days=i)] for i in range(29, -1, -1)
    ]

    # Métriques financières et répartition des abonnements payants
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    stripe_connected = False
    currency = config_plans.DEFAULT_CURRENCY
    monthly_subs_count = 0
    yearly_subs_count = 0
    monthly_mrr = 0.0
    yearly_mrr = 0.0
    total_revenue_collected = 0.0

    # Période de 6 mois pour le graphique des encaissements
    cur_year = today.year
    cur_month = today.month
    revenue_slots = []
    for i in range(5, -1, -1):
        m = cur_month - i
        y = cur_year
        while m <= 0:
            m += 12
            y -= 1
        revenue_slots.append((y, m))

    month_names_fr = {
        1: "Janv",
        2: "Févr",
        3: "Mars",
        4: "Avr",
        5: "Mai",
        6: "Juin",
        7: "Juil",
        8: "Août",
        9: "Sept",
        10: "Oct",
        11: "Nov",
        12: "Déc",
    }
    revenue_chart_labels = [
        f"{month_names_fr[m]} {str(y)[2:]}" for (y, m) in revenue_slots
    ]
    revenue_by_slot = {s: 0.0 for s in revenue_slots}
    subs_by_slot = {s: 0 for s in revenue_slots}
    cancels_by_slot = {s: 0 for s in revenue_slots}

    if stripe_key:
        try:
            stripe.api_key = stripe_key
            stripe_subs = stripe.Subscription.list(status="active", limit=100)
            stripe_connected = True
            for s in stripe_subs.data:
                interval = None
                amount = 0.0
                if getattr(s, "plan", None):
                    interval = s.plan.interval
                    amount = (s.plan.amount or 0) / 100.0
                elif s.items and s.items.data:
                    item = s.items.data[0]
                    if item.price and item.price.recurring:
                        interval = item.price.recurring.interval
                        amount = (item.price.unit_amount or 0) / 100.0

                if interval == "year":
                    yearly_subs_count += 1
                    yearly_mrr += amount / 12.0
                else:
                    monthly_subs_count += 1
                    monthly_mrr += amount

            # Flux complet des abonnements et résiliations via Stripe
            all_subs = stripe.Subscription.list(status="all", limit=100)
            for s in all_subs.data:
                if getattr(s, "created", None):
                    c_dt = datetime.fromtimestamp(s.created, tz=timezone.utc)
                    slot_c = (c_dt.year, c_dt.month)
                    if slot_c in subs_by_slot:
                        subs_by_slot[slot_c] += 1
                c_ts = getattr(s, "canceled_at", None) or getattr(s, "ended_at", None)
                if c_ts:
                    e_dt = datetime.fromtimestamp(c_ts, tz=timezone.utc)
                    slot_e = (e_dt.year, e_dt.month)
                    if slot_e in cancels_by_slot:
                        cancels_by_slot[slot_e] += 1

            # Invoices payées pour l'historique de revenus
            invoices = stripe.Invoice.list(status="paid", limit=100)
            for inv in invoices.data:
                paid = round((inv.amount_paid or 0) / 100.0, 2)
                total_revenue_collected += paid
                inv_dt = datetime.fromtimestamp(inv.created, tz=timezone.utc)
                slot = (inv_dt.year, inv_dt.month)
                if slot in revenue_by_slot:
                    revenue_by_slot[slot] += paid
        except Exception as e:  # noqa: BLE001
            current_app.logger.warning(
                "Erreur de récupération des métriques Stripe : %s", e
            )
            stripe_connected = False

    # Fallback si Stripe non connecté ou hors-ligne (ex: tests automatisés)
    if not stripe_connected or (
        monthly_subs_count == 0 and yearly_subs_count == 0 and premium_users > 0
    ):
        premium_db_users = User.query.filter_by(plan="premium").all()
        for u in premium_db_users:
            if u.stripe_price_id and (
                "year" in u.stripe_price_id.lower()
                or u.stripe_price_id == os.getenv("STRIPE_PRICE_ID_YEARLY")
            ):
                yearly_subs_count += 1
            else:
                monthly_subs_count += 1

        monthly_mrr = monthly_subs_count * config_plans.PRICE_MONTHLY_AMOUNT
        yearly_mrr = yearly_subs_count * (config_plans.PRICE_YEARLY_AMOUNT / 12.0)
        if total_revenue_collected == 0:
            total_revenue_collected = (
                monthly_subs_count * config_plans.PRICE_MONTHLY_AMOUNT
            ) + (yearly_subs_count * config_plans.PRICE_YEARLY_AMOUNT)
            revenue_by_slot[revenue_slots[-1]] = round(
                monthly_mrr + (yearly_mrr * 12.0), 2
            )

    # Fallback pour le flux abonnements / résiliations depuis la base locale si Stripe non connecté
    if not stripe_connected or (
        sum(subs_by_slot.values()) == 0 and sum(cancels_by_slot.values()) == 0
    ):
        for u in User.query.all():
            if (u.plan in ("premium", "founder") or u.stripe_price_id) and u.created_at:
                u_c = (
                    u.created_at.replace(tzinfo=timezone.utc)
                    if u.created_at.tzinfo is None
                    else u.created_at
                )
                slot_c = (u_c.year, u_c.month)
                if slot_c in subs_by_slot:
                    subs_by_slot[slot_c] += 1
            if u.subscription_end_at or u.stripe_subscription_status == "canceled":
                end_dt = u.subscription_end_at or u.created_at
                if end_dt:
                    u_e = (
                        end_dt.replace(tzinfo=timezone.utc)
                        if end_dt.tzinfo is None
                        else end_dt
                    )
                    slot_e = (u_e.year, u_e.month)
                    if slot_e in cancels_by_slot:
                        cancels_by_slot[slot_e] += 1

    total_mrr = round(monthly_mrr + yearly_mrr, 2)
    total_arr = round(total_mrr * 12.0, 2)
    total_revenue_collected = round(total_revenue_collected, 2)
    revenue_chart_data = [round(revenue_by_slot[s], 2) for s in revenue_slots]
    active_subscriptions_count = monthly_subs_count + yearly_subs_count

    # Calculs du flux d'abonnements et de résiliations
    subs_chart_data = [subs_by_slot[s] for s in revenue_slots]
    cancels_chart_data = [-cancels_by_slot[s] for s in revenue_slots]
    total_new_subs = sum(subs_by_slot.values())
    total_cancels = sum(cancels_by_slot.values())
    net_subs_flow = total_new_subs - total_cancels
    churn_rate = (
        round((total_cancels / (active_subscriptions_count + total_cancels) * 100), 1)
        if (active_subscriptions_count + total_cancels) > 0
        else 0.0
    )
    retention_rate = round(max(0.0, 100.0 - churn_rate), 1)

    sub_flow_stats = {
        "total_new": total_new_subs,
        "total_cancels": total_cancels,
        "net_flow": net_subs_flow,
        "churn_rate": churn_rate,
        "retention_rate": retention_rate,
    }

    financial_stats = {
        "mrr": total_mrr,
        "arr": total_arr,
        "total_revenue": total_revenue_collected,
        "currency": currency,
        "active_subscriptions": active_subscriptions_count,
        "monthly_subs": monthly_subs_count,
        "yearly_subs": yearly_subs_count,
        "monthly_mrr": round(monthly_mrr, 2),
        "yearly_mrr": round(yearly_mrr, 2),
        "stripe_connected": stripe_connected,
    }

    subscriptions_type_distribution = {
        "Mensuel (5 CHF)": monthly_subs_count,
        "Annuel (30 CHF)": yearly_subs_count,
    }

    plans_distribution = {
        "Gratuit": free_users,
        "Essai": trial_users,
        "Premium": premium_users,
        "Fondateur": founder_users,
    }

    stats = {
        "total_users": total_users,
        "active_users": active_users,
        "unconfirmed_users": unconfirmed_users,
        "premium_users": premium_users,
        "founder_users": founder_users,
        "paying_or_founder_users": paying_or_founder_users,
        "trial_users": trial_users,
        "free_users": free_users,
        "newsletter_subscribers": newsletter_subscribers,
        "total_books": total_books,
        "total_students": total_students,
        "total_loans": total_loans,
        "total_scans": total_scans,
        "new_feedbacks": new_feedbacks,
        "total_feedbacks": total_feedbacks,
    }

    return render_template(
        "admin/index.html",
        stats=stats,
        recent_users=recent_users,
        recent_feedbacks=recent_feedbacks,
        chart_signups_labels=days_labels,
        chart_signups_data=chart_signups_data,
        plans_distribution=plans_distribution,
        financial_stats=financial_stats,
        subscriptions_type_distribution=subscriptions_type_distribution,
        revenue_chart_labels=revenue_chart_labels,
        revenue_chart_data=revenue_chart_data,
        sub_flow_stats=sub_flow_stats,
        subs_chart_data=subs_chart_data,
        cancels_chart_data=cancels_chart_data,
        active_page="dashboard",
    )


@admin.route("/admin/utilisateurs")
def users():
    users_list = User.query.order_by(User.id.desc()).all()
    return render_template(
        "admin/users.html",
        users=users_list,
        active_page="users",
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
    return redirect(request.referrer or url_for("admin.users"))


@admin.route("/admin/verify_user/<int:user_id>", methods=["POST"])
def verify_user(user_id):
    user = db.get_or_404(User, user_id)
    if not user.is_verified:
        user.is_verified = True
        db.session.commit()
        flash(f"L'utilisateur {user.email} a été marqué comme vérifié.", "success")
    else:
        flash(f"L'utilisateur {user.email} est déjà vérifié.", "info")
    return redirect(request.referrer or url_for("admin.users"))


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
    return redirect(request.referrer or url_for("admin.users"))


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
    return redirect(request.referrer or url_for("admin.users"))


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
            active_page="coupons",
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
        active_page="coupons",
    )


@admin.route("/admin/livres")
def livres():
    q = request.args.get("q", "").strip()
    query = Book.query
    if q:
        query = query.filter(
            Book.title.ilike(f"%{q}%")
            | Book.author.ilike(f"%{q}%")
            | Book.isbn.ilike(f"%{q}%")
        )
    total_books = query.count()
    books_list = query.order_by(Book.id.desc()).limit(100).all()

    return render_template(
        "admin/livres.html",
        books=books_list,
        total_books=total_books,
        search_query=q,
        active_page="livres",
    )


@admin.route("/admin/eleves")
def eleves():
    q = request.args.get("q", "").strip()
    query = Student.query
    if q:
        query = query.filter(
            Student.name.ilike(f"%{q}%") | Student.firstname.ilike(f"%{q}%")
        )
    total_students = query.count()
    students_list = query.order_by(Student.id.desc()).limit(100).all()

    return render_template(
        "admin/eleves.html",
        students=students_list,
        total_students=total_students,
        search_query=q,
        active_page="eleves",
    )


@admin.route("/admin/parametres")
def parametres():
    stripe_configured = bool(os.getenv("STRIPE_SECRET_KEY"))
    mail_configured = bool(os.getenv("MAIL_USERNAME"))

    try:
        stripe_version = importlib.metadata.version("stripe")
    except importlib.metadata.PackageNotFoundError:
        stripe_version = "Non installé"

    try:
        flask_version = importlib.metadata.version("flask")
    except importlib.metadata.PackageNotFoundError:
        flask_version = "Non installé"

    system_info = {
        "python_version": sys.version.split(" ")[0],
        "flask_version": flask_version,
        "stripe_sdk_version": stripe_version,
        "database": str(db.engine.url),
        "stripe_configured": stripe_configured,
        "mail_configured": mail_configured,
        "max_free_students": config_plans.MAX_FREE_STUDENTS,
        "max_free_books": config_plans.MAX_FREE_BOOKS,
        "max_free_scans": config_plans.MAX_FREE_SCANS,
        "free_history_months": config_plans.FREE_HISTORY_MONTHS,
        "price_monthly": config_plans.PRICE_MONTHLY_AMOUNT,
        "price_yearly": config_plans.PRICE_YEARLY_AMOUNT,
    }

    return render_template(
        "admin/parametres.html",
        system_info=system_info,
        active_page="parametres",
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
    # Stats for audience counters, interactive matrix, and health dashboard
    now = datetime.now(timezone.utc)
    users_data = db.session.query(
        User.is_verified,
        User.newsletter_subscribed,
        User.plan,
        User.trial_ends_at,
        User.preferred_language,
        User.email,
    ).all()

    target_keys = ["verified_subscribed", "all_subscribed", "system_all"]
    plan_keys = ["all", "founder", "premium", "trial", "free"]
    lang_keys = ["all", "fr", "en", "de"]

    counts_matrix = {
        t: {p: {l: 0 for l in lang_keys} for p in plan_keys} for t in target_keys
    }

    subscribed_users = 0
    verified_users = 0
    verified_subscribed_users = 0
    unsubscribed_users = 0
    total_users = 0
    lang_distribution = {
        "fr": {"count": 0, "pct": 0},
        "en": {"count": 0, "pct": 0},
        "de": {"count": 0, "pct": 0},
    }

    for is_verified, subscribed, plan, trial_ends_at, pref_lang, email in users_data:
        total_users += 1
        if is_verified:
            verified_users += 1
        if subscribed:
            subscribed_users += 1
            if is_verified:
                verified_subscribed_users += 1
        else:
            unsubscribed_users += 1

        if not email:
            continue

        lang = pref_lang if pref_lang in ("fr", "en", "de") else "fr"
        if subscribed and lang in lang_distribution:
            lang_distribution[lang]["count"] += 1

        # Effective plan category for email targeting:
        if plan == "founder":
            user_plan = "founder"
        elif plan == "premium":
            user_plan = "premium"
        else:
            if trial_ends_at:
                end_dt = (
                    trial_ends_at.replace(tzinfo=timezone.utc)
                    if trial_ends_at.tzinfo is None
                    else trial_ends_at
                )
                if end_dt > now:
                    user_plan = "trial"
                else:
                    user_plan = "free"
            else:
                user_plan = "free"

        user_targets = ["system_all"]
        if subscribed:
            user_targets.append("all_subscribed")
            if is_verified:
                user_targets.append("verified_subscribed")

        for t in user_targets:
            # All plans
            counts_matrix[t]["all"]["all"] += 1
            counts_matrix[t]["all"][lang] += 1
            # Specific plan
            counts_matrix[t][user_plan]["all"] += 1
            counts_matrix[t][user_plan][lang] += 1

    active_rate = (
        round((subscribed_users / total_users * 100), 1) if total_users > 0 else 100.0
    )
    quality_rate = (
        round((verified_users / total_users * 100), 1) if total_users > 0 else 100.0
    )

    for l_key in ("fr", "en", "de"):
        lang_distribution[l_key]["pct"] = (
            round(lang_distribution[l_key]["count"] / subscribed_users * 100, 1)
            if subscribed_users > 0
            else 0
        )

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
    duplicate_target = "verified_subscribed"
    duplicate_plan = "all"
    if duplicate_id:
        try:
            duplicate_campaign = db.session.get(NewsletterCampaign, int(duplicate_id))
            if duplicate_campaign:
                if ":" in duplicate_campaign.target:
                    duplicate_target, duplicate_plan = duplicate_campaign.target.split(
                        ":", 1
                    )
                else:
                    duplicate_target = duplicate_campaign.target
                    duplicate_plan = "all"
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
        target_plan = request.form.get("target_plan", "all")
        target_lang = request.form.get("target_lang", "all")
        message_content = request.form.get("message")
        template_choice = request.form.get("template_choice", "newsletter.html")

        if not subject or not message_content:
            flash("Veuillez remplir le sujet et le message.", "error")
            return redirect(url_for("admin.emails"))

        # Build recipient query based on target, plan, and language selection
        query = User.query
        if target in ("verified_subscribed", "verified"):
            query = query.filter_by(is_verified=True, newsletter_subscribed=True)
        elif target in ("all_subscribed", "all"):
            query = query.filter_by(newsletter_subscribed=True)
        elif target == "system_all":
            pass
        else:
            query = query.filter_by(is_verified=True, newsletter_subscribed=True)

        # Plan filtering
        if target_plan == "founder":
            query = query.filter(User.plan == "founder")
        elif target_plan == "premium":
            query = query.filter(User.plan == "premium")
        elif target_plan == "trial":
            query = query.filter(
                User.plan == "free",
                User.trial_ends_at.is_not(None),
                User.trial_ends_at > now,
            )
        elif target_plan == "free":
            query = query.filter(
                User.plan == "free",
                (User.trial_ends_at.is_(None) | (User.trial_ends_at <= now)),
            )

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
        campaign_target = f"{target}:{target_plan}" if target_plan != "all" else target
        campaign = NewsletterCampaign(
            subject=subject,
            content=message_content,
            template=template_choice,
            target=campaign_target,
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
        duplicate_target=duplicate_target,
        duplicate_plan=duplicate_plan,
        target_lang_prefill=target_lang_prefill,
        active_page="emails",
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
        active_page="feedbacks",
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
