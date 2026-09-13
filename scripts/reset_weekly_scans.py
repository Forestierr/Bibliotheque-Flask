"""
reset_weekly_scans.py: Réinitialisation hebdomadaire des scans gratuits pour les utilisateurs en mode gratuit.
Peut être appelé chaque dimanche à 00:00:00 UTC par une tâche cron.
Exemple crontab :
    0 0 * * 0 cd /path/to/project && .venv/bin/python scripts/reset_weekly_scans.py
Usage :
    python scripts/reset_weekly_scans.py [--dry-run] [--force]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ajouter le dossier racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from project import create_app, db
from project.models import User, get_current_scan_period_start


def main():
    parser = argparse.ArgumentParser(
        description="Réinitialiser les quotas hebdomadaires de scans pour les comptes gratuits."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les utilisateurs concernés sans modifier la base de données.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force la réinitialisation de tous les comptes gratuits avec scans > 0 même si déjà réinitialisés dans la période.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        now = datetime.now(timezone.utc)
        period_start = get_current_scan_period_start(now)

        query = User.query.filter(
            User.plan == "free",
            User.free_scans_used > 0,
        )

        if not args.force:
            query = query.filter(
                db.or_(
                    db.and_(
                        User.last_scan_reset_at.is_(None),
                        User.created_at < period_start,
                    ),
                    User.last_scan_reset_at < period_start,
                )
            )

        candidates = query.all()

        print(
            f"=== Réinitialisation hebdomadaire des scans ({len(candidates)} compte(s) concerné(s)) ==="
        )
        print(f"Date courante : {now.isoformat()}")
        print(f"Début de période (dimanche 00h00) : {period_start.isoformat()}")

        for u in candidates:
            print(
                f"  - ID: {u.id} | Email: {u.email} | Scans utilisés : {u.free_scans_used} | Dernier reset : {u.last_scan_reset_at}"
            )

        if not candidates or args.dry_run:
            if args.dry_run:
                print("Mode simulation (--dry-run) : aucune modification enregistrée.")
            else:
                print("Aucun utilisateur à réinitialiser.")
            return

        for u in candidates:
            u.free_scans_used = 0
            u.last_scan_reset_at = now

        db.session.commit()
        print(f"Succès : {len(candidates)} compte(s) réinitialisé(s) à 0 scans.")


if __name__ == "__main__":
    main()
