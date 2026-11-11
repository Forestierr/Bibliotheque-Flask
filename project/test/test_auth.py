from unittest.mock import MagicMock, patch

import pytest
from flask import get_flashed_messages

from project import create_app


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# Test affichage du formulaire de login
def test_login_get(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"login" in response.data or b"Login" in response.data


# Test connexion avec mauvais identifiants
def test_login_post_bad_credentials(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.os.getenv", return_value=""),
    ):
        mock_query.filter_by().first.return_value = None
        with client:
            client.post(
                "/login",
                data={"email": "test@test.com", "password": "wrong"},
                follow_redirects=True,
            )
            flashed = get_flashed_messages()
        assert any(
            "Vérifier si votre email et votre mot de passe sont correcte." in msg
            for msg in flashed
        )


# Test connexion avec bons identifiants
def test_login_post_success(client, app):
    with app.app_context():
        mock_user = MagicMock()
        mock_user.password = "hash"  # Nécessaire pour check_password_hash
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.get_id.return_value = 1
        with (
            patch("project.auth.User.query") as mock_query,
            patch("project.auth.login_user", autospec=True) as mock_login_user,
            patch("project.auth.check_password_hash", return_value=True),
            patch("project.auth.os.getenv", return_value=""),
        ):
            mock_query.filter_by().first.return_value = mock_user
            with client:
                response = client.post(
                    "/login",
                    data={"email": "test@test.com", "password": "good"},
                    follow_redirects=False,
                )
                assert response.status_code == 302
                assert "/dashboard" in response.headers.get("Location", "")
                assert mock_login_user.call_count == 1


# Test connexion sans CAPTCHA
def test_login_post_missing_captcha(client, app):
    with (
        app.app_context(),
        patch("project.auth.os.getenv", return_value="dummy_secret"),
        client,
    ):
        client.post(
            "/login",
            data={"email": "test@test.com", "password": "good"},
            follow_redirects=True,
        )
        flashed = get_flashed_messages()
        assert any("Veuillez compléter le CAPTCHA." in msg for msg in flashed)


# Test affichage du formulaire d'inscription
def test_signup_get(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert b"signup" in response.data or b"Signup" in response.data


# Test inscription avec email deja utilise
def test_signup_post_email_exists(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.os.getenv", return_value=""),
    ):
        mock_query.filter_by().first.return_value = MagicMock()
        with client:
            client.post(
                "/signup",
                data={"email": "test@test.com", "password": "1234"},
                follow_redirects=True,
            )
            flashed = get_flashed_messages()
        assert any("Cette email est déjà utilisé." in msg for msg in flashed)


# Test inscription avec succes
def test_signup_post_success(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.db.session"),
        patch("project.auth.send_email_verification") as mock_send_email,
        patch("project.auth.os.getenv", return_value=""),
    ):
        mock_query.filter_by().first.return_value = None
        with client:
            response = client.post(
                "/signup",
                data={"email": "test2@test.com", "password": "1234"},
                follow_redirects=True,
            )
            assert response.status_code in (200, 302)
            mock_send_email.assert_called_once()


# Test déconnexion
def test_logout(client, app):
    with app.app_context(), patch("project.auth.logout_user") as mock_logout, client:
        response = client.get("/logout", follow_redirects=True)
        assert response.status_code in (200, 302)
        mock_logout.assert_called_once()


# Test configuration de la durée des sessions
def test_session_lifetimes_config(app):
    from datetime import timedelta

    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=7)
    assert app.config["REMEMBER_COOKIE_DURATION"] == timedelta(days=30)
    assert app.config["REMEMBER_COOKIE_REFRESH_EACH_REQUEST"] is True


# Test présence du champ remember dans le formulaire
def test_login_remember_me_checkbox_in_template(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b'name="remember"' in response.data


# Test connexion avec option "se souvenir de moi"
def test_login_post_with_remember_me(client, app):
    from flask import session

    with app.app_context():
        mock_user = MagicMock()
        mock_user.password = "hash"
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.get_id.return_value = 1
        with (
            patch("project.auth.User.query") as mock_query,
            patch("project.auth.login_user", autospec=True) as mock_login_user,
            patch("project.auth.check_password_hash", return_value=True),
            patch("project.auth.os.getenv", return_value=""),
        ):
            mock_query.filter_by().first.return_value = mock_user
            with client:
                response = client.post(
                    "/login",
                    data={
                        "email": "test@test.com",
                        "password": "good",
                        "remember": "on",
                    },
                    follow_redirects=False,
                )
                assert response.status_code == 302
                assert mock_login_user.call_count == 1
                assert mock_login_user.call_args[1]["remember"] is True
                assert session.permanent is True


# Test connexion sans option "se souvenir de moi"
def test_login_post_without_remember_me(client, app):
    from flask import session

    with app.app_context():
        mock_user = MagicMock()
        mock_user.password = "hash"
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.get_id.return_value = 1
        with (
            patch("project.auth.User.query") as mock_query,
            patch("project.auth.login_user", autospec=True) as mock_login_user,
            patch("project.auth.check_password_hash", return_value=True),
            patch("project.auth.os.getenv", return_value=""),
        ):
            mock_query.filter_by().first.return_value = mock_user
            with client:
                response = client.post(
                    "/login",
                    data={"email": "test@test.com", "password": "good"},
                    follow_redirects=False,
                )
                assert response.status_code == 302
                assert mock_login_user.call_count == 1
                assert mock_login_user.call_args[1]["remember"] is False
                assert session.permanent is True


# Test redirection de /login si deja connecte
def test_login_get_authenticated_redirects(client, app):
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        with patch("project.auth.current_user", mock_user):
            response = client.get("/login", follow_redirects=False)
            assert response.status_code == 302
            assert "/dashboard" in response.headers.get("Location", "")


# Test redirection de /signup si deja connecte
def test_signup_get_authenticated_redirects(client, app):
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        with patch("project.auth.current_user", mock_user):
            response = client.get("/signup", follow_redirects=False)
            assert response.status_code == 302
            assert "/dashboard" in response.headers.get("Location", "")


# Test affichage des limites du plan gratuit et du mode Premium sur /signup
def test_signup_page_displays_free_plan_and_quotas(client):
    response = client.get("/signup")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Vérification de l'accroche
    assert "Simplifiez la gestion de vos livres" in html

    # Vérification des quotas du plan gratuit (config_plans.py)
    assert "40" in html
    assert "élèves gérés" in html
    assert "500" in html
    assert "livres au catalogue" in html
    assert "10" in html
    assert "mois d'historique des prêts" in html
    assert "30" in html
    assert "scans de codes-barres par semaine" in html

    # Vérification de l'existence du mode Premium
    assert "Premium avec accès illimité" in html
    assert "/tarifs" in html

    # Vérification du bouton d'inscription épuré
    assert "S'inscrire et commencer gratuitement" in html


# Test affichage multilingue sur /signup
def test_signup_page_multilingual(client):
    # En anglais
    client.get("/set-lang/en", follow_redirects=True)
    res_en = client.get("/signup")
    html_en = res_en.get_data(as_text=True)
    assert "Simplify your classroom book management" in html_en
    assert "Sign up and get started for free" in html_en
    assert "managed students" in html_en
    assert "catalog books" in html_en

    # En allemand
    client.get("/set-lang/de", follow_redirects=True)
    res_de = client.get("/signup")
    html_de = res_de.get_data(as_text=True)
    assert "Vereinfachen Sie Ihre Klassenbuch-Verwaltung" in html_de
    assert "Registrieren und kostenlos starten" in html_de
    assert "verwaltete Schüler" in html_de


# Test conservation de l'email lors d'un échec de connexion
def test_login_retains_email_on_failure(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.os.getenv", return_value=""),
    ):
        mock_query.filter_by().first.return_value = None
        response = client.post(
            "/login",
            data={"email": "professeur@ecole.ch", "password": "mauvais_mot_de_passe"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'value="professeur@ecole.ch"' in html


# Test conservation de l'email et du nom lors d'un échec d'inscription
def test_signup_retains_email_and_name_on_failure(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.os.getenv", return_value=""),
    ):
        # Simule email déjà existant
        mock_query.filter_by().first.return_value = MagicMock()
        response = client.post(
            "/signup",
            data={
                "email": "existant@ecole.ch",
                "name": "Mme Dupont",
                "password": "motdepasse123",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'value="existant@ecole.ch"' in html
        assert 'value="Mme Dupont"' in html


def test_delete_user_account_preserves_isbn_books_and_removes_user_data(app):
    from project import db
    from project.models import Book, BookTags, Feedback, Loan, Student, Tags, User
    from project.query import delete_user_account

    with app.app_context():
        db.create_all()

        user = User(
            name="Prof Test",
            email="delete_me@test.com",
            password="hash",
            is_verified=True,
            plan="free",
        )
        db.session.add(user)
        db.session.commit()

        # Book with ISBN
        book_isbn = Book(
            title="Le Petit Prince",
            author="Saint-Exupéry",
            isbn="9782070612758",
            barcode="BAC-01",
            user_id=user.id,
        )
        # Book without ISBN
        book_no_isbn = Book(
            title="Livre Fait Maison",
            author="Enseignant",
            isbn=None,
            barcode="BAC-02",
            user_id=user.id,
        )
        db.session.add_all([book_isbn, book_no_isbn])
        db.session.commit()

        # Student & Tag
        student = Student(name="Dupont", firstname="Alice", user_id=user.id)
        tag = Tags(name="Roman", user_id=user.id)
        db.session.add_all([student, tag])
        db.session.commit()

        loan = Loan(student_id=student.id, book_id=book_isbn.id)
        book_tag = BookTags(book_id=book_isbn.id, tag_id=tag.id)
        db.session.add_all([loan, book_tag])
        db.session.commit()

        book_isbn_id = book_isbn.id
        book_no_isbn_id = book_no_isbn.id
        user_id = user.id

        delete_user_account(user, reason="too_expensive", details="Pas de budget")

        # Departure feedback is recorded

        departure_fb = Feedback.query.filter_by(category="depart").first()

        assert departure_fb is not None

        assert departure_fb.departure_reason == "too_expensive"

        assert departure_fb.author_email == "delete_me@test.com"

        assert "Pas de budget" in departure_fb.message

        assert departure_fb.user_id is None

        # User is deleted
        assert db.session.get(User, user_id) is None

        # Student, Loan, Tag are deleted
        assert Student.query.filter_by(user_id=user_id).first() is None
        assert Loan.query.filter_by(book_id=book_isbn_id).first() is None
        assert Tags.query.filter_by(user_id=user_id).first() is None

        # Book without ISBN is deleted
        assert db.session.get(Book, book_no_isbn_id) is None

        # Book with ISBN is PRESERVED for the collaborative database
        preserved = db.session.get(Book, book_isbn_id)
        assert preserved is not None
        assert preserved.user_id is None
        assert preserved.barcode is None
        assert preserved.title == "Le Petit Prince"
        assert preserved.isbn == "9782070612758"
        assert preserved.loans == []
        assert preserved.book_tags == []


def test_delete_account_post_route(app):
    from project import db
    from project.models import Book, Feedback, User

    with app.app_context():
        db.create_all()

        user = User(
            name="Marie Curie",
            email="marie@radium.fr",
            password="hash",
            is_verified=True,
            plan="free",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        book = Book(
            title="La radioactivité",
            author="Marie Curie",
            isbn="9780123456789",
            user_id=user_id,
        )
        db.session.add(book)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)

        res = client.post(
            "/delete_account",
            data={
                "deletion_reason": "too_expensive",
                "deletion_details": "Trop cher",
            },
            follow_redirects=False,
        )

        assert res.status_code == 302

        assert res.headers["Location"].endswith("/")

        departure_fb = Feedback.query.filter_by(category="depart").first()

        assert departure_fb is not None

        assert departure_fb.departure_reason == "too_expensive"

        assert "Trop cher" in departure_fb.message

        assert db.session.get(User, user_id) is None
        preserved = Book.query.filter_by(isbn="9780123456789").first()
        assert preserved is not None
        assert preserved.user_id is None


def test_reglage_danger_zone_shows_promo_retention_box(app):
    from project import db
    from project.models import User

    with app.app_context():
        db.create_all()

        user = User(
            name="Albert",
            email="albert@physique.ch",
            password="hash",
            is_verified=True,
            plan="free",
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)

        res = client.get("/reglage?tab=danger")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "modalDeleteAccount" in html
        assert "promoRetentionBox" in html
        assert "PROMO30" in html
        assert "too_expensive" in html
