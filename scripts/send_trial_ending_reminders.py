"""
send_trial_ending_reminders.py: Envoi automatique d'e-mails de rappel pour les fins d'essai (à J-3).
Peut être appelé quotidiennement par une tâche cron.
Usage :
    python scripts/send_trial_ending_reminders.py [--dry-run]
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ajouter le dossier racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import render_template, url_for

from project import create_app, db
from project.email import send_html_email
from project.models import User


def main():
    parser = argparse.ArgumentParser(
        description="Envoyer les emails de rappel de fin d'essai."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les utilisateurs ciblés sans envoyer d'e-mails.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        now = datetime.now(UTC)
        # Cibler les utilisateurs dont l'essai se termine dans moins de 3 jours et pas encore notifiés
        in_3_days = now + timedelta(days=3)

        candidates = User.query.filter(
            User.plan == "free",
            User.trial_ends_at.isnot(None),
            User.trial_ends_at > now,
            User.trial_ends_at <= in_3_days,
            User.trial_reminder_sent.is_(False),
        ).all()

        print(f"=== Rappels de fin d'essai ({len(candidates)} compte(s) ciblé(s)) ===")
        for u in candidates:
            print(
                f"  - ID: {u.id} | Email: {u.email} | Fin d'essai: {u.trial_ends_at} (reste {u.trial_days_left}j)"
            )

        if not candidates or args.dry_run:
            return

        sender = os.getenv("MAIL_USERNAME")
        sent = 0
        for u in candidates:
            try:
                html_body = render_template(
                    "email/email_trial_ending.html",
                    user=u,
                    days_left=u.trial_days_left,
                    tarifs_url=url_for("subscription.tarifs", _external=True),
                )
                send_html_email(
                    subject=f"⏳ Il vous reste {u.trial_days_left} jours d'accès complet offert sur Livres en Classe !",
                    sender=sender,
                    recipients=[u.email],
                    html_body=html_body,
                )
                u.trial_reminder_sent = True
                sent += 1
                print(f"[OK] Rappel envoyé à {u.email}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERREUR] Échec d'envoi à {u.email} : {e}")

        db.session.commit()
        print(f"\nTerminé : {sent}/{len(candidates)} rappel(s) envoyé(s).")


if __name__ == "__main__":
    main()
