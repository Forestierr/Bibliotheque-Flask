# models.py
# look at the file docs/model.png

import os
from datetime import UTC, datetime, timedelta

from flask_login import UserMixin
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from . import db

# Table d'association pour la relation Many-to-Many entre Book et Tags


class BookTags(db.Model):
    __tablename__ = "book_tags"
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), primary_key=True)


def get_current_scan_period_start(now=None) -> datetime:
    """
    Retourne la date/heure de début de la période courante de scans :
    chaque dimanche à 00:00:00 UTC (nuit du samedi au dimanche).
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    days_since_sunday = (now.weekday() + 1) % 7
    return (now - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    is_verified = db.Column(db.Boolean, default=False)
    newsletter_subscribed = db.Column(db.Boolean, default=True, nullable=False)
    preferred_language = db.Column(
        db.String(5), default="fr", nullable=False, server_default="fr"
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    plan = db.Column(
        db.String(20), default="free", server_default="free", nullable=False
    )
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    trial_reminder_sent = db.Column(
        db.Boolean, default=False, server_default="0", nullable=False
    )
    free_scans_used = db.Column(
        db.Integer, default=0, server_default="0", nullable=False
    )
    stripe_customer_id = db.Column(db.String(120), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True, index=True)
    stripe_subscription_status = db.Column(db.String(30), nullable=True)
    stripe_price_id = db.Column(db.String(120), nullable=True)
    subscription_end_at = db.Column(db.DateTime, nullable=True)
    last_scan_reset_at = db.Column(db.DateTime, nullable=True)

    def check_and_reset_weekly_scans(self) -> bool:
        """
        Vérifie si le dimanche à 00:00:00 UTC le plus récent est postérieur à la dernière
        réinitialisation de scans de l'utilisateur. Si oui, remet free_scans_used à 0.
        Retourne True si une réinitialisation a été effectuée.
        """
        now = datetime.now(UTC)
        period_start = get_current_scan_period_start(now)

        last_reset = self.last_scan_reset_at
        if last_reset is not None and last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=UTC)

        if last_reset is None:
            user_created = self.created_at
            if user_created is not None and user_created.tzinfo is None:
                user_created = user_created.replace(tzinfo=UTC)

            if user_created is not None and user_created < period_start:
                self.free_scans_used = 0
                self.last_scan_reset_at = now
                try:
                    db.session.commit()
                except Exception:  # noqa: BLE001
                    db.session.rollback()
                return True
            else:
                self.last_scan_reset_at = user_created or now
                try:
                    db.session.commit()
                except Exception:  # noqa: BLE001
                    db.session.rollback()
                return False

        if last_reset < period_start:
            self.free_scans_used = 0
            self.last_scan_reset_at = now
            try:
                db.session.commit()
            except Exception:  # noqa: BLE001
                db.session.rollback()
            return True
        return False

    @property
    def weekly_scans_left(self) -> int:
        """Nombre de scans gratuits restants pour la semaine courante."""
        from .config_plans import MAX_FREE_SCANS

        if self.is_premium:
            return 999999
        return max(0, MAX_FREE_SCANS - (self.free_scans_used or 0))

    @property
    def subscription_type(self) -> str | None:
        """Retourne le type d'abonnement ('monthly', 'yearly') pour les comptes premium."""
        if self.plan != "premium":
            return None
        if self.stripe_price_id:
            val = self.stripe_price_id.strip()

            # 1. Correspondance avec les variables d'environnement configurées
            yearly_prices = {
                os.getenv("STRIPE_PRICE_ID_YEARLY"),
                os.getenv("STRIPE_PRICE_YEARLY"),
            } - {None, ""}
            monthly_prices = {
                os.getenv("STRIPE_PRICE_ID_MONTHLY"),
                os.getenv("STRIPE_PRICE_MONTHLY"),
            } - {None, ""}

            if val in yearly_prices:
                return "yearly"
            if val in monthly_prices:
                return "monthly"

            # 2. Valeurs explicites (provenant des métadonnées de checkout ou tests : 'yearly', 'monthly', etc.)
            val_lower = val.lower()
            if val_lower in ("yearly", "year", "annual", "annuel"):
                return "yearly"
            if val_lower in ("monthly", "month", "mensuel"):
                return "monthly"

            # 3. Heuristique pour libellés contenant 'year'/'month' mais sans faux-positifs sur ID Stripe (price_...)
            if not val_lower.startswith("price_"):
                if "year" in val_lower:
                    return "yearly"
                if "month" in val_lower:
                    return "monthly"

        return "monthly"

    @property
    def is_canceling(self) -> bool:
        """Indique si l'abonnement a été résilié mais bénéficie encore de ses accès jusqu'à échéance."""
        if self.plan == "founder":
            return False
        # Cas 1 : abonnement premium avec date de fin programmée dans le futur
        if self.plan == "premium" and self.subscription_end_at:
            end_dt = (
                self.subscription_end_at.replace(tzinfo=UTC)
                if self.subscription_end_at.tzinfo is None
                else self.subscription_end_at
            )
            if datetime.now(UTC) < end_dt:
                return True
        # Cas 2 : abonnement résilié sur Stripe mais dans le délai de grâce
        return bool(self.stripe_subscription_status == "canceled" and self.is_in_trial)

    @property
    def effective_cancellation_date(self):
        """Date effective jusqu'à laquelle l'utilisateur conserve son accès complet."""
        if self.plan == "premium" and self.subscription_end_at:
            return self.subscription_end_at
        if self.stripe_subscription_status == "canceled" and self.trial_ends_at:
            return self.trial_ends_at
        return None

    @property
    def is_in_trial(self) -> bool:
        if self.plan in ("founder", "premium"):
            return False
        if self.trial_ends_at:
            end_dt = (
                self.trial_ends_at.replace(tzinfo=UTC)
                if self.trial_ends_at.tzinfo is None
                else self.trial_ends_at
            )
            return datetime.now(UTC) < end_dt
        return False

    @property
    def trial_days_left(self) -> int:
        if not self.is_in_trial or not self.trial_ends_at:
            return 0
        end_dt = (
            self.trial_ends_at.replace(tzinfo=UTC)
            if self.trial_ends_at.tzinfo is None
            else self.trial_ends_at
        )
        delta = end_dt - datetime.now(UTC)
        return max(0, delta.days + (1 if delta.seconds > 0 else 0))

    @property
    def effective_plan(self) -> str:
        if self.plan == "founder":
            return "founder"
        # Si abonnement premium avec date de fin échue -> free (sauf si en trial)
        if self.plan == "premium" and self.subscription_end_at:
            end_dt = (
                self.subscription_end_at.replace(tzinfo=UTC)
                if self.subscription_end_at.tzinfo is None
                else self.subscription_end_at
            )
            if datetime.now(UTC) >= end_dt:
                return "trial" if self.is_in_trial else "free"
        if self.plan == "premium" and self.stripe_subscription_status == "active":
            return "premium"
        # Abonnement résilié mais encore dans la période payée (cancel_at_period_end)
        # L'accès est maintenu (is_premium=True) mais on retourne "premium" pour cohérence UI
        if self.is_canceling:
            return "premium"
        if self.is_in_trial:
            return "trial"
        return "free"

    @property
    def is_premium(self) -> bool:
        if self.plan == "founder":
            return True
        # Si abonnement premium avec date de fin échue -> False (sauf si en trial)
        if self.plan == "premium" and self.subscription_end_at:
            end_dt = (
                self.subscription_end_at.replace(tzinfo=UTC)
                if self.subscription_end_at.tzinfo is None
                else self.subscription_end_at
            )
            if datetime.now(UTC) >= end_dt:
                return self.is_in_trial
        # "past_due" : Stripe tente de relancer le paiement pendant 3–7 jours (dunning period).
        # On conserve l'accès pendant cette période pour ne pas couper l'enseignant au premier échec.
        if self.plan == "premium" and self.stripe_subscription_status in (
            "active",
            "past_due",
        ):
            return True
        # Abonnement résilié mais période payée ou délai de grâce non échus
        if self.is_canceling:
            return True
        return self.is_in_trial

    # One-to-Many relationship with books
    books = relationship("Book", backref="user", lazy=True)  # User can have many books
    # One-to-Many relationship with students
    students = relationship(
        "Student", backref="user", lazy=True
    )  # User can have many students
    # One-to-Many relationship with tags
    tags = relationship("Tags", backref="user", lazy=True)  # User can have many tags
    # One-to-Many relationship with feedbacks
    feedbacks = relationship(
        "Feedback", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def get_verification_token(self):
        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        return serializer.dumps(self.email, salt="email-verify-" + self.password)

    @staticmethod
    def validate_verification_token(token: str, user_id: int):
        user = db.session.get(User, user_id)

        if not user:
            return None

        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        try:
            email = serializer.loads(
                token,
                salt="email-verify-" + user.password,
                max_age=86400,  # Token valid for 24 hours
            )
        except BadSignature:
            return None

        if email != user.email:
            return None

        return user

    def get_reset_password_token(self):
        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        return serializer.dumps(self.email, salt=self.password)

    @staticmethod
    def validate_reset_password_token(token: str, user_id: int):
        user = db.session.get(User, user_id)

        if not user:
            return None

        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        try:
            email = serializer.loads(
                token, salt=user.password, max_age=3600
            )  # Token valid for 1 hour
        except BadSignature:
            return None

        if email != user.email:
            return None

        return user

    def get_unsubscribe_token(self):
        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        return serializer.dumps(self.email, salt="newsletter-unsubscribe")

    @staticmethod
    def validate_unsubscribe_token(token: str, user_id: int):
        user = db.session.get(User, user_id)

        if not user:
            return None

        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        try:
            email = serializer.loads(token, salt="newsletter-unsubscribe")
        except BadSignature:
            return None

        if email != user.email:
            return None

        return user


class Book(db.Model):
    __tablename__ = "book"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    author = db.Column(db.String(100))
    editor = db.Column(db.String(100))
    year = db.Column(db.Integer)
    type = db.Column(db.String(100))
    isbn = db.Column(db.String(100), nullable=True)
    barcode = db.Column(db.String(100), nullable=True, index=True)

    user_id = db.Column(
        db.Integer, ForeignKey("user.id")
    )  # Each book belongs to a user
    loans = relationship(
        "Loan", backref="book", lazy=True, cascade="all, delete-orphan"
    )
    book_tags = relationship(
        "BookTags", backref="book", lazy=True, cascade="all, delete-orphan"
    )


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    firstname = db.Column(db.String(100))

    # Many-to-One relationship with User
    user_id = db.Column(
        db.Integer, ForeignKey("user.id")
    )  # Each student belongs to a user
    # Loan relationship: One student can have multiple loans
    loans = relationship(
        "Loan", backref="student", lazy=True, cascade="all, delete-orphan"
    )


class Loan(db.Model):
    __tablename__ = "loan"
    id = db.Column(db.Integer, primary_key=True)
    date_loan = db.Column(db.Date)
    date_return = db.Column(db.Date)

    # Foreign keys to link Student and Book
    student_id = db.Column(db.Integer, ForeignKey("student.id"), nullable=False)
    book_id = db.Column(db.Integer, ForeignKey("book.id"), nullable=False)


class Tags(db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

    user_id = db.Column(db.Integer, ForeignKey("user.id"), nullable=False)
    book_tags = relationship(
        "BookTags", backref="tag", lazy=True, cascade="all, delete-orphan"
    )


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey("user.id"), nullable=False)
    category = db.Column(
        db.String(50), nullable=False
    )  # "suggestion", "bug", "general"
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    page_url = db.Column(db.String(255), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.String(30), default="nouveau", nullable=False
    )  # "nouveau", "en_cours", "traite"
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class NewsletterCampaign(db.Model):
    __tablename__ = "newsletter_campaign"
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    template = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(50), nullable=False)
    target_lang = db.Column(
        db.String(10), default="all", nullable=False, server_default="all"
    )
    total_recipients = db.Column(db.Integer, default=0, nullable=False)
    sent_count = db.Column(db.Integer, default=0, nullable=False)
    open_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    deliveries = relationship(
        "NewsletterDelivery",
        backref="campaign",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def open_rate(self) -> float:
        if self.sent_count > 0:
            return round((self.open_count / self.sent_count) * 100, 1)
        return 0.0


class NewsletterDelivery(db.Model):
    __tablename__ = "newsletter_delivery"
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        ForeignKey("newsletter_campaign.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    email = db.Column(db.String(255), nullable=False)
    tracking_token = db.Column(db.String(64), unique=True, index=True, nullable=False)
    status = db.Column(
        db.String(30), default="pending", nullable=False
    )  # "pending", "sent", "failed"
    sent_at = db.Column(db.DateTime, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=True)
    open_count = db.Column(db.Integer, default=0, nullable=False)

    user = relationship("User", backref="newsletter_deliveries", lazy=True)
