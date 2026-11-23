import glob
import importlib.metadata
import json
import logging
import os
import random
import re
import secrets
import string
import sys
import time
from datetime import UTC, datetime, timedelta
from threading import Thread

import markupsafe
import stripe
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_babel import force_locale
from flask_babel import gettext as _
from flask_login import current_user
from flask_mail import Message
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from . import config_plans, db, mail
from .email import send_email_verification
from .models import (
    Book,
    Feedback,
    Loan,
    NewsletterCampaign,
    NewsletterDelivery,
    Student,
    User,
)
from .query import delete_user_account

admin = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


@admin.before_request
def require_authelia_auth():
    """
    Défense en profondeur (FND-01) :
    Vérifie que la requête vers le panneau d'administration provient d'une session
    authentifiée par le reverse proxy Authelia (présence de Remote-User ou Remote-Email).
    Bypass automatique en mode TESTING ou DEBUG.
    """
    if current_app.config.get("TESTING") or current_app.debug:
        return

    remote_user = request.headers.get("Remote-User") or request.headers.get(
        "Remote-Email"
    )
    if not remote_user or not remote_user.strip():
        logger.warning(
            "Tentative d'accès non autorisé à %s sans en-tête d'authentification Authelia (IP: %s)",
            request.path,
            request.remote_addr,
        )
        abort(403)


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
    now = datetime.now(UTC)
    today = now.date()

    # 1. Gestion unifiée de la période (?range=7d|30d|12w|12m)
    range_arg = request.args.get("range", "").strip().lower()
    if range_arg in ("7d", "30d", "12w", "12m"):
        selected_range = range_arg
        session["admin_range"] = selected_range
    else:
        selected_range = session.get("admin_range", "30d")

    # 2. Interrupteur global « Exclure les comptes de test » (?exclude_tests=1|0)
    exclude_arg = request.args.get("exclude_tests")
    if exclude_arg is not None:
        exclude_tests = exclude_arg in ("1", "true", "True")
        session["admin_exclude_tests"] = exclude_tests
    else:
        exclude_tests = session.get("admin_exclude_tests", False)

    test_users_count = User.query.filter_by(is_test=True).count()

    # Requête de base pour les utilisateurs
    base_user_q = User.query
    if exclude_tests:
        base_user_q = base_user_q.filter(User.is_test.is_(False))

    total_users = base_user_q.count()
    active_users = base_user_q.filter_by(is_verified=True).count()
    unconfirmed_users = max(0, total_users - active_users)
    premium_users = base_user_q.filter_by(plan="premium").count()
    founder_users = base_user_q.filter_by(plan="founder").count()
    paying_or_founder_users = premium_users + founder_users
    trial_users = base_user_q.filter(User.trial_ends_at > now).count()
    free_users = max(0, total_users - paying_or_founder_users - trial_users)
    newsletter_subscribers = base_user_q.filter_by(newsletter_subscribed=True).count()

    if exclude_tests:
        total_books = (
            Book.query.join(User, Book.user_id == User.id)
            .filter(User.is_test.is_(False))
            .count()
        )
        total_students = (
            Student.query.join(User, Student.user_id == User.id)
            .filter(User.is_test.is_(False))
            .count()
        )
        total_loans = (
            Loan.query.join(Student, Loan.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .filter(User.is_test.is_(False))
            .count()
        )
        total_scans = (
            db.session.query(func.sum(User.free_scans_used))
            .filter(User.is_test.is_(False))
            .scalar()
            or 0
        )
    else:
        total_books = Book.query.count()
        total_students = Student.query.count()
        total_loans = Loan.query.count()
        total_scans = db.session.query(func.sum(User.free_scans_used)).scalar() or 0

    new_feedbacks = Feedback.query.filter_by(status="nouveau").count()
    total_feedbacks = Feedback.query.count()

    # Bloc « À traiter »
    pending_feedbacks = new_feedbacks
    max_scans_users_count = base_user_q.filter(
        User.free_scans_used >= config_plans.MAX_FREE_SCANS,
        User.plan.notin_(["founder", "premium"]),
    ).count()
    seven_days_later = now + timedelta(days=7)
    expiring_trials_count = base_user_q.filter(
        User.plan.notin_(["founder", "premium"]),
        User.trial_ends_at.isnot(None),
        User.trial_ends_at > now,
        User.trial_ends_at <= seven_days_later,
    ).count()
    total_to_process = pending_feedbacks + max_scans_users_count + expiring_trials_count
    to_process = {
        "total": total_to_process,
        "feedbacks": pending_feedbacks,
        "max_scans": max_scans_users_count,
        "expiring_trials": expiring_trials_count,
    }

    # Taux d'activation (utilisateurs ayant au moins 1 livre ou scans enregistrés)
    user_ids_with_books = (
        db.session.query(Book.user_id).filter(Book.user_id.isnot(None)).distinct()
    )
    activated_users_count = base_user_q.filter(
        (User.id.in_(user_ids_with_books)) | (User.free_scans_used > 0)
    ).count()
    activation_rate = (
        round((activated_users_count / total_users * 100), 1)
        if total_users > 0
        else 0.0
    )

    # 3. SaaS Métrique : Classes Actives Hebdomadaires (WAU)
    seven_days_ago_date = today - timedelta(days=7)
    wau_loan_q = (
        db.session.query(Student.user_id)
        .join(Loan, Loan.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .filter(
            (Loan.date_loan >= seven_days_ago_date)
            | (Loan.date_return >= seven_days_ago_date)
        )
    )
    if exclude_tests:
        wau_loan_q = wau_loan_q.filter(User.is_test.is_(False))
    wau_user_ids = {u[0] for u in wau_loan_q.distinct().all() if u[0]}
    wau_count = len(wau_user_ids)
    active_denom = active_users if active_users > 0 else total_users
    wau_rate = round((wau_count / active_denom * 100), 1) if active_denom > 0 else 0.0

    # 4. SaaS Métrique : Taux de Santé du Scan ISBN
    scanned_books_q = Book.query.filter(
        (Book.isbn.isnot(None)) | (Book.barcode.isnot(None))
    )
    if exclude_tests:
        scanned_books_q = scanned_books_q.join(User, Book.user_id == User.id).filter(
            User.is_test.is_(False)
        )
    scanned_books = scanned_books_q.all()
    scan_health_total = len(scanned_books)
    scan_health_complete = 0
    for b in scanned_books:
        has_title = bool(b.title and b.title.strip() and b.title != "Sans titre")
        has_author = bool(
            b.author
            and b.author.strip()
            and b.author not in ("Auteur inconnu", "Inconnu", "None")
        )
        has_image = bool(
            b.image_url and b.image_url.strip() and "default" not in b.image_url.lower()
        )
        if has_title and has_author and has_image:
            scan_health_complete += 1
    scan_health_incomplete = max(0, scan_health_total - scan_health_complete)
    scan_health_rate = (
        round((scan_health_complete / scan_health_total * 100), 1)
        if scan_health_total > 0
        else 0.0
    )

    # 5. SaaS Métrique : Radar à Paywalls (Conversion Freemium)
    paywall_users_q = base_user_q.filter(User.plan.notin_(["founder", "premium"])).all()
    paywall_prospects = []
    scan_threshold = int(config_plans.MAX_FREE_SCANS * 0.8)  # 24
    student_threshold = int(config_plans.MAX_FREE_STUDENTS * 0.8)  # 32
    book_threshold = int(config_plans.MAX_FREE_BOOKS * 0.8)  # 400
    nine_months_ago = today - timedelta(days=270)

    for u in paywall_users_q:
        alerts = []
        scans = u.free_scans_used or 0
        if scans >= scan_threshold:
            pct = round(scans / config_plans.MAX_FREE_SCANS * 100)
            alerts.append(
                {
                    "type": "scans",
                    "label": "Scans hebdo",
                    "detail": f"{scans}/{config_plans.MAX_FREE_SCANS} scans ({pct}%)",
                    "pct": pct,
                    "urgency": "danger"
                    if scans >= config_plans.MAX_FREE_SCANS
                    else "warning",
                }
            )
        st_count = len(u.students)
        if st_count >= student_threshold:
            pct = round(st_count / config_plans.MAX_FREE_STUDENTS * 100)
            alerts.append(
                {
                    "type": "students",
                    "label": "Élèves",
                    "detail": f"{st_count}/{config_plans.MAX_FREE_STUDENTS} élèves ({pct}%)",
                    "pct": pct,
                    "urgency": "danger"
                    if st_count >= config_plans.MAX_FREE_STUDENTS
                    else "warning",
                }
            )
        bk_count = len(u.books)
        if bk_count >= book_threshold:
            pct = round(bk_count / config_plans.MAX_FREE_BOOKS * 100)
            alerts.append(
                {
                    "type": "books",
                    "label": "Livres",
                    "detail": f"{bk_count}/{config_plans.MAX_FREE_BOOKS} livres ({pct}%)",
                    "pct": pct,
                    "urgency": "danger"
                    if bk_count >= config_plans.MAX_FREE_BOOKS
                    else "warning",
                }
            )
        oldest_loan = (
            db.session.query(func.min(Loan.date_loan))
            .join(Student, Loan.student_id == Student.id)
            .filter(Student.user_id == u.id)
            .scalar()
        )
        if oldest_loan and oldest_loan <= nine_months_ago:
            days_old = (today - oldest_loan).days
            months_old = round(days_old / 30.4, 1)
            alerts.append(
                {
                    "type": "history",
                    "label": "Historique",
                    "detail": f"Prêts de {months_old} mois (flou à {config_plans.FREE_HISTORY_MONTHS}m)",
                    "pct": min(
                        100, round(months_old / config_plans.FREE_HISTORY_MONTHS * 100)
                    ),
                    "urgency": "danger"
                    if months_old >= config_plans.FREE_HISTORY_MONTHS
                    else "warning",
                }
            )
        if alerts:
            paywall_prospects.append(
                {
                    "user": u,
                    "alerts": alerts,
                    "max_urgency": "danger"
                    if any(a["urgency"] == "danger" for a in alerts)
                    else "warning",
                }
            )

    recent_users = base_user_q.order_by(User.id.desc()).limit(5).all()
    recent_feedbacks = Feedback.query.order_by(Feedback.id.desc()).limit(5).all()

    # 6. Période & Slots unifiés pour les graphiques
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

    if selected_range == "7d":
        start_date = today - timedelta(days=6)
        num_slots = 7
        chart_labels = [
            (start_date + timedelta(days=i)).strftime("%d/%m") for i in range(7)
        ]
        get_slot_idx = lambda d: (
            (d - start_date).days if start_date <= d <= today else None
        )
    elif selected_range == "12w":
        current_monday = (now - timedelta(days=now.weekday())).date()
        start_monday = current_monday - timedelta(weeks=11)
        num_slots = 12
        chart_labels = [
            (start_monday + timedelta(weeks=w)).strftime("%d/%m") for w in range(12)
        ]

        def get_slot_idx(d):
            diff = (d - start_monday).days
            idx = diff // 7
            return idx if 0 <= idx < 12 else None
    elif selected_range == "12m":
        cur_year, cur_month = today.year, today.month
        month_slots = []
        for i in range(11, -1, -1):
            m = cur_month - i
            y = cur_year
            while m <= 0:
                m += 12
                y -= 1
            month_slots.append((y, m))
        slot_map = {slot: i for i, slot in enumerate(month_slots)}
        num_slots = 12
        chart_labels = [f"{month_names_fr[m]} {str(y)[2:]}" for (y, m) in month_slots]
        get_slot_idx = lambda d: slot_map.get((d.year, d.month))
    else:  # '30d' par défaut
        start_date = today - timedelta(days=29)
        num_slots = 30
        chart_labels = [
            (start_date + timedelta(days=i)).strftime("%d/%m") for i in range(30)
        ]
        get_slot_idx = lambda d: (
            (d - start_date).days if start_date <= d <= today else None
        )

    # Séries multi-métriques (Enseignants, Livres, Élèves, Prêts)
    chart_series = {
        "users": [0] * num_slots,
        "books": [0] * num_slots,
        "students": [0] * num_slots,
        "loans": [0] * num_slots,
    }

    # Agrégation des utilisateurs
    for u in base_user_q.all():
        if u.created_at:
            u_date = (
                u.created_at.date() if hasattr(u.created_at, "date") else u.created_at
            )
            idx = get_slot_idx(u_date)
            if idx is not None:
                chart_series["users"][idx] += 1

    # Agrégation des livres
    books_q = Book.query
    if exclude_tests:
        books_q = books_q.join(User, Book.user_id == User.id).filter(
            User.is_test.is_(False)
        )
    for b in books_q.all():
        b_dt = b.created_at or (b.user.created_at if b.user else None)
        if b_dt:
            b_date = b_dt.date() if hasattr(b_dt, "date") else b_dt
            idx = get_slot_idx(b_date)
            if idx is not None:
                chart_series["books"][idx] += 1

    # Agrégation des élèves
    students_q = Student.query
    if exclude_tests:
        students_q = students_q.join(User, Student.user_id == User.id).filter(
            User.is_test.is_(False)
        )
    for s in students_q.all():
        s_dt = s.created_at or (s.user.created_at if s.user else None)
        if s_dt:
            s_date = s_dt.date() if hasattr(s_dt, "date") else s_dt
            idx = get_slot_idx(s_date)
            if idx is not None:
                chart_series["students"][idx] += 1

    # Agrégation des prêts
    loans_q = Loan.query
    if exclude_tests:
        loans_q = (
            loans_q.join(Student, Loan.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .filter(User.is_test.is_(False))
        )
    for l in loans_q.all():
        if l.date_loan:
            idx = get_slot_idx(l.date_loan)
            if idx is not None:
                chart_series["loans"][idx] += 1

    chart_totals = {
        "users": sum(chart_series["users"]),
        "books": sum(chart_series["books"]),
        "students": sum(chart_series["students"]),
        "loans": sum(chart_series["loans"]),
    }

    # Rétrocompatibilité weekly_signups pour les tests existants
    total_signups_12w = sum(chart_series["users"])
    avg_signups_per_week = round(total_signups_12w / max(1, num_slots), 1)
    signups_weekly_trend = None
    if len(chart_series["users"]) >= 2 and chart_series["users"][-2] > 0:
        curr_val = chart_series["users"][-1]
        prev_val = chart_series["users"][-2]
        signups_weekly_trend = round(((curr_val - prev_val) / prev_val) * 100, 1)

    # 7. Métriques financières
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    stripe_connected = False
    currency = config_plans.DEFAULT_CURRENCY
    monthly_subs_count = 0
    yearly_subs_count = 0
    monthly_mrr = 0.0
    yearly_mrr = 0.0
    total_revenue_collected = 0.0

    revenue_chart_labels = chart_labels[:]
    revenue_chart_data = [0.0] * num_slots
    subs_chart_data = [0] * num_slots
    cancels_chart_data = [0] * num_slots

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

            # Flux complet via Stripe
            all_subs = stripe.Subscription.list(status="all", limit=100)
            for s in all_subs.data:
                if getattr(s, "created", None):
                    c_dt = datetime.fromtimestamp(s.created, tz=UTC).date()
                    idx = get_slot_idx(c_dt)
                    if idx is not None:
                        subs_chart_data[idx] += 1
                c_ts = getattr(s, "canceled_at", None) or getattr(s, "ended_at", None)
                if c_ts:
                    e_dt = datetime.fromtimestamp(c_ts, tz=UTC).date()
                    idx = get_slot_idx(e_dt)
                    if idx is not None:
                        cancels_chart_data[idx] += 1

            # Invoices payées
            invoices = stripe.Invoice.list(status="paid", limit=100)
            for inv in invoices.data:
                paid = round((inv.amount_paid or 0) / 100.0, 2)
                total_revenue_collected += paid
                inv_dt = datetime.fromtimestamp(inv.created, tz=UTC).date()
                idx = get_slot_idx(inv_dt)
                if idx is not None:
                    revenue_chart_data[idx] += paid
        except Exception as e:  # noqa: BLE001
            current_app.logger.warning(
                "Erreur de récupération des métriques Stripe : %s", e
            )
            stripe_connected = False

    # Fallback si Stripe non connecté
    if not stripe_connected or (
        monthly_subs_count == 0 and yearly_subs_count == 0 and premium_users > 0
    ):
        premium_db_users = base_user_q.filter_by(plan="premium").all()
        for u in premium_db_users:
            if u.subscription_type == "yearly":
                yearly_subs_count += 1
            else:
                monthly_subs_count += 1

        monthly_mrr = monthly_subs_count * config_plans.PRICE_MONTHLY_AMOUNT
        yearly_mrr = yearly_subs_count * (config_plans.PRICE_YEARLY_AMOUNT / 12.0)
        if total_revenue_collected == 0:
            total_revenue_collected = (
                monthly_subs_count * config_plans.PRICE_MONTHLY_AMOUNT
            ) + (yearly_subs_count * config_plans.PRICE_YEARLY_AMOUNT)
            revenue_chart_data[-1] = round(monthly_mrr + (yearly_mrr * 12.0), 2)

    if not stripe_connected or (
        sum(subs_chart_data) == 0 and sum(cancels_chart_data) == 0
    ):
        for u in base_user_q.all():
            if (u.plan in ("premium", "founder") or u.stripe_price_id) and u.created_at:
                u_c = (
                    u.created_at.date()
                    if hasattr(u.created_at, "date")
                    else u.created_at
                )
                idx = get_slot_idx(u_c)
                if idx is not None:
                    subs_chart_data[idx] += 1
            if u.subscription_end_at or u.stripe_subscription_status == "canceled":
                end_dt = u.subscription_end_at or u.created_at
                if end_dt:
                    u_e = end_dt.date() if hasattr(end_dt, "date") else end_dt
                    idx = get_slot_idx(u_e)
                    if idx is not None:
                        cancels_chart_data[idx] += 1

    total_mrr = round(monthly_mrr + yearly_mrr, 2)
    total_arr = round(total_mrr * 12.0, 2)
    total_revenue_collected = round(total_revenue_collected, 2)
    revenue_chart_data = [round(v, 2) for v in revenue_chart_data]
    active_subscriptions_count = monthly_subs_count + yearly_subs_count

    total_new_subs = sum(subs_chart_data)
    total_cancels = sum(cancels_chart_data)
    cancels_neg_data = [-c for c in cancels_chart_data]
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
        "activated_users": activated_users_count,
        "activation_rate": activation_rate,
        "total_signups_12w": total_signups_12w,
        "avg_signups_per_week": avg_signups_per_week,
        "signups_weekly_trend": signups_weekly_trend,
        "wau_count": wau_count,
        "wau_rate": wau_rate,
    }

    return render_template(
        "admin/index.html",
        stats=stats,
        to_process=to_process,
        selected_range=selected_range,
        exclude_tests=exclude_tests,
        test_users_count=test_users_count,
        chart_labels=chart_labels,
        chart_series=chart_series,
        chart_totals=chart_totals,
        wau_count=wau_count,
        wau_rate=wau_rate,
        scan_health_rate=scan_health_rate,
        scan_health_total=scan_health_total,
        scan_health_complete=scan_health_complete,
        scan_health_incomplete=scan_health_incomplete,
        paywall_prospects=paywall_prospects,
        weekly_signups_labels=chart_labels,
        weekly_signups_data=chart_series["users"],
        recent_users=recent_users,
        recent_feedbacks=recent_feedbacks,
        chart_signups_labels=chart_labels,
        chart_signups_data=chart_series["users"],
        plans_distribution=plans_distribution,
        financial_stats=financial_stats,
        subscriptions_type_distribution=subscriptions_type_distribution,
        revenue_chart_labels=revenue_chart_labels,
        revenue_chart_data=revenue_chart_data,
        sub_flow_stats=sub_flow_stats,
        subs_chart_data=subs_chart_data,
        cancels_chart_data=cancels_neg_data,
        active_page="dashboard",
    )


@admin.route("/admin/utilisateurs/<int:user_id>/toggle-test", methods=["POST"])
def toggle_user_test(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.is_test = not bool(user.is_test)
    db.session.commit()
    msg = (
        f"Le compte {user.email} est désormais marqué comme compte de test."
        if user.is_test
        else f"Le compte {user.email} est désormais un compte standard."
    )
    flash(msg, "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


def _get_filtered_users_query(args):
    now = datetime.now(UTC)
    q = args.get("q", "").strip()
    plan_filter = args.get("plan", "").strip().lower()
    status_filter = (args.get("status") or args.get("statut") or "").strip().lower()
    scans_filter = (args.get("scans") or args.get("scans_min") or "").strip().lower()
    trial_filter = args.get("trial", "").strip().lower()
    activated_filter = args.get("activated", "").strip().lower()
    newsletter_filter = args.get("newsletter", "").strip().lower()
    inactif_30j = args.get("inactif_30j", "").strip().lower()

    query = User.query
    filter_descriptions = []

    # 0. Recherche texte (nom ou email)
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(User.name.ilike(search_pattern), User.email.ilike(search_pattern))
        )
        filter_descriptions.append(f"Recherche : « {q} »")

    # 1. Filtre par formule
    if plan_filter:
        if plan_filter in ("premium", "payant"):
            query = query.filter(User.plan == "premium")
            filter_descriptions.append("Formule : Premium")
        elif plan_filter == "founder":
            query = query.filter(User.plan == "founder")
            filter_descriptions.append("Formule : Membres Fondateurs")
        elif plan_filter == "paying":
            query = query.filter(User.plan.in_(["premium", "founder"]))
            filter_descriptions.append("Formule : Payants & Fondateurs")
        elif plan_filter == "trial":
            query = query.filter(
                User.plan.notin_(["premium", "founder"]),
                User.trial_ends_at.isnot(None),
                User.trial_ends_at > now,
            )
            filter_descriptions.append("Formule : En période d'essai")
        elif plan_filter in ("free", "gratuit"):
            query = query.filter(
                User.plan.notin_(["premium", "founder"]),
                (User.trial_ends_at.is_(None) | (User.trial_ends_at <= now)),
            )
            filter_descriptions.append("Formule : Gratuit")

    # 2. Filtre par statut de vérification email
    if status_filter:
        if status_filter in ("verified", "verifie", "actif"):
            query = query.filter(User.is_verified.is_(True))
            filter_descriptions.append("Statut : Vérifié")
        elif status_filter in ("unverified", "non_verifie", "en_attente"):
            query = query.filter(User.is_verified.is_(False))
            filter_descriptions.append("Statut : En attente")
        elif status_filter in ("test", "is_test"):
            query = query.filter(User.is_test.is_(True))
            filter_descriptions.append("Statut : Comptes de test")

    # 3. Filtre par quota de scans
    if scans_filter:
        if scans_filter == "max":
            query = query.filter(
                User.free_scans_used >= config_plans.MAX_FREE_SCANS,
                User.plan.notin_(["founder", "premium"]),
            )
            filter_descriptions.append(
                f"Scans au maximum (≥ {config_plans.MAX_FREE_SCANS} scans / semaine)"
            )
        elif scans_filter.isdigit():
            min_scans = int(scans_filter)
            query = query.filter(User.free_scans_used >= min_scans)
            filter_descriptions.append(f"Scans ≥ {min_scans}")

    # 4. Filtre par période d'essai expirant bientôt
    if trial_filter in ("expiring", "bientot"):
        seven_days = now + timedelta(days=7)
        query = query.filter(
            User.plan.notin_(["founder", "premium"]),
            User.trial_ends_at.isnot(None),
            User.trial_ends_at > now,
            User.trial_ends_at <= seven_days,
        )
        filter_descriptions.append("Essais expirant dans les 7 prochains jours")

    # 5. Filtre par activation
    if activated_filter:
        user_ids_with_books = (
            db.session.query(Book.user_id).filter(Book.user_id.isnot(None)).distinct()
        )
        if activated_filter in ("1", "true", "yes"):
            query = query.filter(
                (User.id.in_(user_ids_with_books)) | (User.free_scans_used > 0)
            )
            filter_descriptions.append("Comptes activés (≥ 1 livre ou scans)")
        elif activated_filter in ("0", "false", "no"):
            query = query.filter(
                ~User.id.in_(user_ids_with_books),
                User.free_scans_used == 0,
            )
            filter_descriptions.append("Comptes non activés (0 livre et 0 scan)")

    # 6. Filtre Newsletter
    if newsletter_filter:
        if newsletter_filter in ("1", "true", "yes", "oui", "sub"):
            query = query.filter(User.newsletter_subscribed.is_(True))
            filter_descriptions.append("Newsletter : Abonnés")
        elif newsletter_filter in ("0", "false", "no", "non", "unsub"):
            query = query.filter(User.newsletter_subscribed.is_(False))
            filter_descriptions.append("Newsletter : Non abonnés")

    # 7. Exclusion des comptes de test
    if args.get("exclude_tests") in ("1", "true", "True"):
        query = query.filter(User.is_test.is_(False))
        filter_descriptions.append("Exclure les comptes de test")

    # 7. Filtre inactifs depuis > 30 jours
    if inactif_30j in ("1", "true", "yes", "oui"):
        thirty_days_ago = now - timedelta(days=30)
        query = query.filter(
            User.created_at <= thirty_days_ago,
            User.free_scans_used == 0,
        )
        filter_descriptions.append("Inactifs (> 30 jours)")

    # Tri optionnel
    sort_col = args.get("sort", "id")
    sort_dir = args.get("dir", "desc")
    if sort_col == "name":
        order_expr = User.name.asc() if sort_dir == "asc" else User.name.desc()
    elif sort_col == "scans":
        order_expr = (
            User.free_scans_used.asc()
            if sort_dir == "asc"
            else User.free_scans_used.desc()
        )
    elif sort_col == "created_at":
        order_expr = (
            User.created_at.asc() if sort_dir == "asc" else User.created_at.desc()
        )
    else:
        order_expr = User.id.asc() if sort_dir == "asc" else User.id.desc()

    query = query.order_by(order_expr)
    return query, filter_descriptions


@admin.route("/admin/utilisateurs")
def users():
    query, filter_descriptions = _get_filtered_users_query(request.args)
    users_list = query.all()
    total_users_count = User.query.count()
    active_filter_label = (
        " • ".join(filter_descriptions) if filter_descriptions else None
    )

    return render_template(
        "admin/users.html",
        users=users_list,
        total_count=total_users_count,
        filtered_count=len(users_list),
        active_filter_label=active_filter_label,
        active_page="users",
    )


@admin.route("/admin/utilisateurs/export")
@admin.route("/admin/users/export")
def export_users():
    import csv
    import io

    query, _ = _get_filtered_users_query(request.args)
    users_list = query.all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "Nom",
            "Email",
            "Date d'inscription",
            "Formule",
            "Statut",
            "Livres",
            "Élèves",
            "Scans cette semaine",
            "Newsletter",
            "Client Stripe",
        ]
    )

    for u in users_list:
        writer.writerow(
            [
                u.name or "Sans nom",
                u.email,
                u.created_at.strftime("%d/%m/%Y %H:%M") if u.created_at else "",
                u.effective_plan if hasattr(u, "effective_plan") else u.plan,
                "Vérifié" if u.is_verified else "En attente",
                len(u.books) if hasattr(u, "books") else 0,
                len(u.students) if hasattr(u, "students") else 0,
                u.free_scans_used or 0,
                "Oui" if u.newsletter_subscribed else "Non",
                u.stripe_customer_id or "",
            ]
        )

    csv_data = output.getvalue().encode("utf-8-sig")
    now_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=utilisateurs_{now_str}.csv"
        },
    )


@admin.route("/admin/utilisateurs/<int:user_id>")
@admin.route("/admin/users/<int:user_id>")
def user_detail(user_id):
    user = db.get_or_404(User, user_id)
    user_books = Book.query.filter_by(user_id=user.id).order_by(Book.id.desc()).all()
    user_students = (
        Student.query.filter_by(user_id=user.id).order_by(Student.name.asc()).all()
    )
    loans_count = Loan.query.join(Book).filter(Book.user_id == user.id).count()
    active_loans_count = (
        Loan.query.join(Book)
        .filter(Book.user_id == user.id, Loan.date_return.is_(None))
        .count()
    )

    return render_template(
        "admin/user_detail.html",
        user=user,
        books=user_books,
        students=user_students,
        loans_count=loans_count,
        active_loans_count=active_loans_count,
        active_page="users",
    )


@admin.route("/admin/users/<int:user_id>/resend-confirmation", methods=["POST"])
def admin_resend_confirmation(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_verified:
        flash("Ce compte est déjà vérifié.", "info")
    else:
        try:
            send_email_verification(user)
            flash(
                f"E-mail de confirmation renvoyé avec succès à {user.email}.", "success"
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Erreur renvoi email confirmation : %s", e)
            flash("Erreur lors de l'envoi de l'e-mail de confirmation.", "danger")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin.route("/admin/users/<int:user_id>/change-plan", methods=["POST"])
def admin_change_plan(user_id):
    user = db.get_or_404(User, user_id)
    new_plan = request.form.get("plan", "").strip().lower()
    scans_str = request.form.get("scans", "").strip()

    if new_plan in ("free", "trial", "premium", "founder"):
        if new_plan == "trial":
            user.trial_ends_at = datetime.now(UTC) + timedelta(days=14)
            user.plan = "free"
        else:
            user.plan = new_plan
            if new_plan != "trial":
                user.trial_ends_at = None

    if scans_str.isdigit():
        user.free_scans_used = max(0, int(scans_str))

    db.session.commit()
    flash(f"Formule et quotas mis à jour pour {user.email}.", "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


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
    delete_user_account(user)
    flash(
        f"Le compte {email} a été supprimé. Les livres avec ISBN ont été conservés dans le catalogue collaboratif.",
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
            user.trial_ends_at = datetime.now(UTC) + timedelta(days=days)
        else:
            # trial_days = 0 → gratuit immédiat, on efface la date d'essai
            user.trial_ends_at = None
        user.trial_reminder_sent = False

    # Surcharge de trial_ends_at pour les plans free/founder si trial_days > 0
    if new_plan in ["free", "founder"] and trial_days.isdigit() and int(trial_days) > 0:
        user.trial_ends_at = datetime.now(UTC) + timedelta(days=int(trial_days))

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

        # Rétrocompatibilité et liaison complète du coupon pour l'affichage dans le template
        coupons_map = {c.id: c for c in coupons_list}
        for p in promos_list:
            c = getattr(p, "coupon", None)
            if not c and hasattr(p, "promotion") and hasattr(p.promotion, "coupon"):
                c = p.promotion.coupon
            if isinstance(c, str):
                c = coupons_map.get(c)
            p.coupon = c
            if c:
                p.linked_coupon_id = getattr(c, "id", None)
                p.coupon_percent_off = getattr(c, "percent_off", None)
                p.coupon_amount_off = getattr(c, "amount_off", None)
                p.coupon_currency = getattr(c, "currency", "chf")
                p.coupon_duration = getattr(c, "duration", None)
                p.coupon_duration_in_months = getattr(c, "duration_in_months", None)
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

    db_url_str = str(db.engine.url)
    if "sqlite" in db_url_str.lower():
        clean = db_url_str.replace("sqlite:///", "")
        db_file = os.path.basename(clean) or "app.db"
        if db_file == ":memory:":
            db_display = "SQLite (En mémoire)"
        else:
            db_display = f"SQLite ({db_file})"
    else:
        db_display = db.engine.name.capitalize()

    # Détection de la date de dernière sauvegarde
    import tempfile

    last_backup_date = None
    backup_meta_path = os.path.join(current_app.instance_path, "last_backup.json")
    if os.path.exists(backup_meta_path):
        try:
            with open(backup_meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                iso_val = data.get("timestamp")
                if iso_val:
                    last_backup_date = datetime.fromisoformat(iso_val).strftime(
                        "%d/%m/%Y à %H:%M"
                    )
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    if not last_backup_date:
        temp_dir = tempfile.gettempdir()
        backups = glob.glob(os.path.join(temp_dir, "bibliotheque_backup_*.db"))
        if backups:
            newest = max(backups, key=os.path.getmtime)
            mtime = datetime.fromtimestamp(os.path.getmtime(newest), UTC)
            last_backup_date = mtime.strftime("%d/%m/%Y à %H:%M")

    system_info = {
        "python_version": sys.version.split(" ")[0],
        "flask_version": flask_version,
        "stripe_sdk_version": stripe_version,
        "database": db_display,
        "last_backup_date": last_backup_date,
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


@admin.route("/admin/backup-db")
def backup_db():
    import sqlite3
    import tempfile

    db_uri = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if not db_uri.startswith("sqlite"):
        flash(
            "La sauvegarde directe n'est disponible que pour les bases de données SQLite.",
            "warning",
        )
        return redirect(url_for("admin.parametres"))

    clean_path = db_uri.replace("sqlite:///", "")
    if clean_path.startswith("/") or (len(clean_path) > 2 and clean_path[1] == ":"):
        db_path = clean_path
    else:
        db_path = os.path.join(current_app.instance_path, clean_path)
        if not os.path.exists(db_path):
            db_path = os.path.join(current_app.root_path, "..", clean_path)
        if not os.path.exists(db_path):
            db_path = os.path.abspath(clean_path)

    if not os.path.exists(db_path):
        flash(f"Fichier de base de données introuvable ({clean_path}).", "danger")
        return redirect(url_for("admin.parametres"))

    temp_dir = tempfile.gettempdir()
    now_utc = datetime.now(UTC)
    timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"bibliotheque_backup_{timestamp}.db"
    backup_path = os.path.join(temp_dir, backup_filename)

    try:
        src_conn = sqlite3.connect(db_path)
        dst_conn = sqlite3.connect(backup_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.error("Erreur de sauvegarde base de données : %s", e)
        flash(f"Erreur lors de la création de la sauvegarde : {e}", "danger")
        return redirect(url_for("admin.parametres"))

    # Enregistrer la date de dernière sauvegarde
    try:
        os.makedirs(current_app.instance_path, exist_ok=True)
        backup_meta_path = os.path.join(current_app.instance_path, "last_backup.json")
        with open(backup_meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": now_utc.isoformat(),
                    "filename": backup_filename,
                },
                f,
            )
    except OSError:
        pass

    return send_file(
        backup_path,
        as_attachment=True,
        download_name=backup_filename,
        mimetype="application/x-sqlite3",
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
                    delivery.sent_at = datetime.now(UTC)
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
    now = datetime.now(UTC)
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
                    trial_ends_at.replace(tzinfo=UTC)
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

        # Si le texte saisi est en markdown / texte brut sans balises HTML de structure, conversion automatique
        if message_content and not re.search(
            r"<\s*(?:p|div|table|h[1-6]|ul|ol)\b", message_content, re.IGNORECASE
        ):
            import markdown

            message_content = markdown.markdown(message_content, extensions=["nl2br"])

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

        if action == "send_test":
            test_email = (
                getattr(current_user, "email", None)
                or os.getenv("MAIL_USERNAME")
                or "contact@livresenclasse.com"
            )
            demo_pseudo = getattr(current_user, "name", None) or "Admin"
            test_sub = f"[TEST] {replace_pseudo(subject, demo_pseudo, is_html=False)}"
            test_msg = replace_pseudo(message_content, demo_pseudo, is_html=True)
            preview_unsub = url_for(
                "auth.unsubscribe",
                token="demo-test-token",
                user_id=getattr(current_user, "id", 0) or 0,
                _external=True,
            )
            prev_lang = target_lang if target_lang in ("fr", "en", "de") else "fr"
            with force_locale(prev_lang):
                html_body = render_template(
                    template_path,
                    content=test_msg,
                    subject=test_sub,
                    unsubscribe_url=preview_unsub,
                    feedback_idea_url=feedback_idea_url,
                    feedback_bug_url=feedback_bug_url,
                    reglage_url=reglage_url,
                    tracking_pixel_url=None,
                    user_name=demo_pseudo,
                )
            sender = os.getenv("MAIL_USERNAME") or "contact@livresenclasse.com"
            try:
                msg = Message(
                    test_sub,
                    sender=sender,
                    recipients=[test_email],
                    reply_to=sender,
                )
                msg.html = html_body
                text_body = re.sub(r"<[^>]+>", " ", test_msg)
                text_body = re.sub(r"\s+", " ", text_body).strip()
                msg.body = f"{test_sub}\n\n{text_body}"
                mail.send(msg)
                flash(
                    f"E-mail de test envoyé avec succès à {test_email} !",
                    "success",
                )
            except Exception as e:  # noqa: BLE001
                flash(f"Erreur lors de l'envoi du test : {e}", "danger")
            return redirect(url_for("admin.emails"))

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
        "depart": Feedback.query.filter_by(category="depart").count(),
        "bug": Feedback.query.filter_by(category="bug").count(),
        "suggestion": Feedback.query.filter_by(category="suggestion").count(),
        "general": Feedback.query.filter_by(category="general").count(),
    }

    # Statistiques et distribution des motifs de départ
    departure_reasons_def = [
        ("too_expensive", "Tarif trop élevé / cher", "#ef4444"),
        ("free_limits", "Quotas gratuit limités", "#f59e0b"),
        ("no_longer_needed", "Plus d'utilité / Fin d'année", "#3b82f6"),
        ("missing_features", "Fonctions manquantes", "#8b5cf6"),
        ("too_complex", "Trop complexe", "#ec4899"),
        ("other", "Autre raison", "#64748b"),
    ]

    all_departures = Feedback.query.filter_by(category="depart").all()
    total_departures = len(all_departures)

    reason_counts = {key: 0 for key, _, _ in departure_reasons_def}
    for dep in all_departures:
        r = dep.departure_reason
        if r in reason_counts:
            reason_counts[r] += 1
        else:
            reason_counts["other"] += 1

    chart_departure_labels = [label for _, label, _ in departure_reasons_def]
    chart_departure_data = [reason_counts[key] for key, _, _ in departure_reasons_def]
    chart_departure_colors = [color for _, _, color in departure_reasons_def]

    top_reason_key = None
    top_reason_count = 0
    if total_departures > 0:
        sorted_reasons = sorted(
            reason_counts.items(), key=lambda item: item[1], reverse=True
        )
        top_reason_key, top_reason_count = sorted_reasons[0]

    top_reason_label = next(
        (label for k, label, _ in departure_reasons_def if k == top_reason_key), "Aucun"
    )
    top_reason_pct = (
        round((top_reason_count / total_departures * 100), 1)
        if total_departures > 0
        else 0
    )

    return render_template(
        "admin/feedbacks.html",
        feedbacks=feedbacks_list,
        counts=counts,
        current_status=status_filter,
        current_category=category_filter,
        active_page="feedbacks",
        total_departures=total_departures,
        top_reason_label=top_reason_label,
        top_reason_count=top_reason_count,
        top_reason_pct=top_reason_pct,
        chart_departure_labels=chart_departure_labels,
        chart_departure_data=chart_departure_data,
        chart_departure_colors=chart_departure_colors,
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


@admin.route("/admin/feedback/<int:feedback_id>/note", methods=["POST"])
def update_feedback_note(feedback_id):
    fb = db.get_or_404(Feedback, feedback_id)
    fb.admin_note = request.form.get("admin_note", "").strip() or None
    db.session.commit()
    flash("Note interne enregistrée.", "success")
    return redirect(url_for("admin.feedbacks"))


@admin.route("/admin/feedback/<int:feedback_id>/delete", methods=["POST"])
def delete_feedback(feedback_id):
    fb = db.get_or_404(Feedback, feedback_id)
    db.session.delete(fb)
    db.session.commit()
    flash("Retour supprimé avec succès.", "success")
    return redirect(url_for("admin.feedbacks"))
