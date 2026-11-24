#!/usr/bin/env python3
"""scripts/setup_stripe.py: Script automatisé pour configurer l'ensemble de l'infrastructure Stripe.

Fonctionnalités :
1. Détection ou création du Produit « Livres en Classe - Premium ».
2. Détection ou création des 3 Tarifs récurrents :
   - Mensuel CHF : 3.00 CHF / mois
   - Annuel CHF : 30.00 CHF / an
   - Annuel EUR : 30.00 EUR / an (Facturation école / coopérative)
3. Configuration du portail client Stripe (Customer Portal) :
   - Autorisation des changements de forfait (Mensuel <-> Annuel)
   - Historique des factures et reçus
   - Mise à jour des moyens de paiement
   - Résiliation à terme (at_period_end)
4. Détection ou création du Webhook Endpoint de production (https://livresenclasse.com/webhook/stripe)
   avec les 8 événements nécessaires.
5. Affichage ou mise à jour automatique du fichier .env.

Usage :
    python scripts/setup_stripe.py [--update-env] [--api-key sk_...]
"""

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Charger .env initial
load_dotenv()

try:
    import stripe
except ImportError:
    print(
        "Erreur: Le module 'stripe' n'est pas installé. Exécutez 'pip install stripe'."
    )
    sys.exit(1)

REQUIRED_WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "invoice.voided",
    "invoice.marked_uncollectible",
]


def update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """Met à jour ou ajoute les clés dans le fichier .env."""
    if not env_path.exists():
        content = ""
    else:
        content = env_path.read_text(encoding="utf-8")

    for key, value in updates.items():
        pattern = rf"^{key}=.*$"
        replacement = f"{key}='{value}'"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            if content and not content.endswith("\n"):
                content += "\n"
            content += f"{replacement}\n"

    env_path.write_text(content, encoding="utf-8")
    print(f"-> Fichier {env_path.name} mis à jour avec succès.")


def setup_stripe(
    api_key: str, webhook_url: str, update_env: bool = False
) -> dict[str, str]:
    stripe.api_key = api_key
    is_live = api_key.startswith("sk_live_")
    mode_str = "LIVE (Production)" if is_live else "TEST (Développement)"
    print(f"=== Configuration Stripe [{mode_str}] ===")

    # 1. Vérification / Création du produit
    print("\n1. Vérification du Produit...")
    products = stripe.Product.list(limit=20).data
    product = None
    for p in products:
        if "Livres en Classe" in p.name and p.active:
            product = p
            break

    if not product:
        print("-> Création du produit 'Livres en Classe - Premium'...")
        product = stripe.Product.create(
            name="Livres en Classe - Premium",
            description="Abonnement enseignant illimité : gestion de bibliothèque, élèves et prêts",
            metadata={"app": "bibliotheque-flask"},
        )
    print(f"-> Produit ID : {product.id} ({product.name})")

    # 2. Vérification / Création des prix
    print("\n2. Vérification des Tarifs récurrents...")
    existing_prices = stripe.Price.list(product=product.id, limit=30).data

    # Mensuel CHF (3.00 CHF / mois)
    price_monthly_chf = next(
        (
            p
            for p in existing_prices
            if p.active
            and p.currency == "chf"
            and p.unit_amount == 300
            and getattr(p.recurring, "interval", None) == "month"
        ),
        None,
    )
    if not price_monthly_chf:
        print("-> Création du tarif mensuel 3.00 CHF / mois...")
        price_monthly_chf = stripe.Price.create(
            product=product.id,
            unit_amount=300,
            currency="chf",
            recurring={"interval": "month"},
            metadata={"plan_type": "monthly"},
        )
    print(f"-> Prix Mensuel CHF : {price_monthly_chf.id} (3.00 CHF / mois)")

    # Annuel CHF (30.00 CHF / an)
    price_yearly_chf = next(
        (
            p
            for p in existing_prices
            if p.active
            and p.currency == "chf"
            and p.unit_amount == 3000
            and getattr(p.recurring, "interval", None) == "year"
        ),
        None,
    )
    if not price_yearly_chf:
        print("-> Création du tarif annuel 30.00 CHF / an...")
        price_yearly_chf = stripe.Price.create(
            product=product.id,
            unit_amount=3000,
            currency="chf",
            recurring={"interval": "year"},
            metadata={"plan_type": "yearly"},
        )
    print(f"-> Prix Annuel CHF  : {price_yearly_chf.id} (30.00 CHF / an)")

    # Annuel EUR (30.00 EUR / an)
    price_yearly_eur = next(
        (
            p
            for p in existing_prices
            if p.active
            and p.currency == "eur"
            and p.unit_amount == 3000
            and getattr(p.recurring, "interval", None) == "year"
        ),
        None,
    )
    if not price_yearly_eur:
        print("-> Création du tarif annuel 30.00 EUR / an...")
        price_yearly_eur = stripe.Price.create(
            product=product.id,
            unit_amount=3000,
            currency="eur",
            recurring={"interval": "year"},
            metadata={"plan_type": "yearly_eur"},
        )
    print(f"-> Prix Annuel EUR  : {price_yearly_eur.id} (30.00 EUR / an)")

    # 3. Configuration du Portail Client (Customer Portal)
    print("\n3. Configuration du Portail Client (Customer Portal)...")
    try:
        portal_configs = stripe.billing_portal.Configuration.list(limit=5).data
        portal_features = {
            "customer_update": {
                "allowed_updates": ["name", "email", "address", "phone"],
                "enabled": True,
            },
            "invoice_history": {"enabled": True},
            "payment_method_update": {"enabled": True},
            "subscription_cancel": {
                "enabled": True,
                "mode": "at_period_end",
                "proration_behavior": "none",
                "cancellation_reason": {
                    "enabled": True,
                    "options": [
                        "too_expensive",
                        "switched_service",
                        "unused",
                        "other",
                    ],
                },
            },
            "subscription_update": {
                "enabled": True,
                "default_allowed_updates": ["price"],
                "proration_behavior": "always_invoice",
                "products": [
                    {
                        "product": product.id,
                        "prices": [price_monthly_chf.id, price_yearly_chf.id],
                    }
                ],
            },
        }

        if portal_configs:
            default_config = portal_configs[0]
            stripe.billing_portal.Configuration.modify(
                default_config.id, features=portal_features
            )
            print(f"-> Configuration portail mise à jour : {default_config.id}")
        else:
            created_portal = stripe.billing_portal.Configuration.create(
                features=portal_features,
                business_profile={
                    "headline": "Livres en Classe — Gestion de votre abonnement"
                },
            )
            print(f"-> Configuration portail créée : {created_portal.id}")
    except Exception as portal_err:  # noqa: BLE001
        print(f"-> Avertissement portail client : {portal_err}")

    # 4. Vérification / Création du Webhook Endpoint
    print(f"\n4. Configuration du Webhook ({webhook_url})...")
    endpoints = stripe.WebhookEndpoint.list(limit=20).data
    existing_webhook = None
    for ep in endpoints:
        if ep.url == webhook_url and ep.status == "enabled":
            existing_webhook = ep
            break

    webhook_secret = None
    if existing_webhook:
        print(f"-> Webhook existant trouvé : {existing_webhook.id}")
        # Mettre à jour les événements si nécessaire
        missing_events = [
            ev
            for ev in REQUIRED_WEBHOOK_EVENTS
            if ev not in existing_webhook.enabled_events
        ]
        if missing_events:
            print(f"-> Mise à jour des événements webhook : +{missing_events}")
            updated_events = list(
                set(existing_webhook.enabled_events + REQUIRED_WEBHOOK_EVENTS)
            )
            stripe.WebhookEndpoint.modify(
                existing_webhook.id, enabled_events=updated_events
            )
        webhook_secret = getattr(existing_webhook, "secret", None)
    else:
        print(f"-> Création du webhook endpoint vers {webhook_url}...")
        created_ep = stripe.WebhookEndpoint.create(
            url=webhook_url,
            enabled_events=REQUIRED_WEBHOOK_EVENTS,
            description="Production Webhook Livres en Classe",
        )
        existing_webhook = created_ep
        webhook_secret = created_ep.secret
        print(f"-> Webhook créé ID : {created_ep.id}")

    # Résumé
    results = {
        "STRIPE_PRICE_MONTHLY": price_monthly_chf.id,
        "STRIPE_PRICE_YEARLY": price_yearly_chf.id,
        "STRIPE_PRICE_YEARLY_EUR": price_yearly_eur.id,
    }
    if webhook_secret:
        results["STRIPE_WEBHOOK_SECRET"] = webhook_secret

    print("\n" + "=" * 50)
    print("Configuration terminée avec succès !")
    print("Voici les variables à renseigner dans votre .env :")
    print("=" * 50)
    for k, v in results.items():
        print(f"{k}='{v}'")
    print("=" * 50)

    if update_env:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        update_env_file(env_path, results)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configuration automatisée Stripe pour Livres en Classe"
    )
    parser.add_argument(
        "--api-key",
        help="Clé secrète Stripe (sk_live_... ou sk_test_...). Par défaut: STRIPE_SECRET_KEY du .env",
    )
    parser.add_argument(
        "--webhook-url",
        default="https://livresenclasse.com/webhook/stripe",
        help="URL du webhook de réception (défaut: https://livresenclasse.com/webhook/stripe)",
    )
    parser.add_argument(
        "--update-env",
        action="store_true",
        help="Met à jour directement le fichier .env local",
    )

    args = parser.parse_args()
    api_key = args.api_key or os.getenv("STRIPE_SECRET_KEY")

    if not api_key:
        print(
            "Erreur: Aucune clé Stripe spécifiée. Utilisez --api-key ou définissez STRIPE_SECRET_KEY."
        )
        sys.exit(1)

    setup_stripe(api_key, args.webhook_url, args.update_env)


if __name__ == "__main__":
    main()
