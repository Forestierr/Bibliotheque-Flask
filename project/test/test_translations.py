from pathlib import Path

from project import LANGUAGES, create_app


def test_mo_files_exist():
    """Verify that compiled .mo translation files exist for every supported language."""
    base_dir = Path(__file__).resolve().parent.parent / "translations"

    for lang in LANGUAGES:
        mo_file = base_dir / lang / "LC_MESSAGES" / "messages.mo"
        assert mo_file.exists(), (
            f"Missing compiled translation file for '{lang}': {mo_file}"
        )
        assert mo_file.stat().st_size > 0, (
            f"Compiled translation file for '{lang}' is empty"
        )


def test_po_files_exist():
    """Verify that source .po translation files exist for every supported language."""
    base_dir = Path(__file__).resolve().parent.parent / "translations"

    for lang in LANGUAGES:
        po_file = base_dir / lang / "LC_MESSAGES" / "messages.po"
        assert po_file.exists(), f"Missing .po translation file for '{lang}': {po_file}"
        assert po_file.stat().st_size > 0, f".po translation file for '{lang}' is empty"


def test_translation_switching():
    """Test switching languages via /set-lang/<lang> route."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Switch to English
        res = client.get("/set-lang/en", follow_redirects=True)
        assert res.status_code == 200
        with client.session_transaction() as sess:
            assert sess.get("lang") == "en"

        # Check English rendering on login page
        res = client.get("/login")
        html = res.data.decode("utf-8")
        assert "Log In" in html
        assert "Forgot password?" in html

        # Switch to German
        res = client.get("/set-lang/de", follow_redirects=True)
        assert res.status_code == 200
        with client.session_transaction() as sess:
            assert sess.get("lang") == "de"

        # Check German rendering on login page
        res = client.get("/login")
        html = res.data.decode("utf-8")
        assert "Anmelden" in html
        assert "Passwort vergessen?" in html

        # Switch back to French
        res = client.get("/set-lang/fr", follow_redirects=True)
        assert res.status_code == 200
        with client.session_transaction() as sess:
            assert sess.get("lang") == "fr"

        # Check French rendering on login page
        res = client.get("/login")
        html = res.data.decode("utf-8")
        assert "Connexion" in html
        assert "Mot de passe oublié ?" in html


def test_user_preferred_language_persistence():
    """Verify that User.preferred_language is updated and persisted in DB."""
    from werkzeug.security import generate_password_hash

    from project import db
    from project.models import User

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
            "WTF_CSRF_ENABLED": False,
        }
    )

    with app.app_context():
        db.create_all()
        user = User(
            email="teacher@example.com",
            name="Professeur",
            password=generate_password_hash("password123", method="pbkdf2:sha256"),
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        assert user.preferred_language == "fr"

        import os
        from unittest.mock import patch

        with (
            patch.dict(os.environ, {"HCAPTCHA_SECRET_KEY": ""}),
            app.test_client() as client,
        ):
            # Login
            client.post(
                "/login",
                data={"email": "teacher@example.com", "password": "password123"},
                follow_redirects=True,
            )

            # Switch language to German
            client.get("/set-lang/de", follow_redirects=True)

            # Check DB updated
            updated_user = db.session.get(User, user_id)
            assert updated_user.preferred_language == "de"

            # Check /reglage POST updates preferred_language
            client.post(
                "/reglage",
                data={
                    "name": "Professeur",
                    "email": "teacher@example.com",
                    "preferred_language": "en",
                },
                follow_redirects=True,
            )

            updated_user = db.session.get(User, user_id)
            assert updated_user.preferred_language == "en"


def test_format_date_localization():
    """Verify that format_date adapts to the active locale in Jinja templates."""
    from datetime import datetime, timezone

    from flask import render_template_string

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    dt = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

    expected = {
        "fr": "5 sept. 2026",
        "en": "Sep 5, 2026",
        "de": "05.09.2026",
    }

    for lang, exp in expected.items():
        with app.test_request_context():
            from flask import session

            session["lang"] = lang
            rendered = render_template_string(
                "{{ format_date(dt, format='medium') }}", dt=dt
            )
            assert rendered == exp, f"Expected '{exp}' for {lang}, got '{rendered}'"
