from datetime import UTC
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
    from datetime import datetime

    from flask import render_template_string

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    dt = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

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
    """Verify that dedicated language URLs and ?lang= query parameter set locale."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Request with dedicated URL /en/
        res = client.get("/en/")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert 'lang="en"' in html
        assert "School Library Management Software" in html
        with client.session_transaction() as sess:
            assert sess.get("lang") == "en"

        # Request with dedicated URL /de/
        res = client.get("/de/")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert 'lang="de"' in html
        assert "Schulbibliothek-Verwaltungssoftware" in html
        with client.session_transaction() as sess:
            assert sess.get("lang") == "de"

        # Request with legacy query parameter ?lang=en (supported via alias in test mode)
        res_param = client.get("/?lang=en")
        assert res_param.status_code == 200


def test_hreflang_and_canonical_tags():
    """Verify that hreflang alternate tags, canonical link, and og:locale are correctly rendered."""
    app = create_app(
        {
            "TESTING": True,
            "SERVER_NAME": "livresenclasse.com",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Check English page /en/aide
        res = client.get("/en/aide")
        assert res.status_code == 200
        html = res.data.decode("utf-8")

        # Canonical points to self
        assert (
            '<link rel="canonical" href="http://livresenclasse.com/en/aide"' in html
            or '<link rel="canonical" href="https://livresenclasse.com/en/aide"' in html
        )

        # Hreflang alternate tags for all 3 languages + x-default
        assert (
            'hreflang="fr" href="http://livresenclasse.com/fr/aide"' in html
            or 'hreflang="fr" href="https://livresenclasse.com/fr/aide"' in html
        )
        assert (
            'hreflang="en" href="http://livresenclasse.com/en/aide"' in html
            or 'hreflang="en" href="https://livresenclasse.com/en/aide"' in html
        )
        assert (
            'hreflang="de" href="http://livresenclasse.com/de/aide"' in html
            or 'hreflang="de" href="https://livresenclasse.com/de/aide"' in html
        )
        assert (
            'hreflang="x-default" href="http://livresenclasse.com/fr/aide"' in html
            or 'hreflang="x-default" href="https://livresenclasse.com/fr/aide"' in html
        )

        # OpenGraph og:locale tags
        assert '<meta property="og:locale" content="en_US"' in html
        assert '<meta property="og:locale:alternate" content="fr_FR"' in html
        assert '<meta property="og:locale:alternate" content="de_DE"' in html


def test_hreflang_reciprocity():
    """Verify strict hreflang reciprocity across all supported languages."""
    app = create_app(
        {
            "TESTING": True,
            "SERVER_NAME": "livresenclasse.com",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    pages = ["/tarifs", "/aide", "/apropos"]
    langs = ["fr", "en", "de"]

    with app.test_client() as client:
        for page in pages:
            for source_lang in langs:
                res = client.get(f"/{source_lang}{page}")
                assert res.status_code == 200, f"Failed for {source_lang}{page}"
                html = res.data.decode("utf-8")

                # Verify each language page lists all targets
                for target_lang in langs:
                    expected_target = f"/{target_lang}{page}"
                    assert f'hreflang="{target_lang}"' in html, (
                        f"Missing hreflang={target_lang} on {source_lang}{page}"
                    )
                    assert expected_target in html, (
                        f"Missing {expected_target} in hreflang on {source_lang}{page}"
                    )
                # Verify x-default
                assert 'hreflang="x-default"' in html
                assert f"/fr{page}" in html


def test_language_redirection_and_vary_header():
    """Verify 302 temporary redirects for content negotiation, 301 for ?lang=, and Vary header."""
    app = create_app(
        {
            "TESTING": True,
            "TEST_REDIRECTS": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Default / redirects 302 to /fr/ with Vary: Accept-Language, Cookie
        res_root = client.get("/")
        assert res_root.status_code == 302
        assert res_root.headers.get("Location") == "/fr/"
        assert "Accept-Language" in res_root.headers.get("Vary", "")
        assert "Cookie" in res_root.headers.get("Vary", "")

        # Unprefixed /tarifs redirects 302 to /fr/tarifs with Vary
        res_tarifs = client.get("/tarifs")
        assert res_tarifs.status_code == 302
        assert res_tarifs.headers.get("Location") == "/fr/tarifs"
        assert "Accept-Language" in res_tarifs.headers.get("Vary", "")

        # Accept-Language: en redirects 302 to /en/
        res_en = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"})
        assert res_en.status_code == 302
        assert res_en.headers.get("Location") == "/en/"

        # Accept-Language: de redirects 302 to /de/
        res_de = client.get("/", headers={"Accept-Language": "de-DE,de;q=0.9"})
        assert res_de.status_code == 302
        assert res_de.headers.get("Location") == "/de/"

        # Explicit ?lang=en triggers 301 permanent redirect
        res_301 = client.get("/tarifs?lang=en")
        assert res_301.status_code == 301
        assert res_301.headers.get("Location") == "/en/tarifs"

        # Unsupported language returns 404
        res_404 = client.get("/es/tarifs")
        assert res_404.status_code == 404


def test_title_and_meta_tags_localized():
    """Verify that <title> and <meta name='description'> adapt to language on dedicated URLs."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # French /fr/aide
        res_fr = client.get("/fr/aide")
        html_fr = res_fr.data.decode("utf-8")
        assert (
            "<title>Centre d&#39;aide | Livres en Classe</title>" in html_fr
            or "<title>Centre d'aide | Livres en Classe</title>" in html_fr
        )

        # English /en/aide
        res_en = client.get("/en/aide")
        html_en = res_en.data.decode("utf-8")
        assert "<title>Help Center | Livres en Classe</title>" in html_en

        # German /de/aide
        res_de = client.get("/de/aide")
        html_de = res_de.data.decode("utf-8")
        assert "<title>Hilfecenter | Livres en Classe</title>" in html_de


def test_sitemap_multilingual_xml():
    """Verify that sitemap.xml returns XML and contains dedicated URLs and xhtml:link alternates."""
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
        assert "https://livresenclasse.com/fr/aide" in xml
        assert "https://livresenclasse.com/en/aide" in xml
        assert "https://livresenclasse.com/de/aide" in xml
        assert "https://livresenclasse.com/fr/tarifs" in xml
        assert "https://livresenclasse.com/en/tarifs" in xml
        assert "https://livresenclasse.com/de/tarifs" in xml


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
        assert "https://livresenclasse.com/fr/" in text
        assert "https://livresenclasse.com/en/" in text
        assert "https://livresenclasse.com/de/" in text


def test_navbar_language_dropdown_and_highlight():
    """Verify that navbar displays language links pointing to dedicated URLs with active language highlighted."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.test_client() as client:
        # Default French /fr/
        res_fr = client.get("/fr/")
        html_fr = res_fr.data.decode("utf-8")
        assert 'id="langDropdownBtn"' in html_fr
        assert '<span class="lang-btn-code">FR</span>' in html_fr
        assert 'class="lang-dropdown-item is-active"' in html_fr
        assert 'href="/en/"' in html_fr
        assert 'href="/de/"' in html_fr

        # English /en/tarifs
        res_en = client.get("/en/tarifs")
        html_en = res_en.data.decode("utf-8")
        assert '<span class="lang-btn-code">EN</span>' in html_en
        assert 'class="lang-dropdown-item is-active"' in html_en
        assert "English" in html_en
        # Verify language switcher links point directly to /fr/tarifs and /de/tarifs
        assert 'href="/fr/tarifs"' in html_en
        assert 'href="/de/tarifs"' in html_en

        # German /de/aide
        res_de = client.get("/de/aide")
        html_de = res_de.data.decode("utf-8")
        assert '<span class="lang-btn-code">DE</span>' in html_de
        assert 'class="lang-dropdown-item is-active"' in html_de
        assert "Deutsch" in html_de
        assert 'href="/fr/aide"' in html_de
        assert 'href="/en/aide"' in html_de


def test_dashboard_heatmap_localization():
    """Verify that heatmap day names, months, and tooltips are localized on /dashboard."""
    from datetime import datetime

    from flask import render_template
    from flask_babel import refresh

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    test_date = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
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


def test_scan_limit_reached_translations_and_dynamic_config():
    """Verify that scan limit messages are translated into EN and DE and dynamically reflect MAX_FREE_SCANS."""
    from project import db
    from project.config_plans import MAX_FREE_SCANS
    from project.models import User

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )

    with app.app_context():
        db.create_all()
        user = User(
            id=999,
            email="limit_scan@test.com",
            plan="free",
            free_scans_used=MAX_FREE_SCANS,
            trial_ends_at=None,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "999"

    # 1. Test FR error message
    res_fr = client.get("/fr/livre/9781234567890/exist")
    assert res_fr.status_code == 403
    data_fr = res_fr.get_json()
    assert data_fr["error"] == "scan_limit_reached"
    assert f"quota de {MAX_FREE_SCANS} scans gratuits" in data_fr["message"]
    assert "dimanche à minuit" in data_fr["message"]

    # 2. Test EN error message
    res_en = client.get("/en/livre/9781234567890/exist")
    assert res_en.status_code == 403
    data_en = res_en.get_json()
    assert data_en["error"] == "scan_limit_reached"
    assert f"weekly quota of {MAX_FREE_SCANS} free scans" in data_en["message"]
    assert "reset on Sunday at midnight" in data_en["message"]

    # 3. Test DE error message
    res_de = client.get("/de/livre/9781234567890/exist")
    assert res_de.status_code == 403
    data_de = res_de.get_json()
    assert data_de["error"] == "scan_limit_reached"
    assert (
        f"wöchentliches Kontingent von {MAX_FREE_SCANS} kostenlosen Scans"
        in data_de["message"]
    )
    assert "Sonntag um Mitternacht" in data_de["message"]

    # 4. Test template /en/livre/scann renders modal with dynamic number and translated title
    res_modal = client.get("/en/livre/scann")
    assert res_modal.status_code == 200
    html_modal = res_modal.get_data(as_text=True)
    assert "Scan limit reached" in html_modal
    assert (
        f"You have used your {MAX_FREE_SCANS} free scans for this week!" in html_modal
    )
