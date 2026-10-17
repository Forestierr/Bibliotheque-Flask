# subscription.py
import logging
import os
import threading
from datetime import UTC, datetime, timedelta
from functools import wraps

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
from flask_babel import gettext as _
from flask_login import current_user, login_required

from . import csrf, db
from .config_plans import (
    DEFAULT_CURRENCY,
    FREE_HISTORY_MONTHS,
    MAX_FREE_BOOKS,
    MAX_FREE_SCANS,
    MAX_FREE_STUDENTS,
    PRICE_MONTHLY_AMOUNT,
    PRICE_YEARLY_AMOUNT,
    TRIAL_PERIOD_DAYS,
)
from .email import send_html_email
from .models import User

logger = logging.getLogger(__name__)

subscription = Blueprint("subscription", __name__)
webhook_bp = Blueprint("webhook", __name__)


def premium_required(f):
    """Décorateur vérifiant que l'utilisateur dispose d'un accès Premium ou Fondateur."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_premium:
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
            ):
                return (
                    jsonify(
                        {
                            "error": "premium_required",
                            "message": _(
                                "Cette fonctionnalité nécessite un abonnement Premium."
                            ),
                        }
                    ),
                    403,
                )
            flash(
                _("Cette fonctionnalité est réservée aux membres Premium."), "warning"
            )
            return redirect(url_for("subscription.tarifs"))
        return f(*args, **kwargs)

    return decorated_function


@subscription.route("/tarifs")
def tarifs():
    """Page publique présentant les offres, les fonctionnalités et les tarifs."""
    return render_template(
        "subscription/tarifs.html",
        currency=DEFAULT_CURRENCY,
        price_monthly=PRICE_MONTHLY_AMOUNT,
        price_yearly=PRICE_YEARLY_AMOUNT,
        max_students=MAX_FREE_STUDENTS,
        max_books=MAX_FREE_BOOKS,
        max_scans=MAX_FREE_SCANS,
        history_months=FREE_HISTORY_MONTHS,
        trial_days=TRIAL_PERIOD_DAYS,
    )


@subscription.route("/paiement")
def paiement():
    """Page de récapitulatif de commande avant la redirection Stripe Checkout."""
    plan_type = request.args.get("plan_type") or request.args.get("plan", "yearly")
    if plan_type.lower() in ("monthly", "mensuel"):
        plan_type = "monthly"
    else:
        plan_type = "yearly"

    return render_template(
        "subscription/paiement.html",
        plan_type=plan_type,
        currency=DEFAULT_CURRENCY,
        price_monthly=PRICE_MONTHLY_AMOUNT,
        price_yearly=PRICE_YEARLY_AMOUNT,
    )


@subscription.route("/subscription/create-checkout-session", methods=["POST", "GET"])
@login_required
def create_checkout_session():
    """Génère une session Stripe Checkout pour un abonnement mensuel ou annuel."""
    plan_type = request.form.get("plan_type") or request.args.get("plan_type", "yearly")

    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_secret:
        logger.warning("STRIPE_SECRET_KEY non configurée. Redirection mode simulation.")
        flash(
            _(
                "Le service de paiement Stripe est en cours de configuration. Contactez l'administrateur."
            ),
            "info",
        )
        return redirect(url_for("subscription.tarifs"))

    stripe.api_key = stripe_secret

    price_id = (
        (os.getenv("STRIPE_PRICE_ID_YEARLY") or os.getenv("STRIPE_PRICE_YEARLY"))
        if plan_type == "yearly"
        else (os.getenv("STRIPE_PRICE_ID_MONTHLY") or os.getenv("STRIPE_PRICE_MONTHLY"))
    )

    # Paramètres de base de la session (Managed Payments géré par le Dashboard Stripe)
    checkout_params = {
        "mode": "subscription",
        "allow_promotion_codes": True,
        "client_reference_id": str(current_user.id),
        "metadata": {
            "user_id": str(current_user.id),
            "plan_type": plan_type,
        },
        "success_url": url_for("subscription.success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": url_for("subscription.cancel", _external=True),
    }

    # Réutiliser le client Stripe s'il existe déjà
    if current_user.stripe_customer_id:
        checkout_params["customer"] = current_user.stripe_customer_id
    else:
        checkout_params["customer_email"] = current_user.email

    if price_id:
        checkout_params["line_items"] = [{"price": price_id, "quantity": 1}]
    else:
        # Configuration dynamique si price_id absent des variables d'environnement
        unit_amount = (
            int(PRICE_YEARLY_AMOUNT * 100)
            if plan_type == "yearly"
            else int(PRICE_MONTHLY_AMOUNT * 100)
        )
        interval = "year" if plan_type == "yearly" else "month"
        checkout_params["line_items"] = [
            {
                "price_data": {
                    "currency": DEFAULT_CURRENCY.lower(),
                    "product_data": {
                        "name": f"Abonnement Livres en Classe ({'Annuel' if plan_type == 'yearly' else 'Mensuel'})",
                        "description": "Accès complet et illimité à toutes les fonctionnalités pour enseignants.",
                    },
                    "unit_amount": unit_amount,
                    "recurring": {"interval": interval},
                },
                "quantity": 1,
            }
        ]

    try:
        session = stripe.checkout.Session.create(**checkout_params)
        return redirect(session.url, code=303)
    except Exception:
        logger.exception("Erreur lors de la création de session Stripe Checkout")
        flash(
            _(
                "Une erreur est survenue lors de l'accès au paiement. Veuillez réessayer ultérieurement ou contacter le support."
            ),
            "error",
        )
        return redirect(url_for("subscription.tarifs"))


@subscription.route(
    "/portail-abonne", methods=["GET", "POST"], endpoint="portail_abonne"
)
@subscription.route("/subscription/portal", methods=["GET", "POST"], endpoint="portal")
@login_required
def portail_abonne():
    """Redirige l'utilisateur vers le Stripe Customer Portal pour gérer sa carte ou résilier."""
    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_secret or not current_user.stripe_customer_id:
        flash(
            _(
                "Aucun abonnement Stripe actif n'est associé à votre compte pour le moment."
            ),
            "info",
        )
        return redirect(url_for("auth.reglage"))

    stripe.api_key = stripe_secret
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for("auth.reglage", _external=True),
        )
        return redirect(portal_session.url, code=303)
    except Exception:
        logger.exception("Erreur Stripe Portal")
        flash(
            _(
                "Impossible d'accéder au portail de gestion pour le moment. Veuillez réessayer ultérieurement."
            ),
            "error",
        )
        return redirect(url_for("auth.reglage"))


# Alias rétrocompatible
portal = portail_abonne


@subscription.route("/subscription/success")
@login_required
def success():
    """Page de confirmation et de félicitations post-paiement."""
    session_id = request.args.get("session_id")
    # Synchronisation immédiate si session_id présent
    if session_id and os.getenv("STRIPE_SECRET_KEY"):
        try:
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            session = stripe.checkout.Session.retrieve(session_id)
            session_data = session.to_dict() if hasattr(session, "to_dict") else session
            if (
                session_data.get("payment_status") == "paid"
                or session_data.get("status") == "complete"
            ):
                current_user.plan = "premium"
                current_user.stripe_subscription_status = "active"
                current_user.subscription_end_at = None
                if session_data.get("customer"):
                    current_user.stripe_customer_id = str(session_data["customer"])
                if session_data.get("subscription"):
                    current_user.stripe_subscription_id = str(
                        session_data["subscription"]
                    )
                # Récupérer le type d'abonnement (mensuel/annuel) depuis les métadonnées de session
                plan_type = (session_data.get("metadata") or {}).get("plan_type")
                if plan_type and not current_user.stripe_price_id:
                    current_user.stripe_price_id = plan_type
                db.session.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Erreur vérification session_id success : %s", e)

    return render_template("subscription/success.html")


@subscription.route("/subscription/cancel")
def cancel():
    """Page d'annulation (aucun débit effectué)."""
    return render_template("subscription/cancel.html")


@webhook_bp.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    """Endpoint recevant les événements Stripe sécurisés par signature."""
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    event = None
    if endpoint_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError as e:
            logger.error("Payload webhook Stripe invalide : %s", e)
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError as e:
            logger.error("Signature webhook Stripe invalide : %s", e)
            return jsonify({"error": "Invalid signature"}), 400
    else:
        try:
            event = request.get_json(force=True)
        except (ValueError, TypeError):
            return jsonify({"error": "No JSON payload"}), 400

    if hasattr(event, "to_dict"):
        event = event.to_dict()

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})
    if hasattr(data_object, "to_dict"):
        data_object = data_object.to_dict()

    logger.info("Webhook Stripe reçu : %s", event_type)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data_object)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data_object)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data_object)
    elif event_type == "invoice.payment_failed":
        _handle_invoice_payment_failed(data_object)

    return jsonify({"status": "success"}), 200


def _handle_checkout_completed(session):
    if hasattr(session, "to_dict"):
        session = session.to_dict()
    client_ref_id = session.get("client_reference_id")
    user_id = client_ref_id or session.get("metadata", {}).get("user_id")

    user = None
    if user_id:
        try:
            user = db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            user = None

    if not user:
        email = session.get("customer_email") or (
            session.get("customer_details") or {}
        ).get("email")
        if email:
            user = User.query.filter_by(email=email).first()

    if not user:
        logger.warning(
            "Webhook checkout.session.completed ignoré : aucun utilisateur trouvé (user_id=%s, email=%s)",
            user_id,
            session.get("customer_email")
            or (session.get("customer_details") or {}).get("email"),
        )
        return

    if user:
        customer_id = str(session.get("customer")) if session.get("customer") else None
        subscription_id = (
            str(session.get("subscription")) if session.get("subscription") else None
        )

        # Idempotence : vérifier si l'événement a déjà été appliqué
        if (
            user.plan == "premium"
            and user.stripe_subscription_status == "active"
            and (not customer_id or user.stripe_customer_id == customer_id)
            and (not subscription_id or user.stripe_subscription_id == subscription_id)
        ):
            logger.info(
                "Webhook checkout.session.completed déjà traité pour l'utilisateur %s (idempotent)",
                user.id,
            )
            return

        user.plan = "premium"
        user.stripe_subscription_status = "active"
        user.subscription_end_at = None
        if customer_id:
            user.stripe_customer_id = customer_id
        if subscription_id:
            user.stripe_subscription_id = subscription_id
        plan_type = session.get("metadata", {}).get("plan_type")
        if plan_type:
            user.stripe_price_id = plan_type
        db.session.commit()
        logger.info(
            "Utilisateur %s activé en Premium via checkout.session.completed",
            user.id,
        )


def _handle_subscription_updated(sub):
    if hasattr(sub, "to_dict"):
        sub = sub.to_dict()
    sub_id = sub.get("id")
    customer_id = sub.get("customer")
    status = sub.get("status")
    cancel_at_period_end = sub.get("cancel_at_period_end", False)
    cancel_at = sub.get("cancel_at")
    current_period_end = sub.get("current_period_end")

    user = User.query.filter(
        (User.stripe_subscription_id == sub_id)
        | (User.stripe_customer_id == customer_id)
    ).first()

    if user:
        target_plan = user.plan
        if status == "active":
            target_plan = "premium"
        elif status in ("canceled", "unpaid") and user.plan != "founder":
            target_plan = "free"

        end_at = None
        cancel_ts = cancel_at
        if not cancel_ts and cancel_at_period_end:
            cancel_ts = current_period_end
        if cancel_ts:
            end_at = datetime.fromtimestamp(cancel_ts, tz=UTC)

        # Idempotence : si le statut, le plan et subscription_end_at sont déjà identiques, pas de commit redondant
        # On compare les timestamps (int) pour éviter les problèmes timezone-aware vs naive avec SQLite
        existing_end_ts = None
        if user.subscription_end_at:
            dt = user.subscription_end_at
            existing_end_ts = int(
                dt.replace(tzinfo=UTC).timestamp()
                if dt.tzinfo is None
                else dt.timestamp()
            )
        new_end_ts = int(end_at.timestamp()) if end_at else None
        if (
            user.stripe_subscription_status == status
            and user.plan == target_plan
            and existing_end_ts == new_end_ts
        ):
            logger.info(
                "Subscription %s déjà à jour pour l'utilisateur %s (idempotent)",
                sub_id,
                user.id,
            )
            return

        user.stripe_subscription_status = status
        user.plan = target_plan
        user.subscription_end_at = end_at
        if sub.get("items", {}).get("data"):
            price_obj = sub["items"]["data"][0].get("price", {})
            interval = price_obj.get("recurring", {}).get("interval")
            if interval:
                user.stripe_price_id = "yearly" if interval == "year" else "monthly"
            elif price_obj.get("id"):
                user.stripe_price_id = price_obj.get("id")
        db.session.commit()
        logger.info(
            "Statut d'abonnement mis à jour pour l'utilisateur %s : %s (fin prévue: %s)",
            user.id,
            status,
            end_at,
        )


def _handle_subscription_deleted(sub):
    if hasattr(sub, "to_dict"):
        sub = sub.to_dict()
    sub_id = sub.get("id")
    customer_id = sub.get("customer")

    user = User.query.filter(
        (User.stripe_subscription_id == sub_id)
        | (User.stripe_customer_id == customer_id)
    ).first()

    if user:
        # Idempotence : si l'abonnement est déjà résilié
        if (
            user.stripe_subscription_status == "canceled"
            and user.stripe_subscription_id is None
            and user.plan in ("free", "founder")
        ):
            logger.info(
                "Résiliation déjà traitée pour l'utilisateur %s (idempotent)",
                user.id,
            )
            return

        user.stripe_subscription_status = "canceled"
        user.stripe_subscription_id = None
        # Règle d'or : ne jamais dégrader un Membre Fondateur
        if user.plan != "founder":
            user.plan = "free"
            # Délai de grâce de 48h pour ne pas bloquer l'enseignant en pleine journée de classe
            user.trial_ends_at = datetime.now(UTC) + timedelta(hours=48)
            user.subscription_end_at = None

        db.session.commit()
        logger.info(
            "Abonnement résilié pour l'utilisateur %s (délai de grâce 48h accordé, repassage en free sans suppression)",
            user.id,
        )

        # Envoi d'un email de confirmation de résiliation (en arrière-plan pour ne pas bloquer le webhook)
        app = current_app._get_current_object()
        user_email = user.email
        user_copy = {"email": user_email, "name": getattr(user, "name", "")}

        def _send_cancellation_email():
            with app.app_context():
                try:
                    html_body = render_template(
                        "email/email_subscription_canceled.html",
                        user=user_copy,
                        reactivate_url=url_for("subscription.paiement", _external=True),
                    )
                    send_html_email(
                        subject="Confirmation d'interruption de votre abonnement Livres en Classe",
                        sender=os.getenv("MAIL_USERNAME"),
                        recipients=[user_email],
                        html_body=html_body,
                    )
                    logger.info("Email de résiliation envoyé à %s", user_email)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Impossible d'envoyer l'email de résiliation : %s", e
                    )

        threading.Thread(target=_send_cancellation_email, daemon=True).start()


def _handle_invoice_payment_failed(invoice):
    if hasattr(invoice, "to_dict"):
        invoice = invoice.to_dict()
    customer_id = invoice.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()

    if user:
        user.stripe_subscription_status = "past_due"
        db.session.commit()

        # Envoi d'un e-mail d'alerte (en arrière-plan pour ne pas bloquer le webhook)
        app = current_app._get_current_object()
        user_email = user.email
        user_copy = {"email": user_email, "name": getattr(user, "name", "")}

        def _send_payment_failed_email():
            with app.app_context():
                try:
                    html_body = render_template(
                        "email/email_payment_failed.html",
                        user=user_copy,
                        reglage_url=url_for("auth.reglage", _external=True),
                    )
                    send_html_email(
                        subject="Problème de paiement pour votre abonnement Livres en Classe",
                        sender=os.getenv("MAIL_USERNAME"),
                        recipients=[user_email],
                        html_body=html_body,
                    )
                    logger.info("Email d'échec de paiement envoyé à %s", user_email)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Impossible d'envoyer l'email d'échec de paiement : %s", e
                    )

        threading.Thread(target=_send_payment_failed_email, daemon=True).start()
