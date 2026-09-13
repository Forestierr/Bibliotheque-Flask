"""
scheduler.py - Thread d'arrière-plan pour les tâches de maintenance serveur.
Remplace les tâches cron externes pour :
1. La réinitialisation hebdomadaire des scans le dimanche à 00:00:00 UTC.
2. La rétrogradation en mode gratuit des abonnements résiliés dont l'échéance est passée.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from . import db
from .models import User, get_current_scan_period_start

logger = logging.getLogger(__name__)

_scheduler_lock = threading.Lock()
_scheduler_started = False


def reset_weekly_scans(app) -> int:
    """
    Réinitialise le compteur de scans à 0 pour les comptes gratuits
    si la période courante a changé (chaque dimanche à 00:00:00 UTC).
    Retourne le nombre d'utilisateurs réinitialisés.
    """
    with app.app_context():
        now = datetime.now(timezone.utc)
        period_start = get_current_scan_period_start(now)

        query = User.query.filter(
            User.plan == "free",
            User.free_scans_used > 0,
            db.or_(
                db.and_(
                    User.last_scan_reset_at.is_(None),
                    User.created_at < period_start,
                ),
                User.last_scan_reset_at < period_start,
            ),
        )

        candidates = query.all()
        if not candidates:
            return 0

        for u in candidates:
            u.free_scans_used = 0
            u.last_scan_reset_at = now

        try:
            db.session.commit()
            logger.info(
                "Scheduler: %d compte(s) gratuit(s) réinitialisé(s) à 0 scans.",
                len(candidates),
            )
            return len(candidates)
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.error(
                "Scheduler: Erreur lors de la réinitialisation des scans : %s", e
            )
            return 0


def downgrade_expired_subscriptions(app) -> int:
    """
    Bascule automatiquement sur le plan gratuit ('free') les utilisateurs premium
    dont la date de fin d'abonnement est échue (subscription_end_at <= now).
    Ne dégrade JAMAIS un Membre Fondateur.
    Retourne le nombre d'utilisateurs rétrogradés.
    """
    with app.app_context():
        now = datetime.now(timezone.utc)

        # Les utilisateurs premium non-fondateurs dont l'accès est arrivé à échéance
        expired_users = User.query.filter(
            User.plan == "premium",
            User.plan != "founder",
            User.subscription_end_at.isnot(None),
            User.subscription_end_at <= now,
        ).all()

        if not expired_users:
            return 0

        for u in expired_users:
            u.plan = "free"
            u.stripe_subscription_status = "canceled"
            u.subscription_end_at = None
            u.trial_ends_at = None

        try:
            db.session.commit()
            logger.info(
                "Scheduler: %d compte(s) premium échu(s) basculé(s) en mode gratuit.",
                len(expired_users),
            )
            return len(expired_users)
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.error(
                "Scheduler: Erreur lors de la rétrogradation des abonnements échus : %s",
                e,
            )
            return 0


def _should_run_tasks(app, min_interval_seconds: int) -> bool:
    """
    Coordination multi-workers (Gunicorn -w 4) via un fichier horodaté dans instance/.
    Permet d'éviter que plusieurs workers n'exécutent simultanément les mêmes requêtes.
    """
    lock_file = os.path.join(app.instance_path, ".scheduler_last_run.json")
    now_ts = time.time()

    try:
        os.makedirs(app.instance_path, exist_ok=True)
        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    last_run = data.get("last_run", 0)
                    if now_ts - last_run < min_interval_seconds:
                        return False
            except Exception:  # noqa: BLE001, S110
                pass

        # Écriture du nouvel horodatage
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump({"last_run": now_ts}, f)
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("Scheduler: Impossible de vérifier le lock multi-workers : %s", e)
        return True


def run_maintenance_tasks(app, min_interval_seconds: int = 600) -> dict:
    """
    Exécute toutes les tâches de maintenance serveur si l'intervalle est respecté.
    Retourne un résumé d'exécution.
    """
    if not _should_run_tasks(app, min_interval_seconds):
        return {"executed": False, "reason": "rate_limited"}

    scans_reset = reset_weekly_scans(app)
    downgraded = downgrade_expired_subscriptions(app)

    return {
        "executed": True,
        "scans_reset": scans_reset,
        "downgraded_subscriptions": downgraded,
    }


def start_background_scheduler(app, interval_seconds: int = 600):
    """
    Démarre un thread d'arrière-plan (daemon) dans le processus Flask
    pour exécuter périodiquement les tâches de maintenance.
    Ignoré si l'application est en mode TESTING.
    """
    global _scheduler_started

    if app.config.get("TESTING"):
        return None

    with _scheduler_lock:
        if _scheduler_started:
            return None
        _scheduler_started = True

    def _worker():
        logger.info(
            "Scheduler d'arrière-plan démarré (intervalle: %d secondes).",
            interval_seconds,
        )
        # Attente initiale de 5 secondes pour laisser le serveur finaliser son démarrage
        time.sleep(5)

        while True:
            try:
                run_maintenance_tasks(app, min_interval_seconds=interval_seconds - 30)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Erreur inattendue dans le scheduler d'arrière-plan : %s", e
                )

            time.sleep(interval_seconds)

    thread = threading.Thread(
        target=_worker, name="server-maintenance-scheduler", daemon=True
    )
    thread.start()
    return thread
