"""
send_subscription_renewal_reminders.py: Envoi automatique d'e-mails de rappel pour le renouvellement annuel (à J-30).
Peut être appelé quotidiennement par une tâche cron.
Usage :
    python scripts/send_subscription_renewal_reminders.py [--dry-run] [--days-before 30]
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ajouter le dossier racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from project import create_app, db
from project.email import send_email_subscription_renewal_reminder
from project.models import User


def main():
    parser = argparse.ArgumentParser(
        description="Envoyer les emails de rappel de renouvellement annuel d'abonnement."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les utilisateurs ciblés sans envoyer d'e-mails.",
    )
    parser.add_argument(
        "--days-before",
        type=int,
        default=30,
        help="Fenêtre d'anticipation en jours (défaut : 30 jours).",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        now = datetime.now(UTC)
        threshold = now + timedelta(days=args.days_before)

        candidates = User.query.filter(
            User.plan == "premium",
            User.plan != "founder",
            User.subscription_end_at.isnot(None),
            User.subscription_end_at > now,
            User.subscription_end_at <= threshold,
            User.renewal_reminder_sent.is_(False),
        ).all()

        print(
            f"=== Rappels de renouvellement annuel ({len(candidates)} compte(s) ciblé(s) à J-{args.days_before}) ==="
        )
        for u in candidates:
            print(
                f"  - ID: {u.id} | Email: {u.email} | Échéance: {u.subscription_end_at} (reste {u.subscription_days_left}j)"
            )

        if not candidates or args.dry_run:
            return

        sent = 0
        for u in candidates:
            try:
                send_email_subscription_renewal_reminder(u)
                u.renewal_reminder_sent = True
                sent += 1
                print(f"[OK] Rappel de renouvellement envoyé à {u.email}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERREUR] Échec d'envoi à {u.email} : {e}")

        db.session.commit()
        print(f"\nTerminé : {sent}/{len(candidates)} rappel(s) envoyé(s).")


if __name__ == "__main__":
    main()
