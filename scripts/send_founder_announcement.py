"""
send_founder_announcement.py: Script d'envoi de l'e-mail d'annonce aux Membres Fondateurs.
Usage :
    python scripts/send_founder_announcement.py [--dry-run] [--yes]
"""

import argparse
import os
import sys
from pathlib import Path

# Ajouter le dossier racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import render_template, url_for

from project import create_app
from project.email import send_html_email
from project.models import User


def main():
    parser = argparse.ArgumentParser(
        description="Envoyer l'email d'annonce aux Membres Fondateurs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche la liste des destinataires sans envoyer d'email.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirme l'envoi sans demande de confirmation interactive.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        founders = User.query.filter_by(plan="founder").order_by(User.id.asc()).all()

        print(
            f"=== Annonce Membres Fondateurs ({len(founders)} compte(s) trouvé(s)) ==="
        )
        for u in founders:
            print(f"  - ID: {u.id} | Email: {u.email} | Nom: {u.name}")

        if not founders:
            print("Aucun utilisateur avec le statut 'founder' trouvé.")
            return

        if args.dry_run:
            print("\nMode --dry-run activé : aucun e-mail envoyé.")
            return

        if not args.yes:
            confirm = input(
                f"\nConfirmez-vous l'envoi de l'email à ces {len(founders)} utilisateurs ? [o/N] : "
            )
            if confirm.lower() not in ("o", "oui", "y", "yes"):
                print("Envoi annulé.")
                return

        sender = os.getenv("MAIL_USERNAME")
        sent = 0
        for u in founders:
            try:
                html_body = render_template(
                    "email/email_founder_announcement.html",
                    user=u,
                    dashboard_url=url_for("main.dashboard", _external=True),
                )
                send_html_email(
                    subject="👑 Vous êtes Membre Fondateur à vie de Livres en Classe !",
                    sender=sender,
                    recipients=[u.email],
                    html_body=html_body,
                )
                sent += 1
                print(f"[OK] Email envoyé à {u.email}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERREUR] Échec d'envoi à {u.email} : {e}")

        print(f"\nTerminé : {sent}/{len(founders)} e-mail(s) envoyé(s).")


if __name__ == "__main__":
    main()
