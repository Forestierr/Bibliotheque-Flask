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
        assert "Free Classroom Library Management Software" in html
        with client.session_transaction() as sess:
            assert sess.get("lang") == "en"

        # Request with dedicated URL /de/
        res = client.get("/de/")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert 'lang="de"' in html
        assert "Kostenlose Software zur Verwaltung von Klassenbibliotheken" in html
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
        # Verify subscription and freemium documentation
        assert "Modèle Freemium & Abonnements" in text
        assert "30 élèves" in text
        assert "100 livres" in text
        assert "30 scans" in text
        assert "3.00 CHF" in text
        assert "30.00 CHF" in text
        assert "https://livresenclasse.com/tarifs" in text


def test_bing_webmaster_and_indexnow_verification():
    """Verify Bing Webmaster / IndexNow verification key file at root and meta tag."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
            "TEST_REDIRECTS": True,
        }
    )

    with app.test_client() as client:
        # 1. Root verification files (support multi-clés)
        res_old = client.get("/1452be41003e41c59435f150f75f55d8.txt")
        assert res_old.status_code == 200
        assert "text/plain" in res_old.content_type
        assert (
            res_old.data.decode("utf-8").strip() == "1452be41003e41c59435f150f75f55d8"
        )

        res_new = client.get("/744d589148a54a93bfd6c066fce258a6.txt")
        assert res_new.status_code == 200
        assert "text/plain" in res_new.content_type
        assert (
            res_new.data.decode("utf-8").strip() == "744d589148a54a93bfd6c066fce258a6"
        )

        # 2. Non-existent txt key should return 404
        res_404 = client.get("/00000000000000000000000000000000.txt")
        assert res_404.status_code == 404

        # 3. Bing verification meta tag in homepage
        res_home = client.get("/fr/")
        assert res_home.status_code == 200
        html = res_home.data.decode("utf-8")
        assert (
            '<meta name="msvalidate.01" content="744d589148a54a93bfd6c066fce258a6"/>'
            in html
        )


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


def test_mentions_legales_translations():
    """Test that mentions-legales renders in FR, EN, and DE with translated legal terms."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-translations",
        }
    )
    client = app.test_client()

    # French
    res_fr = client.get("/fr/mentions-legales")
    assert res_fr.status_code == 200
    html_fr = res_fr.get_data(as_text=True)
    assert (
        "Mentions Légales &amp; Conditions Générales" in html_fr
        or "Mentions Légales & Conditions Générales" in html_fr
    )
    assert (
        "1. CONDITIONS GÉNÉRALES D&#39;UTILISATION (CGU)" in html_fr
        or "1. CONDITIONS GÉNÉRALES D'UTILISATION (CGU)" in html_fr
    )
    assert "Éditeur du service :" in html_fr

    # English
    res_en = client.get("/en/mentions-legales")
    assert res_en.status_code == 200
    html_en = res_en.get_data(as_text=True)
    assert (
        "Legal Notice &amp; General Terms" in html_en
        or "Legal Notice & General Terms" in html_en
    )
    assert "1. GENERAL TERMS OF USE" in html_en
    assert "Service Publisher:" in html_en
    assert "service availability and account termination" in html_en.lower()

    # German
    res_de = client.get("/de/mentions-legales")
    assert res_de.status_code == 200
    html_de = res_de.get_data(as_text=True)
    assert (
        "Impressum &amp; Allgemeine Geschäftsbedingungen" in html_de
        or "Impressum & Allgemeine Geschäftsbedingungen" in html_de
    )
    assert "1. ALLGEMEINE NUTZUNGSBEDINGUNGEN (AGB)" in html_de
    assert "Herausgeber des Dienstes:" in html_de


def test_all_translations_complete_and_no_fuzzy():
    """Verify 0 empty, 0 fuzzy, valid placeholders, and .mo/.po/source sync."""
    import importlib.util

    script_path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts"
        / "check_translations.py"
    )
    spec = importlib.util.spec_from_file_location("check_translations", script_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    errors = mod.check_translations(skip_extract=False)
    assert errors == [], "Problèmes i18n détectés:\n" + "\n".join(errors[:20])


def test_seo_sitemap_and_matomo_htmx_guards():
    """Verify sitemap excludes noindex routes and Matomo is isolated from HTMX search loops."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-seo",
        }
    )
    client = app.test_client()

    # 1. Sitemap must not list noindex auth routes
    res_sm = client.get("/sitemap.xml")
    assert res_sm.status_code == 200
    sm = res_sm.get_data(as_text=True)
    assert "/fr/login" not in sm
    assert "/fr/signup" not in sm
    assert "/fr/tarifs" in sm

    # 2. Matomo in <head>, production hostname guarded, and uses htmx:pushedIntoHistory
    res_home = client.get("/fr/")
    assert res_home.status_code == 200
    html = res_home.get_data(as_text=True)
    assert "window.location.hostname === 'livresenclasse.com'" in html
    assert "window.__matomoInitialized" in html
    assert "htmx:pushedIntoHistory" in html
    assert "htmx:afterOnLoad" not in html

    # 3. Tarifs uses rel="nofollow" on checkout / invoice routes
    res_tarifs = client.get("/fr/tarifs")
    assert res_tarifs.status_code == 200
    html_tarifs = res_tarifs.get_data(as_text=True)
    assert 'rel="nofollow"' in html_tarifs


def test_localized_seo_route_aliases_and_llms():
    """Verify EN/DE route aliases, localized app_install/blog titles, and multilingual llms.txt."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-seo-aliases",
        }
    )
    client = app.test_client()

    aliases = [
        ("/en/pricing", "/en/tarifs"),
        ("/de/preise", "/de/tarifs"),
        ("/en/resources", "/en/ressources"),
        ("/de/ressourcen", "/de/ressources"),
        ("/en/teachers", "/en/enseignants"),
        ("/de/lehrkraefte", "/de/enseignants"),
        ("/en/help", "/en/aide"),
        ("/de/hilfe", "/de/aide"),
        ("/en/about", "/en/apropos"),
        ("/de/ueber-uns", "/de/apropos"),
        ("/en/legal", "/en/mentions-legales"),
        ("/de/impressum", "/de/mentions-legales"),
    ]
    for alias_url, expected_canonical in aliases:
        res = client.get(alias_url)
        assert res.status_code == 200, f"Expected 200 on {alias_url}"
        html = res.get_data(as_text=True)
        assert expected_canonical in html

    # Localized /install pages
    res_inst_en = client.get("/en/install")
    assert res_inst_en.status_code == 200
    assert "Install the App" in res_inst_en.get_data(as_text=True)

    res_inst_de = client.get("/de/install")
    assert res_inst_de.status_code == 200
    assert "App installieren" in res_inst_de.get_data(as_text=True)

    # Blog EN free of French (CP) jargon in title/body
    res_blog_en = client.get("/en/blog/meilleurs-livres-cp")
    assert res_blog_en.status_code == 200
    blog_en_html = res_blog_en.get_data(as_text=True)
    assert "1st Grade (CP)" not in blog_en_html
    assert "Best Books for 1st Grade Readers" in blog_en_html

    # Multilingual llms.txt
    res_llms = client.get("/llms.txt")
    assert res_llms.status_code == 200
    llms = res_llms.get_data(as_text=True)
    assert "English Summary" in llms
    assert "Deutsche Übersicht" in llms
    assert "/en/pricing" in llms
    assert "/de/preise" in llms


def test_seo_tickets_t4_to_t8():
    """Verify SEO fixes T-4 (OG/Twitter parity), T-5 (HTTPS og:url + og:locale:alternate),
    T-6 (direct canonical resource links), T-7 (sitemap canonicals & real lastmod), and T-8 (EN/DE diploma dates).
    """
    import re
    import xml.etree.ElementTree as ET

    app = create_app(
        {
            "TESTING": True,
            "TEST_REDIRECTS": True,
            "SERVER_NAME": "livresenclasse.com",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-seo-tickets",
        }
    )
    client = app.test_client()

    # T-4 & T-5: OG/Twitter meta parity, HTTPS og:url == canonical, 2 og:locale:alternate
    sample_paths = [
        "/fr/",
        "/en/",
        "/de/",
        "/fr/blog/meilleurs-livres-cp",
        "/en/blog/meilleurs-livres-cp",
        "/de/blog/meilleurs-livres-cp",
        "/fr/ressources/diplome-de-lecture-a-imprimer",
        "/en/ressources/diplome-de-lecture-a-imprimer",
        "/de/ressources/diplome-de-lecture-a-imprimer",
        "/fr/tarifs",
        "/en/aide",
    ]
    for path in sample_paths:
        res = client.get(path)
        assert res.status_code == 200, path
        html = res.get_data(as_text=True)

        title = re.search(r"<title>(.*?)</title>", html, re.DOTALL).group(1)
        og_title = re.search(
            r'<meta property="og:title" content="(.*?)"', html, re.DOTALL
        ).group(1)
        tw_title = re.search(
            r'<meta name="twitter:title" content="(.*?)"', html, re.DOTALL
        ).group(1)
        assert title == og_title == tw_title, f"Title mismatch on {path}"

        desc = re.search(
            r'<meta name="description" content="(.*?)"', html, re.DOTALL
        ).group(1)
        og_desc = re.search(
            r'<meta property="og:description" content="(.*?)"', html, re.DOTALL
        ).group(1)
        tw_desc = re.search(
            r'<meta name="twitter:description" content="(.*?)"', html, re.DOTALL
        ).group(1)
        assert desc == og_desc == tw_desc, f"Description mismatch on {path}"

        canonical = re.search(r'<link rel="canonical" href="(.*?)"', html).group(1)
        og_url = re.search(r'<meta property="og:url" content="(.*?)"', html).group(1)
        assert canonical == og_url and og_url.startswith("https://"), (
            path,
            canonical,
            og_url,
        )

        alt_locales = re.findall(
            r'<meta property="og:locale:alternate" content="(.*?)"', html
        )
        assert len(alt_locales) == 2, (path, alt_locales)

    fr_blog = client.get("/fr/blog/meilleurs-livres-cp").get_data(as_text=True)
    assert "Les Meilleurs Livres pour le CP" in re.search(
        r'<meta property="og:title" content="(.*?)"', fr_blog, re.DOTALL
    ).group(1)

    # T-6: Homepage resource links point directly to final canonical URLs
    for lang in ("fr", "en", "de"):
        home_html = client.get(f"/{lang}/").get_data(as_text=True)
        assert f"/{lang}/ressources/diplome-de-lecture-a-imprimer" in home_html
        assert f"/{lang}/ressources/marque-pages-a-imprimer" in home_html
        assert f"/{lang}/ressources/charte-coin-lecture-a-imprimer" in home_html
        assert f'href="/{lang}/ressources/diplome"' not in home_html
        assert f'href="/{lang}/ressources/marque-pages"' not in home_html
        assert f'href="/{lang}/ressources/charte"' not in home_html
        assert 'href="/sitemap.xml"' in home_html

    # T-7: Sitemap lists canonicals (mentions-legales, not mentions_legales) & varied lastmod
    sm_res = client.get("/sitemap.xml")
    assert sm_res.status_code == 200
    sm_xml = sm_res.get_data(as_text=True)
    assert "mentions_legales" not in sm_xml
    assert "/fr/mentions-legales" in sm_xml
    root = ET.fromstring(sm_xml)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    lastmods = {el.text for el in root.findall(".//ns:lastmod", ns)}
    assert len(lastmods) > 2, f"Expected non-uniform lastmod dates, got {lastmods}"

    for lang in ("fr", "en", "de"):
        r_sm = client.get(f"/{lang}/sitemap")
        assert r_sm.status_code == 301
        assert r_sm.headers["Location"].endswith("/sitemap.xml")

    # T-8: Diploma preview & JS date format localized for EN and DE
    diplome_en = client.get("/en/ressources/diplome-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Le 06/09/2026" not in diplome_en
    assert "09/06/2026" in diplome_en
    assert "toLocaleDateString('en-US'" in diplome_en

    diplome_de = client.get("/de/ressources/diplome-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Le 06/09/2026" not in diplome_de
    assert "06.09.2026" in diplome_de
    assert "toLocaleDateString('de-DE'" in diplome_de


def test_seo_t10_t11_keywords():
    """Verify T-10 (real German 1st-grade books with authors, publishers & ISBNs)
    and T-11 native page-1 SEO keywords / calque & quota cleanup across DE and EN.
    """
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-for-t10-t11",
        }
    )
    client = app.test_client()

    # T-10: DE 1st grade article has real verified books, authors, publishers, ISBNs
    de_books = client.get("/de/blog/meilleurs-livres-cp").get_data(as_text=True)
    for placeholder in ("Hurra, ich bin ein Schulkind!", "Der Wackelzahn ist los!"):
        assert placeholder not in de_books
    for expected in (
        "978-3-7855-6511-7",
        "978-3-473-46443-2",
        "978-3-570-15420-5",
        "978-3-948690-23-6",
        "Franziska Gehm",
        "Manfred Mai",
        "Ingo Siegner",
        "Erhard Dietl",
        "Patrick Wirbeleit",
        "Leseurkunde",
        "Lesepass",
        "Ausleihliste",
    ):
        assert expected in de_books

    # T-11 DE native page-1 keywords
    de_dip = client.get("/de/ressources/diplome-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Leseurkunde zum Ausdrucken" in de_dip
    assert "LESEURKUNDE" in de_dip

    de_pass = client.get("/de/ressources/passeport-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Lesepass zum Ausdrucken" in de_pass
    assert "Leselogbuch" in de_pass

    de_checkout = client.get("/de/blog/suivi-emprunts-livres-eleves").get_data(
        as_text=True
    )
    assert "Ausleihliste Klassenbibliothek" in de_checkout
    assert "Klassenbücherei" in de_checkout

    de_org = client.get("/de/blog/comment-classer-livres").get_data(as_text=True)
    assert "Klassenbibliothek &amp; Klassenbücherei ordnen" in de_org

    de_bcd = client.get("/de/blog/logiciel-bcd-ecole").get_data(as_text=True)
    assert "500 Bücher und 40 Schüler" not in de_bcd
    assert "100 Bücher und 30 Schüler" in de_bcd

    # T-11 EN native page-1 keywords & cleanup of French acronyms/calques
    en_dip = client.get("/en/ressources/diplome-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Printable Reading Certificate" in en_dip
    assert "READING CERTIFICATE" in en_dip

    en_pass = client.get("/en/ressources/passeport-de-lecture-a-imprimer").get_data(
        as_text=True
    )
    assert "Printable Reading Log" in en_pass

    en_checkout = client.get("/en/blog/suivi-emprunts-livres-eleves").get_data(
        as_text=True
    )
    assert "Classroom Library Checkout System" in en_checkout

    en_org = client.get("/en/blog/comment-classer-livres").get_data(as_text=True)
    assert "Classroom Library Organization" in en_org
    assert "Book Bin Labels" in en_org

    en_bcd = client.get("/en/blog/logiciel-bcd-ecole").get_data(as_text=True)
    assert "BCDI" not in en_bcd
    assert "SIGB" not in en_bcd
    assert "500 books and 40 students" not in en_bcd
    assert "100 books and 30 students" in en_bcd

    en_mot = client.get("/en/blog/donner-envie-lire").get_data(as_text=True)
    assert "reading rally" not in en_mot
    assert "reading quarter hour" not in en_mot
