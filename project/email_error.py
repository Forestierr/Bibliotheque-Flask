import logging
import os


class MailCriticalHandler(logging.Handler):
    def __init__(self, mail_instance, app, recipients):
        super().__init__(level=logging.ERROR)
        self.mail = mail_instance
        self.app = app
        self.recipients = recipients
        self._is_emitting = False

    def emit(self, record):
        # Éviter les boucles récursives si l'envoi d'email journalise lui-même une erreur
        if self._is_emitting or "email" in record.name.lower():
            return

        recipient_email = self.recipients or os.getenv("MAIL_USERNAME")
        if not recipient_email:
            return

        self._is_emitting = True
        try:
            with self.app.app_context():
                sender = os.getenv("MAIL_USERNAME") or recipient_email
                recipients = [recipient_email]
                subject = f"[{record.levelname}] in {record.name}"
                body = self.format(record)
                from .email import send_email

                send_email(subject, sender, recipients, body)
        except Exception:  # noqa: BLE001, S110
            pass
        finally:
            self._is_emitting = False
