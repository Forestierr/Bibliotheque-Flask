from unittest.mock import MagicMock, patch

import pytest
from flask import get_flashed_messages

from project import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
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
    with app.app_context(), patch("project.auth.User.query") as mock_query:
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


# Test affichage du formulaire d'inscription
def test_signup_get(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert b"signup" in response.data or b"Signup" in response.data


# Test inscription avec email déjà utilisé
def test_signup_post_email_exists(client, app):
    with app.app_context(), patch("project.auth.User.query") as mock_query:
        mock_query.filter_by().first.return_value = MagicMock()
        with client:
            client.post(
                "/signup",
                data={"email": "test@test.com", "password": "1234"},
                follow_redirects=True,
            )
            flashed = get_flashed_messages()
        assert any("Cette email est déjà utilisé." in msg for msg in flashed)


# Test inscription avec succès
def test_signup_post_success(client, app):
    with (
        app.app_context(),
        patch("project.auth.User.query") as mock_query,
        patch("project.auth.db.session"),
        patch("project.auth.send_email_verification") as mock_send_email,
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
