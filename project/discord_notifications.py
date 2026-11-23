import json
import logging
import os
import urllib.request
from threading import Thread

logger = logging.getLogger(__name__)

DISCORD_ROLE_CRITICAL = os.getenv("DISCORD_ROLE_CRITICAL", "")
DISCORD_ROLE_INFO = os.getenv("DISCORD_ROLE_INFO", "")

WEBHOOK_APP_EVENTS = os.getenv("DISCORD_WEBHOOK_APP_EVENTS", "")
WEBHOOK_APP_ERRORS = os.getenv("DISCORD_WEBHOOK_APP_ERRORS", "")


def _send_discord_payload_async(webhook_url, payload):
    """Envoie un payload JSON à un webhook Discord de manière asynchrone (thread)."""
    if not webhook_url:
        return

    def _worker():
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "LivresEnClasse-Notifier/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Impossible d'expédier le webhook Discord : {e}")

    Thread(target=_worker, daemon=True).start()


def notify_new_user_signup(name, email, preferred_language="fr"):
    """Notifie dans #app-event qu'un nouvel enseignant s'est inscrit."""
    if not WEBHOOK_APP_EVENTS:
        return
    flag = (
        "🇫🇷"
        if preferred_language == "fr"
        else ("🇬🇧" if preferred_language == "en" else "🇩🇪")
    )
    mention = f"<@&{DISCORD_ROLE_INFO}>" if DISCORD_ROLE_INFO else ""
    payload = {
        "username": "Livres en Classe (Événements)",
        "avatar_url": "https://livresenclasse.com/static/img/logo.png",
        "content": mention,
        "embeds": [
            {
                "title": f"🎉 Nouvel enseignant inscrit {flag}",
                "description": "Un nouvel utilisateur a créé son compte sur **livresenclasse.com**.",
                "color": 5793266,  # Bleu Discord
                "fields": [
                    {"name": "Nom", "value": name or "(Non renseigné)", "inline": True},
                    {"name": "Email", "value": email, "inline": True},
                    {
                        "name": "Langue",
                        "value": preferred_language.upper(),
                        "inline": True,
                    },
                ],
                "footer": {"text": "Modèle SaaS Freemium · Essai 14 jours"},
            }
        ],
    }
    _send_discord_payload_async(WEBHOOK_APP_EVENTS, payload)


def notify_stripe_subscription_activated(customer_email, plan_name, amount_str):
    """Notifie dans #app-event d'un nouvel abonnement Premium payant."""
    if not WEBHOOK_APP_EVENTS:
        return
    mention = f"<@&{DISCORD_ROLE_INFO}>" if DISCORD_ROLE_INFO else ""
    payload = {
        "username": "Livres en Classe (Stripe)",
        "avatar_url": "https://livresenclasse.com/static/img/logo.png",
        "content": mention,
        "embeds": [
            {
                "title": "💳 Nouvel Abonnement Premium Activé !",
                "description": f"L'enseignant **{customer_email}** a souscrit à la formule **{plan_name}**.",
                "color": 5763719,  # Vert Discord
                "fields": [
                    {"name": "Formule", "value": plan_name, "inline": True},
                    {"name": "Tarif", "value": amount_str, "inline": True},
                    {
                        "name": "Statut Stripe",
                        "value": "Actif (Paiement validé)",
                        "inline": True,
                    },
                ],
                "footer": {"text": "Stripe Webhook checkout.session.completed"},
            }
        ],
    }
    _send_discord_payload_async(WEBHOOK_APP_EVENTS, payload)


def notify_app_exception(error_name, route, method="GET", user_email=None):
    """Notifie dans #app-errors d'une erreur 500 ou exception critique."""
    if not WEBHOOK_APP_ERRORS:
        return
    mention = f"<@&{DISCORD_ROLE_CRITICAL}>" if DISCORD_ROLE_CRITICAL else ""
    payload = {
        "username": "Livres en Classe (Erreurs)",
        "avatar_url": "https://livresenclasse.com/static/img/logo.png",
        "content": mention,
        "embeds": [
            {
                "title": "🚨 Erreur HTTP 500 / Exception Backend",
                "description": "Une exception non interceptée s'est produite lors d'une requête.",
                "color": 15158332,  # Rouge Discord
                "fields": [
                    {"name": "Route", "value": f"`{method} {route}`", "inline": True},
                    {
                        "name": "Utilisateur",
                        "value": user_email or "Anonyme",
                        "inline": True,
                    },
                    {
                        "name": "Détails",
                        "value": f"```{str(error_name)[:500]}```",
                        "inline": False,
                    },
                ],
                "footer": {"text": "Alerte critique application"},
            }
        ],
    }
    _send_discord_payload_async(WEBHOOK_APP_ERRORS, payload)
