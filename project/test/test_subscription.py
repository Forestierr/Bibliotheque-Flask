import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from project import create_app, db
from project.config_plans import (
    MAX_FREE_BOOKS,
    MAX_FREE_STUDENTS,
)
from project.models import Book, Student, User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-subscription",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_trial_period_attributes():
    """Vérifie la gestion de la période d'essai sur le modèle User."""
    now = datetime.now(timezone.utc)

    # Utilisateur en période d'essai valide (15 jours restants)
    user_trial = User(
        email="trial@test.com",
        plan="free",
        trial_ends_at=now + timedelta(days=15),
    )
    assert user_trial.is_in_trial is True
    assert user_trial.trial_days_left in (14, 15)
    assert user_trial.effective_plan == "trial"
    assert user_trial.is_premium is True

    # Utilisateur avec essai expiré
    user_expired = User(
        email="expired@test.com",
        plan="free",
        trial_ends_at=now - timedelta(days=1),
    )
    assert user_expired.is_in_trial is False
    assert user_expired.trial_days_left == 0
    assert user_expired.effective_plan == "free"
    assert user_expired.is_premium is False

    # Membre fondateur
    user_founder = User(email="founder@test.com", plan="founder")
    assert user_founder.effective_plan == "founder"
    assert user_founder.is_premium is True

    # Abonné premium actif
    user_premium = User(
        email="premium@test.com",
        plan="premium",
        stripe_subscription_status="active",
    )
    assert user_premium.effective_plan == "premium"
    assert user_premium.is_premium is True

    # Abonné premium avec paiement en retard (past_due) :
    # Stripe relance la facturation pendant 3–7 jours (dunning period).
    # L'enseignant conserve l'accès Premium pour ne pas être coupé au premier échec.
    user_past_due = User(
        email="pastdue@test.com",
        plan="premium",
        stripe_subscription_status="past_due",
    )
    assert user_past_due.effective_plan == "free"  # pas "premium actif" dans l'UI
    assert user_past_due.is_premium is True  # mais accès maintenu pendant dunning


def test_student_quota_enforcement_free_user(client, app):
    """Vérifie le blocage du 41ème élève pour un utilisateur gratuit."""
    with app.app_context():
        user = User(
            id=10,
            email="free_teacher@test.com",
            plan="free",
            trial_ends_at=None,
        )
        db.session.add(user)
        # Création de 40 élèves
        students = [
            Student(id=100 + i, name=f"Nom{i}", firstname=f"Prenom{i}", user_id=10)
            for i in range(MAX_FREE_STUDENTS)
        ]
        db.session.add_all(students)
        db.session.commit()

    mock_user = MagicMock(id=10, is_authenticated=True, is_premium=False)
    with patch("flask_login.utils._get_user", return_value=mock_user):
        # 1. Tentative ajout formulaire classique (doit rediriger vers /tarifs avec code 302)
        resp_form = client.post(
            "/eleve/ajout",
            data={"name": "41eme", "firstname": "Eleve"},
            follow_redirects=False,
        )
        assert resp_form.status_code == 302
        assert "/tarifs" in resp_form.headers.get("Location", "")

        # 2. Tentative ajout via AJAX (doit renvoyer 403 quota_reached)
        resp_ajax = client.post(
            "/eleve/ajout",
            data={"name": "41eme", "firstname": "Eleve"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp_ajax.status_code == 403
        data = resp_ajax.get_json()
        assert data["error"] == "quota_reached"


def test_student_dynamic_quota_reopening(client, app):
    """Vérifie que la suppression d'un élève libère immédiatement la place pour en ajouter un autre."""
    with app.app_context():
        user = User(id=11, email="dynamic@test.com", plan="free", trial_ends_at=None)
        db.session.add(user)
        students = [
            Student(id=200 + i, name=f"Nom{i}", firstname=f"Prenom{i}", user_id=11)
            for i in range(MAX_FREE_STUDENTS)
        ]
        db.session.add_all(students)
        db.session.commit()

        # Supprimer 1 élève
        student_to_delete = db.session.get(Student, 200)
        db.session.delete(student_to_delete)
        db.session.commit()

        count = Student.query.filter_by(user_id=11).count()
        assert count == MAX_FREE_STUDENTS - 1

    mock_user = MagicMock(id=11, is_authenticated=True, is_premium=False)
    with patch("flask_login.utils._get_user", return_value=mock_user):
        # Ajout du nouvel élève maintenant autorisé
        resp = client.post(
            "/eleve/ajout",
            data={"name": "Remplacant", "firstname": "Nouveau"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/eleve" in resp.headers.get("Location", "")

        with app.app_context():
            assert Student.query.filter_by(user_id=11).count() == MAX_FREE_STUDENTS


def test_book_quota_enforcement(client, app):
    """Vérifie le blocage à 500 livres pour un compte gratuit."""
    with app.app_context():
        user = User(id=12, email="books@test.com", plan="free", trial_ends_at=None)
        db.session.add(user)
        db.session.commit()

    mock_user = MagicMock(id=12, is_authenticated=True, is_premium=False)
    with (
        patch("flask_login.utils._get_user", return_value=mock_user),
        patch("project.livre.get_books_count", return_value=MAX_FREE_BOOKS),
    ):
        resp = client.post(
            "/livre/ajout",
            data={"title": "Livre en trop", "author": "Auteur"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/tarifs" in resp.headers.get("Location", "")


def test_barcode_scan_quota_enforcement(client, app):
    """Vérifie le compteur et le blocage à 30 scans codes-barres pour un utilisateur gratuit."""
    with app.app_context():
        user = User(
            id=13,
            email="scans@test.com",
            plan="free",
            free_scans_used=29,
            trial_ends_at=None,
        )
        db.session.add(user)
        db.session.commit()

    with app.app_context():
        u = db.session.get(User, 13)

    with (
        patch("flask_login.utils._get_user", return_value=u),
        patch("project.livre.get_books_by_barcode", return_value=[]),
        patch("project.livre.get_books_by_isbn", return_value=[MagicMock(id=1)]),
    ):
        # 30ème scan : autorisé (code 200) et compteur incrémenté
        resp_30 = client.get("/livre/9781234567890/exist")
        assert resp_30.status_code == 200
        assert u.free_scans_used == 30

        # 31ème scan : bloqué (code 403, error: scan_limit_reached)
        resp_31 = client.get("/livre/9781234567890/exist")
        assert resp_31.status_code == 403
        data = resp_31.get_json()
        assert data["error"] == "scan_limit_reached"


def test_premium_required_protection_on_exports(client, app):
    """Vérifie que les exports Excel sont protégés par @premium_required."""
    with app.app_context():
        user_free = User(
            id=14, email="export_free@test.com", plan="free", trial_ends_at=None
        )
        db.session.add(user_free)
        db.session.commit()

    # Utilisateur non connecté -> redirigé vers login
    resp_anon = client.get("/export/books")
    assert resp_anon.status_code == 302
    assert "/login" in resp_anon.headers.get("Location", "")

    # Utilisateur gratuit -> redirigé vers tarifs
    mock_free = MagicMock(id=14, is_authenticated=True, is_premium=False)
    with patch("flask_login.utils._get_user", return_value=mock_free):
        resp_free = client.get("/export/books")
        assert resp_free.status_code == 302
        assert "/tarifs" in resp_free.headers.get("Location", "")

    # Utilisateur premium -> autorisé (200)
    mock_prem = MagicMock(id=14, is_authenticated=True, is_premium=True)
    with patch("flask_login.utils._get_user", return_value=mock_prem):
        resp_prem = client.get("/export/books")
        assert resp_prem.status_code == 200


def test_stripe_webhook_checkout_session_completed(client, app):
    """Vérifie l'activation de l'abonnement lors du webhook checkout.session.completed."""
    with app.app_context():
        user = User(id=15, email="stripe_checkout@test.com", plan="free")
        db.session.add(user)
        db.session.commit()

    payload = {
        "id": "evt_test_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "15",
                "customer": "cus_123456",
                "subscription": "sub_987654",
            }
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=payload),
        patch("stripe.Subscription.retrieve") as mock_sub,
    ):
        mock_sub.return_value = MagicMock(
            status="active",
            items=MagicMock(data=[MagicMock(price=MagicMock(id="price_monthly_test"))]),
        )

        resp = client.post(
            "/webhook/stripe",
            data=json.dumps(payload),
            headers={"Stripe-Signature": "test_sig"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            u = db.session.get(User, 15)
            assert u.plan == "premium"
            assert u.stripe_customer_id == "cus_123456"
            assert u.stripe_subscription_id == "sub_987654"
            assert u.stripe_subscription_status == "active"
            assert u.is_premium is True


def test_stripe_webhook_customer_subscription_deleted_no_data_loss(client, app):
    """Vérifie la résiliation Stripe : bascule sur free SANS suppression de données."""
    with app.app_context():
        user = User(
            id=16,
            email="cancel@test.com",
            plan="premium",
            stripe_customer_id="cus_canceller",
            stripe_subscription_id="sub_canceller",
            stripe_subscription_status="active",
        )
        db.session.add(user)
        # Création de livres et élèves
        b = Book(id=50, title="Livre Conservé", user_id=16)
        s = Student(id=50, name="Eleve", firstname="Conserve", user_id=16)
        db.session.add_all([b, s])
        db.session.commit()

    payload = {
        "id": "evt_test_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_canceller",
                "customer": "cus_canceller",
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=payload):
        resp = client.post(
            "/webhook/stripe",
            data=json.dumps(payload),
            headers={"Stripe-Signature": "test_sig"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            u = db.session.get(User, 16)
            assert u.plan == "free"
            assert u.stripe_subscription_status == "canceled"
            # Grâce à la politique de délai de grâce de 48h, l'enseignant reste actif pendant 48h
            assert u.is_in_trial is True
            assert u.is_premium is True

            # Une fois le délai de grâce écoulé, l'accès premium retombe sur free
            u.trial_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.session.commit()
            assert u.is_in_trial is False
            assert u.is_premium is False

            # Politique de non-destruction des données vérifiée : livres et élèves intacts
            assert Book.query.filter_by(user_id=16).count() == 1
            assert Student.query.filter_by(user_id=16).count() == 1


def test_admin_set_plan_and_reset_scans(client, app):
    """Vérifie la mise à jour manuelle d'un plan et la réinitialisation des scans depuis l'administration."""
    with app.app_context():
        user = User(
            id=17,
            email="admin_target@test.com",
            plan="free",
            free_scans_used=30,
        )
        db.session.add(user)
        db.session.commit()

    # Changement en fondateur et remise à zéro des scans
    resp = client.post(
        "/admin/set_plan/17",
        data={"plan": "founder", "reset_scans": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        u = db.session.get(User, 17)
        assert u.plan == "founder"
        assert u.free_scans_used == 0
        assert u.is_premium is True


def test_tarifs_no_redirect_loop_and_founder_reglage_display(client, app):
    """Vérifie que /tarifs répond en 200 (sans boucle 302) et que les réglages d'un fondateur n'affichent ni couronne ni incitation Premium."""
    with app.app_context():
        founder = User(
            id=18,
            name="Alice Fondatrice",
            email="founder_test@example.com",
            plan="founder",
        )
        free_user = User(
            id=19,
            name="Bob Gratuit",
            email="free_test@example.com",
            plan="free",
            trial_ends_at=None,
        )
        premium_user = User(
            id=20,
            name="Claire Premium",
            email="claire_prem@example.com",
            plan="premium",
            stripe_subscription_status="active",
            stripe_customer_id="cus_claire",
            trial_ends_at=None,
        )
        db.session.add_all([founder, free_user, premium_user])
        db.session.commit()

    mock_founder = MagicMock()
    mock_founder.id = 18
    mock_founder.name = "Alice Fondatrice"
    mock_founder.email = "founder_test@example.com"
    mock_founder.plan = "founder"
    mock_founder.is_authenticated = True
    mock_founder.is_premium = True
    mock_founder.is_in_trial = False
    mock_founder.stripe_subscription_status = None
    mock_founder.preferred_language = "fr"

    mock_free = MagicMock()
    mock_free.id = 19
    mock_free.name = "Bob Gratuit"
    mock_free.email = "free_test@example.com"
    mock_free.plan = "free"
    mock_free.is_authenticated = True
    mock_free.is_premium = False
    mock_free.is_in_trial = False
    mock_free.stripe_subscription_status = None
    mock_free.preferred_language = "fr"

    # 1. Vérification que /tarifs répond en code 200 sans boucle 302
    resp_tarifs_anon = client.get("/tarifs", follow_redirects=False)
    assert resp_tarifs_anon.status_code == 200

    with patch("flask_login.utils._get_user", return_value=mock_founder):
        resp_tarifs_founder = client.get("/tarifs", follow_redirects=False)
        assert resp_tarifs_founder.status_code == 200

    # 2. Vérification de la page /reglage pour un membre fondateur
    with patch("flask_login.utils._get_user", return_value=mock_founder):
        resp_reglage_founder = client.get("/reglage")
        assert resp_reglage_founder.status_code == 200
        content = resp_reglage_founder.get_data(as_text=True)

        # Doit afficher le badge Membre Fondateur
        assert "Membre Fondateur" in content
        # Ne doit PAS comporter de couronne 👑
        assert "👑" not in content
        # Ne doit PAS proposer de passer à Premium
        assert "Passer à Premium" not in content
        assert "Passer à Premium (dès 5.- CHF/mois)" not in content
        # Ne doit PAS avoir de bouton de portail Stripe facturation
        assert "subscription/portal" not in content

    # 3. Vérification du tableau de bord pour un fondateur : pas de badge fondateur sur le dashboard
    with patch("flask_login.utils._get_user", return_value=mock_founder):
        resp_dash_founder = client.get("/dashboard")
        assert resp_dash_founder.status_code == 200
        dash_content = resp_dash_founder.get_data(as_text=True)
        assert "👑" not in dash_content

    # 4. Vérification de la page /reglage pour un utilisateur gratuit
    with patch("flask_login.utils._get_user", return_value=mock_free):
        resp_reglage_free = client.get("/reglage")
        assert resp_reglage_free.status_code == 200
        content_free = resp_reglage_free.get_data(as_text=True)
        # La carte Formule & Abonnement en bas propose toujours le passage à Premium
        assert "Passer à Premium (dès 5.- CHF/mois)" in content_free
        # Mais pas de bouton dans la boîte de profil supérieure (à côté du nom)
        assert 'class="button is-primary is-rounded is-small"' not in content_free
        # La navbar ne doit pas avoir de bouton "Passer Premium" à côté de Ressources
        assert "Passer Premium" not in content_free

    # 5. Vérification de la page /reglage pour un abonné Premium actif
    mock_premium = MagicMock()
    mock_premium.id = 20
    mock_premium.name = "Claire Premium"
    mock_premium.email = "claire_prem@example.com"
    mock_premium.plan = "premium"
    mock_premium.is_authenticated = True
    mock_premium.is_premium = True
    mock_premium.is_in_trial = False
    mock_premium.stripe_subscription_status = "active"
    mock_premium.stripe_customer_id = "cus_claire"
    mock_premium.preferred_language = "fr"

    with patch("flask_login.utils._get_user", return_value=mock_premium):
        resp_reglage_prem = client.get("/reglage")
        assert resp_reglage_prem.status_code == 200
        content_prem = resp_reglage_prem.get_data(as_text=True)
        assert "Abonnement Premium Actif" in content_prem
        assert "subscription/portal" in content_prem


def test_signup_without_free_trial(client, app):
    """Vérifie qu'un nouvel inscrit démarre directement en compte gratuit sans période d'essai."""
    with (
        patch("project.auth.send_email_verification"),
        patch.dict(os.environ, {"HCAPTCHA_SECRET_KEY": ""}),
    ):
        resp = client.post(
            "/signup",
            data={
                "name": "Nouveau Prof",
                "email": "nouveau_prof@test.com",
                "password": "Password123!",
                "password2": "Password123!",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    with app.app_context():
        user = User.query.filter_by(email="nouveau_prof@test.com").first()
        assert user is not None
        assert user.plan == "free"
        assert user.trial_ends_at is None
        assert user.is_in_trial is False
        assert user.is_premium is False


def test_paiement_page_display(client, app):
    """Vérifie l'affichage de la page de récapitulatif /paiement pour les formules annuelle et mensuelle."""
    # 1. Visiteur anonyme - formule annuelle par défaut
    resp_anon_yearly = client.get("/paiement")
    assert resp_anon_yearly.status_code == 200
    text = resp_anon_yearly.get_data(as_text=True)
    assert "Votre abonnement Premium" in text
    assert "30.-" in text
    assert "Créer un compte enseignant" in text

    # 2. Visiteur anonyme - formule mensuelle
    resp_anon_monthly = client.get("/paiement?plan_type=monthly")
    assert resp_anon_monthly.status_code == 200
    text_m = resp_anon_monthly.get_data(as_text=True)
    assert "5.-" in text_m

    # 3. Utilisateur connecté gratuit
    with app.app_context():
        user = User(id=30, email="connected_teacher@test.com", plan="free")
        db.session.add(user)
        db.session.commit()

    mock_user = MagicMock(id=30, is_authenticated=True, plan="free", is_premium=False)
    with patch("flask_login.utils._get_user", return_value=mock_user):
        resp_auth = client.get("/paiement?plan_type=yearly")
        assert resp_auth.status_code == 200
        text_auth = resp_auth.get_data(as_text=True)
        assert "btnSubmitCheckout" in text_auth
        assert "Procéder au paiement sécurisé" in text_auth


def test_portail_abonne_route(client, app):
    """Vérifie l'accès au portail de gestion d'abonnement /portail-abonne."""
    # 1. Non connecté -> redirection login
    resp_anon = client.get("/portail-abonne")
    assert resp_anon.status_code == 302
    assert "/login" in resp_anon.headers.get("Location", "")

    # 2. Connecté sans customer_id -> redirection réglage
    mock_no_cust = MagicMock(id=31, is_authenticated=True, stripe_customer_id=None)
    with patch("flask_login.utils._get_user", return_value=mock_no_cust):
        resp_no_cust = client.get("/portail-abonne")
        assert resp_no_cust.status_code == 302
        assert "/reglage" in resp_no_cust.headers.get("Location", "")

    # 3. Connecté avec customer_id -> redirection Stripe Portal
    mock_cust = MagicMock(
        id=32, is_authenticated=True, stripe_customer_id="cus_portal123"
    )
    mock_portal = MagicMock(url="https://billing.stripe.com/session/test_123")
    with (
        patch("flask_login.utils._get_user", return_value=mock_cust),
        patch("stripe.billing_portal.Session.create", return_value=mock_portal),
        patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_mock"}),
    ):
        resp_portal = client.get("/portail-abonne")
        assert resp_portal.status_code == 303
        assert (
            resp_portal.headers.get("Location")
            == "https://billing.stripe.com/session/test_123"
        )


def test_webhook_idempotency(client, app):
    """Vérifie que la réception multiple d'un même événement Stripe ne produit ni erreur ni modification superflue."""
    with app.app_context():
        user = User(id=33, email="idempotent@test.com", plan="free")
        db.session.add(user)
        db.session.commit()

    payload = {
        "id": "evt_idempotent_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "33",
                "customer": "cus_idem_123",
                "subscription": "sub_idem_456",
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=payload):
        # 1er appel : traite et active
        resp1 = client.post(
            "/webhook/stripe",
            data=json.dumps(payload),
            headers={"Stripe-Signature": "test_sig"},
            content_type="application/json",
        )
        assert resp1.status_code == 200

        with app.app_context():
            u = db.session.get(User, 33)
            assert u.plan == "premium"
            assert u.stripe_subscription_status == "active"

        # 2ème appel identique : doit être ignoré proprement (idempotent, 200 OK)
        with patch("project.subscription.db.session.commit") as mock_commit:
            resp2 = client.post(
                "/webhook/stripe",
                data=json.dumps(payload),
                headers={"Stripe-Signature": "test_sig"},
                content_type="application/json",
            )
            assert resp2.status_code == 200
            mock_commit.assert_not_called()


def test_stripe_webhook_csrf_exemption():
    """Vérifie formellement que /webhook/stripe est exempté de la protection CSRF de Flask-WTF."""
    csrf_app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-csrf",
        }
    )
    with csrf_app.app_context():
        db.create_all()

    test_client = csrf_app.test_client()

    payload = {
        "id": "evt_csrf_test",
        "type": "checkout.session.completed",
        "data": {"object": {}},
    }

    with patch("stripe.Webhook.construct_event", return_value=payload):
        # Envoi d'une requête POST sans token CSRF
        resp = test_client.post(
            "/webhook/stripe",
            data=json.dumps(payload),
            headers={"Stripe-Signature": "test_sig"},
            content_type="application/json",
        )
        # Ne doit PAS renvoyer 400 Bad Request ("The CSRF session token is missing")
        assert resp.status_code == 200


def test_admin_set_plan_free_resets_trial_ends_at(client, app):
    """Vérifie que basculer un utilisateur sur 'free' efface complètement trial_ends_at."""
    with app.app_context():
        user = User(
            id=55,
            email="to_free@test.com",
            plan="premium",
            stripe_subscription_status="active",
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=20),
        )
        db.session.add(user)
        db.session.commit()

        # 1. Passage en free sans trial_days -> trial_ends_at doit être None
        client.post(
            "/admin/set_plan/55",
            data={"plan": "free", "trial_days": ""},
        )
        updated = db.session.get(User, 55)
        assert updated.plan == "free"
        assert updated.trial_ends_at is None
        assert updated.effective_plan == "free"

        # 2. Passage en trial avec trial_days = 0 -> trial_ends_at doit être None
        client.post(
            "/admin/set_plan/55",
            data={"plan": "trial", "trial_days": "0"},
        )
        updated2 = db.session.get(User, 55)
        assert updated2.plan == "free"
        assert updated2.trial_ends_at is None
        assert updated2.effective_plan == "free"


def test_admin_coupons_create_uses_modern_stripe_promotion(client, app):
    """Vérifie la création d'un code promo avec le paramètre promotion moderne de Stripe."""
    with (
        patch("os.getenv", return_value="sk_test_mock"),
        patch("stripe.Coupon.create") as mock_coupon_create,
        patch("stripe.PromotionCode.create") as mock_promo_create,
        patch("stripe.Coupon.list") as mock_coupon_list,
        patch("stripe.PromotionCode.list") as mock_promo_list,
    ):
        mock_coupon_create.return_value = MagicMock(id="coup_test123")
        mock_coupon_list.return_value = MagicMock(data=[])
        mock_promo_list.return_value = MagicMock(data=[])

        resp = client.post(
            "/admin/coupons",
            data={
                "code": "RENTREE50",
                "discount_type": "percent",
                "discount_value": "50",
                "duration": "once",
                "max_redemptions": "100",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Vérifier que Coupon.create a bien été appelé
        mock_coupon_create.assert_called_once_with(
            duration="once",
            name="Code RENTREE50",
            percent_off=50.0,
        )

        # Vérifier que PromotionCode.create a été appelé avec promotion={'type': 'coupon', 'coupon': ...}
        mock_promo_create.assert_called_once_with(
            promotion={"type": "coupon", "coupon": "coup_test123"},
            code="RENTREE50",
            max_redemptions=100,
        )


def test_user_is_canceling_attributes():
    """Vérifie la gestion des attributs is_canceling et effective_cancellation_date."""
    now = datetime.now(timezone.utc)
    future_date = now + timedelta(days=12)

    # Utilisateur avec résiliation programmée
    user_canceling = User(
        email="canceling@test.com",
        plan="premium",
        stripe_subscription_status="active",
        subscription_end_at=future_date,
    )
    assert user_canceling.is_canceling is True
    assert user_canceling.is_premium is True
    assert user_canceling.effective_cancellation_date == future_date

    # Utilisateur dont la date de fin est dépassée
    user_ended = User(
        email="ended@test.com",
        plan="premium",
        stripe_subscription_status="canceled",
        subscription_end_at=now - timedelta(days=1),
    )
    assert user_ended.is_canceling is False

    # Membre fondateur (ne doit jamais être considéré comme canceling)
    user_founder = User(
        email="founder_cancel@test.com",
        plan="founder",
        subscription_end_at=future_date,
    )
    assert user_founder.is_canceling is False


def test_reglage_displays_cancellation_info(app):
    """Vérifie que la page /reglage indique la résiliation programmée et la date d'échéance."""
    future_date = datetime.now(timezone.utc) + timedelta(days=15)
    with app.app_context():
        user = User(
            id=88,
            email="canceling_teacher@test.com",
            plan="premium",
            stripe_subscription_status="active",
            stripe_customer_id="cus_canceling_test",
            subscription_end_at=future_date,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = "88"

        res = client.get("/reglage")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert "Résiliation programmée" in html
        assert "Abonnement résilié" in html
        assert "Réactiver ou modifier mon abonnement" in html


def test_stripe_webhook_subscription_updated_cancel_at_period_end(client, app):
    """Vérifie que le webhook customer.subscription.updated enregistre bien subscription_end_at."""
    with app.app_context():
        user = User(
            id=99,
            email="cancel_webhook@test.com",
            plan="premium",
            stripe_customer_id="cus_hook_cancel",
            stripe_subscription_id="sub_hook_cancel",
            stripe_subscription_status="active",
        )
        db.session.add(user)
        db.session.commit()

        future_timestamp = int(
            (datetime.now(timezone.utc) + timedelta(days=20)).timestamp()
        )
        payload = {
            "id": "evt_sub_update_cancel",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_hook_cancel",
                    "customer": "cus_hook_cancel",
                    "status": "active",
                    "cancel_at_period_end": True,
                    "cancel_at": future_timestamp,
                }
            },
        }

        with patch("stripe.Webhook.construct_event", return_value=payload):
            resp = client.post(
                "/webhook/stripe",
                data=json.dumps(payload),
                headers={"Stripe-Signature": "sig"},
                content_type="application/json",
            )
            assert resp.status_code == 200

        updated_user = db.session.get(User, 99)
        assert updated_user.subscription_end_at is not None
        assert updated_user.is_canceling is True
        assert updated_user.is_premium is True
