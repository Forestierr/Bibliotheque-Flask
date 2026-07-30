import logging
import os


class MailCriticalHandler(logging.Handler):
    def __init__(self, mail_instance, app, recipients):
        print("Init MailCriticalHandler")
        super().__init__(level=logging.ERROR)
        self.mail = mail_instance
        self.app = app
        self.recipients = recipients

    def emit(self, record):
        print("Sending error email")
        try:
            with self.app.app_context():  # Assurez-vous d'utiliser le contexte Flask
                sender = os.getenv("MAIL_USERNAME")
                recipients = [os.getenv("MAIL_USERNAME")]
                subject = f"[{record.levelname}] in {record.name}"
                body = self.format(record)  # Format du message de log
                from .email import send_email

                send_email(subject, sender, recipients, body)
        except Exception as e:
            print(f"Failed to send log email: {e}")
