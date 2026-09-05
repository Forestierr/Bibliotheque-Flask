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
