from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from project import create_app, db
from project.models import Book, Loan, Student, User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-ressources",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_ressources_index_anonymous(client):
    """Vérifie que la page index des ressources est accessible publiquement."""
    response = client.get("/ressources")
    assert response.status_code == 200
    assert "Outils et Ressources pour la Classe" in response.get_data(as_text=True)
    assert "Diplômes de Lecture" in response.get_data(as_text=True)


def test_ressources_301_redirects(client):
    """Vérifie la redirection 301 stricte des anciennes URLs vers les nouvelles URLs canoniques."""
    redirects = [
        ("/ressources/diplome", "/fr/ressources/diplome-de-lecture-a-imprimer"),
        ("/ressources/marque-pages", "/fr/ressources/marque-pages-a-imprimer"),
        ("/ressources/fiches-avis", "/fr/ressources/fiche-de-lecture-a-imprimer"),
        ("/ressources/charte", "/fr/ressources/charte-coin-lecture-a-imprimer"),
        ("/ressources/bingo", "/fr/ressources/defi-lecture-bingo-a-imprimer"),
        ("/ressources/passeport", "/fr/ressources/passeport-de-lecture-a-imprimer"),
    ]
    for old_url, expected_dest in redirects:
        res = client.get(old_url)
        assert res.status_code == 301, f"{old_url} doit renvoyer 301"
        assert (
            res.headers["Location"].endswith(expected_dest)
            or expected_dest in res.headers["Location"]
        )


def test_diplome_anonymous(client):
    """Vérifie que l'éditeur de diplôme s'ouvre avec les valeurs par défaut pour un visiteur sur l'URL canonique."""
    response = client.get("/ressources/diplome-de-lecture-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DIPLÔME DE LECTURE" in html
    assert "Thomas Dubois" in html


def test_diplome_authenticated_with_student(client, app):
    """Vérifie que l'éditeur pré-remplit les informations d'un élève connecté."""
    with app.app_context():
        user = User(id=1, email="prof@ecole.fr", name="M. Dupont", password="xyz")
        db.session.add(user)
        student = Student(id=10, name="Martin", firstname="Léa", user_id=1)
        db.session.add(student)
        book = Book(id=1, title="Le Petit Prince", user_id=1)
        db.session.add(book)
        loan = Loan(
            id=1,
            student_id=10,
            book_id=1,
            date_loan=date(2026, 1, 1),
            date_return=date(2026, 1, 10),
        )
        db.session.add(loan)
        db.session.commit()

    with patch("project.ressource.current_user") as mock_user:
        mock_user.is_authenticated = True
        mock_user.id = 1
        mock_user.name = "M. Dupont"

        response = client.get("/ressources/diplome-de-lecture-a-imprimer?student_id=10")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Léa Martin" in html
        assert "1 livres lus" in html or "1" in html


def test_marque_pages_page(client):
    """Vérifie l'accessibilité du générateur de marque-pages sur l'URL canonique."""
    response = client.get("/ressources/marque-pages-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "FICHE D'EMPRUNT" in html
    assert "AVIS DE LECTURE" in html


def test_charte_page(client):
    """Vérifie l'accessibilité du générateur de la charte du coin lecture."""
    response = client.get("/ressources/charte-coin-lecture-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "LA CHARTE DU COIN LECTURE" in html


def test_bingo_page(client):
    """Vérifie l'accessibilité du générateur de bingo lecture."""
    response = client.get("/ressources/defi-lecture-bingo-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DÉFI LECTURE" in html


def test_etiquettes_page(client):
    """Vérifie l'accessibilité du générateur d'étiquettes de bacs (premium requis)."""
    resp_anon = client.get("/ressources/etiquettes")
    assert resp_anon.status_code == 302

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    mock_user.is_premium = True
    with patch("flask_login.utils._get_user", return_value=mock_user):
        response = client.get("/ressources/etiquettes")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "ROMANS" in html
        assert "BANDES DESSINÉES" in html


def test_fiches_avis_page(client):
    """Vérifie l'accessibilité du générateur de fiches coup de cœur sur l'URL canonique."""
    response = client.get("/ressources/fiche-de-lecture-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "COUP DE CŒUR" in html


def test_codes_barres_page(client):
    """Vérifie l'accessibilité du générateur de codes-barres (premium requis)."""
    resp_anon = client.get("/ressources/codes-barres")
    assert resp_anon.status_code == 302

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    mock_user.is_premium = True
    with patch("flask_login.utils._get_user", return_value=mock_user):
        response = client.get("/ressources/codes-barres")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "JsBarcode" in html or "Codes-Barres" in html


def test_passeport_page(client):
    """Vérifie l'accessibilité du passeport de lecture sur l'URL canonique."""
    response = client.get("/ressources/passeport-de-lecture-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "PASSEPORT DE LECTEUR" in html
    assert "PARCOURS DES GENRES" in html


def test_ressource_unknown_slug_404(client):
    """Vérifie qu'un slug inexistant renvoie 404."""
    response = client.get("/ressources/inconnu-inexistant-xyz")
    assert response.status_code == 404


def test_a4_page_orientations(client):
    """Vérifie que les orientations @page et les classes A4 correspondent (landscape vs portrait)."""
    # Paysage
    for route in [
        "/ressources/diplome-de-lecture-a-imprimer",
        "/ressources/passeport-de-lecture-a-imprimer",
    ]:
        resp = client.get(route)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "size: A4 landscape" in html
        assert "a4-sheet landscape" in html

    # Portrait (publiques)
    for route in [
        "/ressources/charte-coin-lecture-a-imprimer",
        "/ressources/defi-lecture-bingo-a-imprimer",
        "/ressources/marque-pages-a-imprimer",
        "/ressources/fiche-de-lecture-a-imprimer",
    ]:
        resp = client.get(route)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "size: A4 portrait" in html
        assert "a4-sheet portrait" in html

    # Ressources protégées (premium)
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    mock_user.is_premium = True
    with patch("flask_login.utils._get_user", return_value=mock_user):
        resp = client.get("/ressources/etiquettes")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "size: A4 portrait" in html
        assert "a4-sheet portrait" in html

        resp_cb = client.get("/ressources/codes-barres")
        assert resp_cb.status_code == 200
        html_cb = resp_cb.get_data(as_text=True)
        assert "multi-page" in html_cb


def test_diplome_authenticated_students_dropdown_and_batch(client, app):
    """Vérifie la présence du sélecteur d'élèves avec décompte des lectures et le mode toute la classe."""
    with app.app_context():
        user = User(id=2, email="instit@ecole.fr", name="Mme Bernard", password="pwd")
        db.session.add(user)
        s1 = Student(id=21, name="Dupont", firstname="Lucas", user_id=2)
        s2 = Student(id=22, name="Moreau", firstname="Chloé", user_id=2)
        db.session.add_all([s1, s2])
        b1 = Book(id=10, title="Livre 1", user_id=2)
        b2 = Book(id=11, title="Livre 2", user_id=2)
        db.session.add_all([b1, b2])
        l1 = Loan(
            id=101,
            student_id=21,
            book_id=10,
            date_loan=date(2026, 1, 1),
            date_return=date(2026, 1, 15),
        )
        l2 = Loan(
            id=102,
            student_id=21,
            book_id=11,
            date_loan=date(2026, 2, 1),
            date_return=date(2026, 2, 10),
        )
        db.session.add_all([l1, l2])
        db.session.commit()

    with patch("project.ressource.current_user") as mock_user:
        mock_user.is_authenticated = True
        mock_user.id = 2
        mock_user.name = "Mme Bernard"

        response = client.get("/ressources/diplome-de-lecture-a-imprimer")
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        # Vérifie le sélecteur et l'option de saisie libre
        assert "studentSelector" in html
        assert "Saisie libre / Autre élève" in html
        assert "Lucas Dupont" in html
        assert "Chloé Moreau" in html
        assert "2 livres lus" in html
        assert "0 livre lu" in html

        # Vérifie la présence des conteneurs du mode toute la classe
        assert "allDiplomesView" in html
        assert "diplome-multi-container" in html


def test_diplome_unauthenticated_login_prompt(client):
    """Vérifie qu'un visiteur non connecté voit l'invitation à se connecter pour lier ses élèves."""
    response = client.get("/ressources/diplome-de-lecture-a-imprimer")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Connectez-vous pour sélectionner automatiquement vos élèves" in html
    assert "inputRecipient" in html


def test_resources_sample_texts_harmonized(client):
    """Vérifie l'harmonisation stricte des textes d'exemple entre les inputs et la prévisualisation."""
    # 1. Diplôme
    resp_dip = client.get("/ressources/diplome-de-lecture-a-imprimer")
    html_dip = resp_dip.get_data(as_text=True)
    assert 'value="Décerné avec toutes les félicitations de la classe à"' in html_dip
    assert (
        'id="diplomeSubtitle">Décerné avec toutes les félicitations de la classe à<'
        in html_dip
    )
    assert (
        "pour sa curiosité, son autonomie et son engagement dans ses lectures de classe."
        in html_dip
    )

    # 2. Charte
    resp_ch = client.get("/ressources/charte-coin-lecture-a-imprimer")
    html_ch = resp_ch.get_data(as_text=True)
    assert (
        "Je prends soin des livres : je tourne les pages avec délicatesse et des mains propres."
        in html_ch
    )
    assert (
        "Je respecte le calme du lieu : je lis silencieusement ou je chuchote pour ne pas déranger mes camarades."
        in html_ch
    )

    # 3. Bingo
    resp_bg = client.get("/ressources/defi-lecture-bingo-a-imprimer")
    html_bg = resp_bg.get_data(as_text=True)
    assert 'value="DÉFI LECTURE DES VACANCES"' in html_bg
    assert 'id="bingoTitle"' in html_bg and "DÉFI LECTURE DES VACANCES" in html_bg
    assert (
        "Coche chaque défi accompli pour compléter ta grille et progresser dans tes lectures."
        in html_bg
    )

    # 4. Fiches avis
    resp_fa = client.get("/ressources/fiche-de-lecture-a-imprimer")
    html_fa = resp_fa.get_data(as_text=True)
    assert 'value="COUP DE CŒUR DE LECTEUR"' in html_fa
    assert "COUP DE CŒUR DE LECTEUR" in html_fa


def test_editable_elements_present_on_all_resources(client):
    """Vérifie que chaque ressource contient des éléments de classe .editable."""
    routes = [
        "/ressources/diplome-de-lecture-a-imprimer",
        "/ressources/charte-coin-lecture-a-imprimer",
        "/ressources/marque-pages-a-imprimer",
        "/ressources/defi-lecture-bingo-a-imprimer",
        "/ressources/fiche-de-lecture-a-imprimer",
        "/ressources/passeport-de-lecture-a-imprimer",
    ]
    for r in routes:
        resp = client.get(r)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'class="' in html and "editable" in html, (
            f"Pas de classe editable sur {r}"
        )

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    mock_user.is_premium = True
    with patch("flask_login.utils._get_user", return_value=mock_user):
        resp = client.get("/ressources/etiquettes")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'class="' in html and "editable" in html


def test_mobile_responsive_preview_structure(client):
    """Vérifie que la structure HTML et CSS permet l'affichage de la preview sous la sidebar sur mobile."""
    # 1. Vérification HTML sur un éditeur
    resp = client.get("/ressources/diplome-de-lecture-a-imprimer")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="studioSidebarTop"' in html
    assert 'id="studioPreviewContainer"' in html
    assert 'href="#studioPreviewContainer"' in html
    assert "studio-mobile-only" in html
    assert "studio-canvas-container" in html

    # 2. Vérification que la sidebar précède le container de preview dans le DOM
    sidebar_pos = html.find("studio-sidebar")
    preview_pos = html.find("studioPreviewContainer")
    assert sidebar_pos != -1 and preview_pos != -1
    assert sidebar_pos < preview_pos

    # 3. Vérification des règles CSS responsive
    resp_css = client.get("/static/css/ressources_editor.css")
    assert resp_css.status_code == 200
    css = resp_css.get_data(as_text=True)
    assert "@media screen and (max-width: 1023px)" in css
    assert "flex-direction: column" in css
    assert "overflow-x: hidden" in css
    assert "max-width: 100vw" in css

    # 4. Vérification que le JS utilise viewportWidth pour le calcul de fitToScreen
    resp_js = client.get("/static/javascript/ressources_editor.js")
    assert resp_js.status_code == 200
    js = resp_js.get_data(as_text=True)
    assert "viewportWidth" in js


def test_lead_magnets_seo_and_matomo_tracking(client):
    """Vérifie la présence des métadonnées SEO, tags Matomo et boutons Pinterest sur les lead magnets."""
    lead_magnets = [
        (
            "/ressources/marque-pages-a-imprimer",
            "marque-pages-a-imprimer",
            "marque_pages",
        ),
        (
            "/ressources/diplome-de-lecture-a-imprimer",
            "diplome-de-lecture-a-imprimer",
            "diplome_lecture",
        ),
        (
            "/ressources/fiche-de-lecture-a-imprimer",
            "fiche-de-lecture-a-imprimer",
            "fiche_lecture",
        ),
    ]

    for url, res_id, mtm_content in lead_magnets:
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # 1. Hreflang restreint à fr et x-default (pas d'en/de)
        assert 'hreflang="fr"' in html
        assert 'hreflang="x-default"' in html
        assert 'hreflang="en"' not in html
        assert 'hreflang="de"' not in html

        # 2. Schema.org LearningResource
        assert '"@type": "LearningResource"' in html

        # 3. Tracking Matomo
        assert "trackPinterestClick" in html
        assert "trackCtaLogiciel" in html
        assert "triggerStudioPrint" in html
        assert "mtm_source" in html
        assert mtm_content in html
        assert f'data-ressource-id="{res_id}"' in html
