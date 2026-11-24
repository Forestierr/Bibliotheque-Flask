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
    get_stripe_tax_notice,
)
from .email import send_html_email
from .models import SchoolInvoice, User

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

    is_school_reimbursement = request.form.get("is_school_reimbursement") in ("1", "true", "on")
    school_name = (request.form.get("school_name") or "").strip()
    school_address = (request.form.get("school_address") or "").strip()

    # Paramètres de base de la session (Managed Payments géré par le Dashboard Stripe)
    checkout_params = {
        "mode": "subscription",
        "allow_promotion_codes": True,
        "client_reference_id": str(current_user.id),
        "tax_id_collection": {"enabled": True},
        "metadata": {
            "user_id": str(current_user.id),
            "plan_type": plan_type,
        },
        "success_url": url_for("subscription.success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": url_for("subscription.cancel", _external=True),
    }

    if is_school_reimbursement or school_name:
        checkout_params["metadata"]["is_school_reimbursement"] = "true"
        if school_name:
            checkout_params["metadata"]["school_name"] = school_name
        if school_address:
            checkout_params["metadata"]["school_address"] = school_address

    # S'assurer d'avoir un client Stripe existant pour autoriser customer_update
    if not current_user.stripe_customer_id:
        try:
            cust_params = {
                "email": current_user.email,
                "metadata": {"user_id": str(current_user.id)},
            }
            if current_user.name:
                cust_params["name"] = current_user.name
            cust = stripe.Customer.create(**cust_params)
            current_user.stripe_customer_id = cust.id
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Erreur pré-création stripe.Customer: %s", e)

    # Réutiliser le client Stripe s'il existe déjà
    if current_user.stripe_customer_id:
        checkout_params["customer"] = current_user.stripe_customer_id
        checkout_params["customer_update"] = {"name": "auto", "address": "auto"}
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
    except Exception as e:
        if current_app.testing:
            logger.warning(
                "Erreur simulée lors de la création de session Stripe Checkout : %s",
                e,
            )
        else:
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
    except Exception as e:
        if current_app.testing:
            logger.warning("Erreur simulée Stripe Portal : %s", e)
        else:
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
            session = stripe.checkout.Session.retrieve(
                session_id, expand=["invoice"]
            )
            session_data = (
                session.to_dict() if hasattr(session, "to_dict") else session
            )

            # Vérification d'identité (FND-08) : s'assurer que la session appartient à l'utilisateur connecté
            session_user_id = session_data.get("client_reference_id") or (
                session_data.get("metadata") or {}
            ).get("user_id")
            if str(session_user_id) != str(current_user.id):
                flash(_("Session de paiement invalide ou expirée."), "error")
                return redirect(url_for("main.dashboard"))
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

                # Récupérer l'ID et l'URL du PDF de facture acquittée
                inv_obj = session_data.get("invoice")
                if inv_obj:
                    if isinstance(inv_obj, str):
                        try:
                            retrieved_inv = stripe.Invoice.retrieve(inv_obj)
                            current_user.stripe_latest_invoice_id = str(
                                retrieved_inv.id
                            )
                            if getattr(retrieved_inv, "invoice_pdf", None):
                                current_user.stripe_latest_invoice_pdf = (
                                    retrieved_inv.invoice_pdf
                                )
                        except Exception as inv_err:  # noqa: BLE001
                            logger.warning(
                                "Erreur récupération facture acquittée Stripe : %s",
                                inv_err,
                            )
                    elif isinstance(inv_obj, dict):
                        current_user.stripe_latest_invoice_id = str(
                            inv_obj.get("id")
                        )
                        current_user.stripe_latest_invoice_pdf = inv_obj.get(
                            "invoice_pdf"
                        )
                db.session.commit()
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            logger.warning("Erreur vérification session_id success : %s", e)

    return render_template("subscription/success.html")


@subscription.route("/subscription/facture-acquittee")
@login_required
def facture_acquittee():
    """Redirige l'enseignant vers le PDF officiel Stripe de sa dernière facture acquittée."""
    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    pdf_url = current_user.stripe_latest_invoice_pdf

    # Si l'URL n'est pas connue ou pour actualiser depuis Stripe
    if stripe_secret and (
        current_user.stripe_customer_id
        or current_user.stripe_latest_invoice_id
    ):
        try:
            stripe.api_key = stripe_secret
            if current_user.stripe_latest_invoice_id:
                inv = stripe.Invoice.retrieve(current_user.stripe_latest_invoice_id)
                inv_pdf = getattr(inv, "invoice_pdf", None) or (
                    inv.get("invoice_pdf") if isinstance(inv, dict) else None
                )
                inv_hosted = getattr(inv, "hosted_invoice_url", None) or (
                    inv.get("hosted_invoice_url") if isinstance(inv, dict) else None
                )
                if inv_pdf:
                    current_user.stripe_latest_invoice_pdf = inv_pdf
                    db.session.commit()
                    return redirect(inv_pdf, code=302)
                elif inv_hosted:
                    return redirect(inv_hosted, code=302)

            if current_user.stripe_customer_id:
                invoices = stripe.Invoice.list(
                    customer=current_user.stripe_customer_id,
                    status="paid",
                    limit=1,
                )
                invoices_data = getattr(invoices, "data", [])
                if invoices_data:
                    latest = invoices_data[0]
                    latest_id = getattr(latest, "id", None) or (
                        latest.get("id") if isinstance(latest, dict) else None
                    )
                    latest_pdf = getattr(latest, "invoice_pdf", None) or (
                        latest.get("invoice_pdf") if isinstance(latest, dict) else None
                    )
                    latest_hosted = getattr(latest, "hosted_invoice_url", None) or (
                        latest.get("hosted_invoice_url") if isinstance(latest, dict) else None
                    )
                    if latest_id:
                        current_user.stripe_latest_invoice_id = str(latest_id)
                    if latest_pdf:
                        current_user.stripe_latest_invoice_pdf = latest_pdf
                    db.session.commit()
                    if latest_pdf:
                        return redirect(latest_pdf, code=302)
                    if latest_hosted:
                        return redirect(latest_hosted, code=302)
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            logger.warning("Erreur récupération facture acquittée Stripe : %s", e)


    if pdf_url:
        return redirect(pdf_url, code=302)

    flash(
        _(
            "Aucune facture acquittée n'est disponible pour votre compte actuellement."
        ),
        "info",
    )
    return redirect(url_for("auth.reglage"))


@subscription.route("/subscription/facture-ecole", methods=["GET", "POST"])
@login_required
def facture_ecole():
    """Permet à un enseignant de demander une facture officielle Stripe au nom de son école/coopérative."""
    if current_user.plan == "founder":
        flash(
            _(
                "Votre statut Fondateur vous donne déjà un accès complet et illimité à vie."
            ),
            "info",
        )
        return redirect(url_for("main.dashboard"))

    # Vérifier si l'utilisateur a déjà une facture école en attente de paiement
    pending_invoice = current_user.active_pending_school_invoice

    if request.method == "POST":
        if pending_invoice:
            flash(
                _(
                    "Une facture école est déjà en cours de règlement pour votre compte."
                ),
                "warning",
            )
            return redirect(
                url_for(
                    "subscription.facture_ecole_confirmation",
                    invoice_id=pending_invoice.id,
                )
            )

        school_name = (request.form.get("school_name") or "").strip()
        school_address = (request.form.get("school_address") or "").strip()
        school_billing_email = (
            request.form.get("school_billing_email") or ""
        ).strip()
        country_currency = (
            request.form.get("country_currency") or "EUR"
        ).upper()
        siret_or_tax_id = (request.form.get("siret_or_tax_id") or "").strip()
        order_reference = (request.form.get("order_reference") or "").strip()

        if not school_name or not school_address or not school_billing_email:
            flash(
                _(
                    "Veuillez renseigner le nom de l'organisme, son adresse complète et l'e-mail de facturation."
                ),
                "error",
            )
            return render_template(
                "subscription/facture_ecole.html",
                pending_invoice=pending_invoice,
                user_school_name=school_name,
            )

        stripe_secret = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_secret:
            logger.warning(
                "STRIPE_SECRET_KEY non configurée pour facture école."
            )
            flash(
                _(
                    "Le service de facturation Stripe est en cours de configuration. Contactez l'administrateur."
                ),
                "info",
            )
            return redirect(url_for("subscription.tarifs"))

        stripe.api_key = stripe_secret
        currency = "eur" if country_currency == "EUR" else "chf"
        unit_amount = 3000  # 30.00 EUR ou 30.00 CHF

        try:
            # 1. Créer le client Stripe dédié à l'école / organisme payeur
            cust_params = {
                "name": school_name,
                "email": school_billing_email,
                "address": {"line1": school_address},
                "metadata": {
                    "user_id": str(current_user.id),
                    "teacher_email": current_user.email,
                    "teacher_name": current_user.name or "",
                    "flow": "flux_b_school_invoice",
                    "siret_or_tax_id": siret_or_tax_id,
                },
            }
            customer = stripe.Customer.create(**cust_params)

            # Enregistrer le numéro de TVA intracommunautaire officiel sur le client Stripe si fourni
            if siret_or_tax_id:
                clean_tax = siret_or_tax_id.strip().replace(" ", "").upper()
                try:
                    stripe.Customer.create_tax_id(customer.id, value=clean_tax)
                    logger.info("Tax ID Stripe créé pour %s : %s", customer.id, clean_tax)
                except Exception as tax_err:  # noqa: BLE001
                    logger.info(
                        "Tax ID informel ou SIRET non normalisé Stripe Tax ID : %s",
                        tax_err,
                    )

            # 2. Créer le brouillon de facture Stripe Invoicing avec devise explicite et mention fiscale
            tax_footer = get_stripe_tax_notice(currency)
            invoice_params = {
                "customer": customer.id,
                "currency": currency,
                "collection_method": "send_invoice",
                "days_until_due": 30,
                "auto_advance": True,
                "footer": tax_footer,
                "metadata": {
                    "user_id": str(current_user.id),
                    "school_name": school_name,
                    "school_billing_email": school_billing_email,
                    "flow": "flux_b_school_invoice",
                },
                "payment_settings": {
                    "payment_method_types": ["card", "customer_balance"],
                },
            }

            custom_fields = []
            if siret_or_tax_id:
                field_label = (
                    "N° TVA"
                    if any(
                        siret_or_tax_id.upper().startswith(p)
                        for p in ("FR", "BE", "CHE", "DE", "ES", "IT")
                    )
                    else "SIRET / IDE"
                )
                custom_fields.append({"name": field_label, "value": siret_or_tax_id[:30]})
            if order_reference:
                custom_fields.append({"name": "Bon de commande", "value": order_reference[:30]})
            if custom_fields:
                invoice_params["custom_fields"] = custom_fields

            try:
                created_inv = stripe.Invoice.create(**invoice_params)
            except Exception as pay_err:  # noqa: BLE001
                logger.warning(
                    "Fallback création facture sans payment_settings custom : %s",
                    pay_err,
                )
                invoice_params.pop("payment_settings", None)
                created_inv = stripe.Invoice.create(**invoice_params)

            # 3. Créer la ligne de facture attachée directement à cette facture
            item_description = (
                f"Abonnement annuel Livres en Classe (Année scolaire) — "
                f"Enseignant(e) : {current_user.name or current_user.email} (Prix net HT)"
            )
            if order_reference:
                item_description += f" [Réf: {order_reference}]"

            stripe.InvoiceItem.create(
                customer=customer.id,
                invoice=created_inv.id,
                amount=unit_amount,
                currency=currency,
                description=item_description,
                metadata={
                    "user_id": str(current_user.id),
                    "school_name": school_name,
                },
            )

            # 4. Finaliser la facture pour générer hosted_invoice_url et PDF
            try:
                finalized_inv = stripe.Invoice.finalize_invoice(created_inv.id)
            except Exception:  # noqa: BLE001
                finalized_inv = stripe.Invoice.retrieve(created_inv.id)

            # 5. Envoyer l'e-mail officiel Stripe au secrétariat
            try:
                stripe.Invoice.send_invoice(finalized_inv.id)
            except Exception as send_err:  # noqa: BLE001
                logger.warning(
                    "Notification Stripe send_invoice échouée : %s", send_err
                )

            # 6. Enregistrer la facture école en base de données
            due_date = datetime.now(UTC) + timedelta(days=30)
            hosted_url = getattr(finalized_inv, "hosted_invoice_url", None)
            pdf_url = getattr(finalized_inv, "invoice_pdf", None)

            school_inv = SchoolInvoice(
                user_id=current_user.id,
                stripe_invoice_id=finalized_inv.id,
                stripe_customer_id=customer.id,
                school_name=school_name,
                school_address=school_address,
                school_billing_email=school_billing_email,
                siret_or_tax_id=siret_or_tax_id,
                order_reference=order_reference,
                amount=float(unit_amount) / 100.0,
                currency=currency.upper(),
                status="pending",
                hosted_invoice_url=hosted_url,
                invoice_pdf_url=pdf_url,
                due_at=due_date,
                created_at=datetime.now(UTC),
            )
            db.session.add(school_inv)

            # 7. Activer l'accès Premium immédiat de 30 jours (Grace Period)
            db_user = db.session.get(User, current_user.id)
            if db_user and db_user.plan != "founder":
                db_user.trial_ends_at = due_date
            if hasattr(current_user, "trial_ends_at") and current_user.plan != "founder":
                current_user.trial_ends_at = due_date
            db.session.commit()

            # 8. Envoyer un email de confirmation à l'enseignant (en arrière-plan)
            _send_school_invoice_created_email(current_user, school_inv)

            flash(
                _(
                    "Votre facture école a été générée avec succès. Votre accès Premium est débloqué pour 30 jours !"
                ),
                "success",
            )
            return redirect(
                url_for(
                    "subscription.facture_ecole_confirmation",
                    invoice_id=school_inv.id,
                )
            )

        except Exception as e:
            if current_app.testing:
                logger.warning(
                    "Erreur simulée lors de la création de la facture école Stripe : %s",
                    e,
                )
            else:
                logger.exception("Erreur lors de la création de la facture école Stripe")
            db.session.rollback()
            flash(
                _(
                    "Une erreur est survenue lors de la création de la facture Stripe. Veuillez vérifier les informations ou réessayer ultérieurement."
                ),
                "error",
            )
            return redirect(url_for("subscription.facture_ecole"))

    return render_template(
        "subscription/facture_ecole.html",
        pending_invoice=pending_invoice,
        user_school_name="",
    )


@subscription.route("/subscription/facture-ecole/confirmation/<int:invoice_id>")
@login_required
def facture_ecole_confirmation(invoice_id):
    """Affiche la page de confirmation et les détails d'une facture école émise."""
    school_inv = db.session.get(SchoolInvoice, invoice_id)
    if not school_inv or school_inv.user_id != current_user.id:
        flash(_("Facture école introuvable."), "error")
        return redirect(url_for("auth.reglage"))

    # Auto-synchronisation avec Stripe si la facture est encore marquée pending
    if school_inv.status == "pending" and school_inv.stripe_invoice_id:
        stripe_secret = os.getenv("STRIPE_SECRET_KEY")
        if stripe_secret and not current_app.config.get("TESTING"):
            try:
                stripe.api_key = stripe_secret
                st_inv = stripe.Invoice.retrieve(school_inv.stripe_invoice_id)
                st_status = getattr(st_inv, "status", None)
                if st_status == "paid":
                    _handle_invoice_paid(st_inv)
                elif st_status in ("void", "uncollectible"):
                    _handle_invoice_voided(st_inv)
            except Exception as sync_err:  # noqa: BLE001
                logger.warning(
                    "Erreur auto-sync confirmation facture école %s : %s",
                    school_inv.id,
                    sync_err,
                )

    return render_template(
        "subscription/facture_ecole_confirmation.html",
        invoice=school_inv,
    )


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
    if not endpoint_secret and current_app.testing:
        endpoint_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "whsec_test")

    if not endpoint_secret:
        logger.error("STRIPE_WEBHOOK_SECRET non configuré dans l'environnement.")
        return jsonify({"error": "Webhook secret not configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        logger.error("Payload webhook Stripe invalide : %s", e)
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.error("Signature webhook Stripe invalide : %s", e)
        return jsonify({"error": "Invalid signature"}), 400

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
    elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
        _handle_invoice_paid(data_object)
    elif event_type in ("invoice.voided", "invoice.marked_uncollectible"):
        _handle_invoice_voided(data_object)

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
        user.renewal_reminder_sent = False
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

        # Notification Discord (#app-events)
        try:
            from .discord_notifications import notify_stripe_subscription_activated

            amount_total = session.get("amount_total", 0)
            currency = (session.get("currency") or "chf").upper()
            amount_str = (
                f"{amount_total / 100:.2f} {currency}" if amount_total else "Payé"
            )
            notify_stripe_subscription_activated(
                customer_email=user.email,
                plan_name=plan_type or "Premium",
                amount_str=amount_str,
            )
        except Exception:  # noqa: BLE001, S110
            pass


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
                except Exception as e:  # noqa: BLE001  # noqa: BLE001
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
                except Exception as e:  # noqa: BLE001  # noqa: BLE001
                    logger.warning(
                        "Impossible d'envoyer l'email d'échec de paiement : %s", e
                    )

        threading.Thread(target=_send_payment_failed_email, daemon=True).start()


def _handle_invoice_paid(invoice_data):
    if hasattr(invoice_data, "to_dict"):
        invoice_data = invoice_data.to_dict()
    invoice_id = invoice_data.get("id")
    if not invoice_id:
        return

    # 1. Vérifier si c'est une facture école (Flux B)
    school_inv = SchoolInvoice.query.filter_by(
        stripe_invoice_id=invoice_id
    ).first()
    if school_inv:
        if school_inv.status == "paid":
            logger.info(
                "Facture école %s déjà traitée comme payée (idempotent)",
                invoice_id,
            )
            return

        school_inv.status = "paid"
        school_inv.paid_at = datetime.now(UTC)
        if invoice_data.get("invoice_pdf"):
            school_inv.invoice_pdf_url = invoice_data.get("invoice_pdf")
        if invoice_data.get("hosted_invoice_url"):
            school_inv.hosted_invoice_url = invoice_data.get("hosted_invoice_url")

        user = school_inv.user
        if user and user.plan != "founder":
            user.plan = "premium"
            user.stripe_subscription_status = "active"
            user.stripe_latest_invoice_id = invoice_id
            if invoice_data.get("invoice_pdf"):
                user.stripe_latest_invoice_pdf = invoice_data.get("invoice_pdf")

            # Prolongation de 365 jours complets
            now = datetime.now(UTC)
            base_date = now
            if user.subscription_end_at:
                end_aware = (
                    user.subscription_end_at.replace(tzinfo=UTC)
                    if user.subscription_end_at.tzinfo is None
                    else user.subscription_end_at
                )
                if end_aware > now:
                    base_date = end_aware
            user.subscription_end_at = base_date + timedelta(days=365)
            user.trial_ends_at = None
            user.renewal_reminder_sent = False
            db.session.commit()
            logger.info(
                "Facture école %s payée. Compte de l'utilisateur %s prolongé pour 365 jours jusqu'au %s",
                invoice_id,
                user.id,
                user.subscription_end_at,
            )
            _send_school_invoice_paid_email(user, school_inv)
        else:
            db.session.commit()
        return

    # 2. Facture de souscription classique (Flux A)
    customer_id = invoice_data.get("customer")
    user = None
    if customer_id:
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        user_id = (invoice_data.get("metadata") or {}).get("user_id")
        if user_id:
            try:
                user = db.session.get(User, int(user_id))
            except (ValueError, TypeError):
                user = None

    if user:
        user.stripe_latest_invoice_id = invoice_id
        if invoice_data.get("invoice_pdf"):
            user.stripe_latest_invoice_pdf = invoice_data.get("invoice_pdf")
        db.session.commit()
        logger.info(
            "Facture acquittée %s associée à l'utilisateur %s via invoice.paid",
            invoice_id,
            user.id,
        )


def _handle_invoice_voided(invoice_data):
    if hasattr(invoice_data, "to_dict"):
        invoice_data = invoice_data.to_dict()
    invoice_id = invoice_data.get("id")
    if not invoice_id:
        return
    school_inv = SchoolInvoice.query.filter_by(
        stripe_invoice_id=invoice_id
    ).first()
    if school_inv:
        new_status = (
            "expired"
            if invoice_data.get("status") == "uncollectible"
            else "void"
        )
        school_inv.status = new_status
        db.session.commit()
        logger.info(
            "Facture école %s marquée comme %s", invoice_id, new_status
        )


def _safe_external_url(endpoint, **values):
    """Génère une URL absolue même hors contexte de requête active."""
    try:
        return url_for(endpoint, _external=True, **values)
    except Exception:  # noqa: BLE001
        base_url = os.getenv("BASE_URL", "https://livresenclasse.com").rstrip("/")
        try:
            rel = url_for(endpoint, **values)
        except Exception:  # noqa: BLE001
            rel = "/"
        return f"{base_url}{rel}"


def _send_school_invoice_created_email(user, school_inv):
    app = current_app._get_current_object()
    user_email = user.email
    user_copy = {"email": user_email, "name": getattr(user, "name", "")}
    inv_copy = {
        "id": school_inv.id,
        "school_name": school_inv.school_name,
        "school_billing_email": school_inv.school_billing_email,
        "amount": school_inv.amount,
        "currency": school_inv.currency,
        "hosted_invoice_url": school_inv.hosted_invoice_url,
        "invoice_pdf_url": school_inv.invoice_pdf_url,
        "due_at": school_inv.due_at,
    }

    def _send():
        with app.app_context():
            try:
                confirmation_url = _safe_external_url(
                    "subscription.facture_ecole_confirmation",
                    invoice_id=inv_copy["id"],
                )
                html_body = render_template(
                    "email/email_school_invoice_created.html",
                    user=user_copy,
                    invoice=inv_copy,
                    confirmation_url=confirmation_url,
                )
                recipients = [user_email]
                billing_email = inv_copy.get("school_billing_email")
                if billing_email and billing_email not in recipients:
                    recipients.append(billing_email)

                send_html_email(
                    subject="Facture école — Accès Premium 30 jours actif — Livres en Classe",
                    sender=os.getenv("MAIL_USERNAME"),
                    recipients=recipients,
                    html_body=html_body,
                )
                logger.info(
                    "Email facture école créée envoyé à %s", ", ".join(recipients)
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Impossible d'envoyer l'email facture école créée : %s", e
                )

    threading.Thread(target=_send, daemon=True).start()


def _send_school_invoice_paid_email(user, school_inv):
    app = current_app._get_current_object()
    user_email = user.email
    user_copy = {
        "email": user_email,
        "name": getattr(user, "name", ""),
        "subscription_end_at": getattr(user, "subscription_end_at", None),
    }
    inv_copy = {
        "id": school_inv.id,
        "school_name": school_inv.school_name,
        "school_billing_email": getattr(school_inv, "school_billing_email", None),
        "amount": school_inv.amount,
        "currency": school_inv.currency,
        "invoice_pdf_url": school_inv.invoice_pdf_url,
    }

    def _send():
        with app.app_context():
            try:
                reglage_url = _safe_external_url("auth.reglage")
                html_body = render_template(
                    "email/email_school_invoice_paid.html",
                    user=user_copy,
                    invoice=inv_copy,
                    reglage_url=reglage_url,
                )
                recipients = [user_email]
                billing_email = inv_copy.get("school_billing_email")
                if billing_email and billing_email not in recipients:
                    recipients.append(billing_email)

                send_html_email(
                    subject="Règlement validé — Votre abonnement annuel Livres en Classe est actif",
                    sender=os.getenv("MAIL_USERNAME"),
                    recipients=recipients,
                    html_body=html_body,
                )
                logger.info(
                    "Email confirmation règlement facture école envoyé à %s",
                    ", ".join(recipients),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Impossible d'envoyer l'email confirmation règlement : %s", e
                )
                logger.warning(
                    "Impossible d'envoyer l'email de confirmation de paiement école : %s",
                    e,
                )

    threading.Thread(target=_send, daemon=True).start()
