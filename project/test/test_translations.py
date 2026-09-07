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


def test_query_param_language_selection():
    """Verify that ?lang= query parameter sets locale and persists into session."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Request with ?lang=en
        res = client.get("/?lang=en")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert '<html lang="en">' in html
        assert "School Library Management Software" in html
        with client.session_transaction() as sess:
            assert sess.get("lang") == "en"

        # Request with ?lang=de
        res = client.get("/?lang=de")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert '<html lang="de">' in html
        assert "Schulbibliothek-Verwaltungssoftware" in html
        with client.session_transaction() as sess:
            assert sess.get("lang") == "de"


def test_hreflang_and_canonical_tags():
    """Verify that hreflang alternate tags and canonical link are correctly rendered."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        res = client.get("/aide?lang=en")
        assert res.status_code == 200
        html = res.data.decode("utf-8")

        # Check hreflang tags
        assert '<link rel="alternate" hreflang="fr"' in html
        assert '<link rel="alternate" hreflang="en"' in html
        assert '<link rel="alternate" hreflang="de"' in html
        assert '<link rel="alternate" hreflang="x-default"' in html

        # Check canonical tag
        assert '<link rel="canonical"' in html
        assert "lang=en" in html


def test_title_and_meta_tags_localized():
    """Verify that <title> and <meta name='description'> adapt to language."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # French default
        res_fr = client.get("/aide?lang=fr")
        html_fr = res_fr.data.decode("utf-8")
        assert (
            "<title>Centre d&#39;aide | Livres en Classe</title>" in html_fr
            or "<title>Centre d'aide | Livres en Classe</title>" in html_fr
        )

        # English
        res_en = client.get("/aide?lang=en")
        html_en = res_en.data.decode("utf-8")
        assert "<title>Help Center | Livres en Classe</title>" in html_en

        # German
        res_de = client.get("/aide?lang=de")
        html_de = res_de.data.decode("utf-8")
        assert "<title>Hilfecenter | Livres en Classe</title>" in html_de


def test_sitemap_multilingual_xml():
    """Verify that sitemap.xml returns XML and contains xhtml:link alternates."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        res = client.get("/sitemap.xml")
        assert res.status_code == 200
        assert "application/xml" in res.content_type
        xml = res.data.decode("utf-8")
        assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in xml
        assert '<xhtml:link rel="alternate" hreflang="fr"' in xml
        assert '<xhtml:link rel="alternate" hreflang="en"' in xml
        assert '<xhtml:link rel="alternate" hreflang="de"' in xml
        assert '<xhtml:link rel="alternate" hreflang="x-default"' in xml
        assert "https://livresenclasse.com/aide" in xml


def test_llms_txt_mentions_languages():
    """Verify that llms.txt returns 200 text/plain and documents multilingual support."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        res = client.get("/llms.txt")
        assert res.status_code == 200
        assert "text/plain" in res.content_type
        text = res.data.decode("utf-8")
        assert "Français (fr)" in text
        assert "English (en)" in text
        assert "Deutsch (de)" in text


def test_navbar_language_dropdown_and_highlight():
    """Verify that navbar displays compact language dropdown with active language highlighted."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Default French
        res_fr = client.get("/")
        html_fr = res_fr.data.decode("utf-8")
        assert 'id="langDropdownBtn"' in html_fr
        assert '<span class="lang-btn-code">FR</span>' in html_fr
        assert 'class="lang-dropdown-item is-active"' in html_fr

        # English
        res_en = client.get("/?lang=en")
        html_en = res_en.data.decode("utf-8")
        assert '<span class="lang-btn-code">EN</span>' in html_en
        assert 'class="lang-dropdown-item is-active"' in html_en
        assert "English" in html_en

        # German
        res_de = client.get("/?lang=de")
        html_de = res_de.data.decode("utf-8")
        assert '<span class="lang-btn-code">DE</span>' in html_de
        assert 'class="lang-dropdown-item is-active"' in html_de
        assert "Deutsch" in html_de


def test_dashboard_heatmap_localization():
    """Verify that heatmap day names, months, and tooltips are localized on /dashboard."""
    from datetime import datetime, timezone

    from flask import render_template
    from flask_babel import refresh

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    test_date = datetime(2025, 9, 1, 12, 0, tzinfo=timezone.utc)
    months = [(test_date, 4)]
    loans = [(test_date, 2, 1)] * 371

    expectations = {
        "fr": {
            "days": ["<td>Lun</td>", "<td>Mer</td>", "<td>Ven</td>", "<td>Dim</td>"],
            "month": "Sept.",
            "tooltip": "Le 1 sept. 2025<br>2 prêts, 1 retours",
        },
        "en": {
            "days": ["<td>Mon</td>", "<td>Wed</td>", "<td>Fri</td>", "<td>Sun</td>"],
            "month": "Sep",
            "tooltip": "On Sep 1, 2025<br>2 loans, 1 returns",
        },
        "de": {
            "days": ["<td>Mo</td>", "<td>Mi</td>", "<td>Fr</td>", "<td>So</td>"],
            "month": "Sept.",
            "tooltip": "Am 01.09.2025<br>2 Ausleihen, 1 Rückgaben",
        },
    }

    with app.test_request_context():
        for lang, expected in expectations.items():
            from flask import session

            session["lang"] = lang
            refresh()

            rendered = render_template(
                "user/dashboard.html",
                n_books=0,
                n_students=0,
                books=[],
                students=[],
                books_loaned=[],
                months=months,
                loans=loans,
            )

            for day_html in expected["days"]:
                assert day_html in rendered, f"Expected {day_html} in {lang}"
            assert f">{expected['month']}</td>" in rendered, (
                f"Expected >{expected['month']}</td> in {lang}"
            )
            assert expected["tooltip"] in rendered, (
                f"Expected tooltip '{expected['tooltip']}' in {lang}"
            )


def test_ressources_page_translations():
    """Verify that /ressources and resource editors are properly translated in fr, en, and de."""
    from project import create_app

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
            "WTF_CSRF_ENABLED": False,
        }
    )

    client = app.test_client()

    checks = {
        "fr": [
            "Outils et Ressources pour la Classe",
            "Diplômes de Lecture",
            "Toutes les ressources",
            "Personnaliser et imprimer",
            "Eduscol — Lire et écrire au cycle 2",
        ],
        "en": [
            "Classroom Tools and Resources",
            "Reading Diplomas",
            "All resources",
            "Customize and print",
            "Eduscol — Reading and Writing in Primary Education",
        ],
        "de": [
            "Werkzeuge und Ressourcen für das Klassenzimmer",
            "Lese-Diplome",
            "Alle Ressourcen",
            "Anpassen und drucken",
            "Eduscol — Lesen und Schreiben in der Grundschule",
        ],
    }

    for lang, expected_strings in checks.items():
        client.get(f"/set-lang/{lang}", follow_redirects=True)
        response = client.get("/ressources")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        for expected in expected_strings:
            assert expected in html, (
                f"Missing '{expected}' in /ressources for language {lang}"
            )
