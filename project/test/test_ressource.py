from datetime import date
from unittest.mock import patch

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


def test_diplome_anonymous(client):
    """Vérifie que l'éditeur de diplôme s'ouvre avec les valeurs par défaut pour un visiteur."""
    response = client.get("/ressources/diplome")
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

        response = client.get("/ressources/diplome?student_id=10")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Léa Martin" in html
        assert "1 livres lus" in html or "1" in html


def test_marque_pages_page(client):
    """Vérifie l'accessibilité du générateur de marque-pages."""
    response = client.get("/ressources/marque-pages")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "FICHE D'EMPRUNT" in html
    assert "AVIS DE LECTURE" in html


def test_charte_page(client):
    """Vérifie l'accessibilité du générateur de la charte du coin lecture."""
    response = client.get("/ressources/charte")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "LA CHARTE DU COIN LECTURE" in html


def test_bingo_page(client):
    """Vérifie l'accessibilité du générateur de bingo lecture."""
    response = client.get("/ressources/bingo")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DÉFI LECTURE" in html


def test_etiquettes_page(client):
    """Vérifie l'accessibilité du générateur d'étiquettes de bacs."""
    response = client.get("/ressources/etiquettes")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ROMANS" in html
    assert "BANDES DESSINÉES" in html


def test_fiches_avis_page(client):
    """Vérifie l'accessibilité du générateur de fiches coup de cœur."""
    response = client.get("/ressources/fiches-avis")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "COUP DE CŒUR" in html


def test_codes_barres_page(client):
    """Vérifie l'accessibilité du générateur de codes-barres."""
    response = client.get("/ressources/codes-barres")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "JsBarcode" in html or "Codes-Barres" in html


def test_passeport_page(client):
    """Vérifie l'accessibilité du passeport de lecture."""
    response = client.get("/ressources/passeport")
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
    for route in ["/ressources/diplome", "/ressources/passeport"]:
        resp = client.get(route)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "size: A4 landscape" in html
        assert "a4-sheet landscape" in html

    # Portrait
    for route in [
        "/ressources/charte",
        "/ressources/bingo",
        "/ressources/marque-pages",
        "/ressources/etiquettes",
        "/ressources/fiches-avis",
    ]:
        resp = client.get(route)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "size: A4 portrait" in html
        assert "a4-sheet portrait" in html

    # Multi-page pour codes-barres
    resp_cb = client.get("/ressources/codes-barres")
    assert resp_cb.status_code == 200
    html_cb = resp_cb.get_data(as_text=True)
    assert "multi-page" in html_cb
