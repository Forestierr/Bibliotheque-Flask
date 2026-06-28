import pytest
from flask import get_flashed_messages
from unittest.mock import patch, MagicMock
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


# Test affichage de la liste des élèves
def test_eleve_db(client):
    with (
        patch("project.eleve.get_all_students_info", return_value=[]),
        patch("project.eleve.current_user") as mock_user,
    ):
        mock_user.id = 1
        response = client.get("/eleve")
        assert response.status_code == 200
        assert b"eleve" in response.data or b"Eleve" in response.data


# Test ajout d'un élève (GET)
def test_ajouter_eleve_get(client):
    with patch("project.eleve.current_user") as mock_user:
        mock_user.id = 1
        response = client.get("/eleve/ajout")
        assert response.status_code == 200
        assert b"ajouter" in response.data or b"Ajouter" in response.data


# Test ajout d'un élève (POST, succès)
def test_ajouter_eleve_post_success(client, app):
    with app.app_context():
        with (
            patch("project.eleve.current_user") as mock_user,
            patch("project.eleve.Student.query") as mock_query,
            patch("project.eleve.db.session"),
        ):
            mock_user.id = 1
            mock_query.filter_by().first.return_value = None
            response = client.post(
                "/eleve/ajout",
                data={"name": "Dupont", "firstname": "Jean"},
                follow_redirects=True,
            )
            assert response.status_code in (200, 302)


# Test ajout d'un élève (POST, champs vides)
def test_ajouter_eleve_post_empty(client):
    with patch("project.eleve.current_user") as mock_user:
        mock_user.id = 1
        response = client.post(
            "/eleve/ajout", data={"name": "", "firstname": ""}, follow_redirects=True
        )
        assert b"Veuillez remplir tous les champs" in response.data


# Test ajout d'un élève (POST, déjà existant)
def test_ajouter_eleve_post_exists(client, app):
    with app.app_context():
        with (
            patch("project.eleve.current_user") as mock_user,
            patch("project.eleve.Student.query") as mock_query,
        ):
            mock_user.id = 1
            mock_query.filter_by().first.return_value = MagicMock()
            # Utiliser le contexte de requête pour récupérer les messages flash
            with client:
                client.post(
                    "/eleve/ajout",
                    data={"name": "Dupont", "firstname": "Jean"},
                    follow_redirects=True,
                )
                flashed = get_flashed_messages()
            assert "L'élève existe déjà." in flashed


# Test affichage infos élève
def test_eleve_infos(client):
    with (
        patch("project.eleve.get_student_infos", return_value=(MagicMock(), [], [])),
        patch("project.eleve.current_user") as mock_user,
    ):
        mock_user.id = 1
        response = client.get("/eleve/1")
        assert response.status_code == 200


# Test suppression d'un élève
def test_eleve_delete(client, app):
    with app.app_context():
        mock_student = MagicMock(id=1)
        with (
            patch("project.eleve.current_user") as mock_user,
            patch("project.eleve.Student.query") as mock_query,
            patch("project.eleve.Loan.query") as mock_loan_query,
            patch("project.eleve.db.session"),
        ):
            mock_user.id = 1
            mock_query.filter_by().first.return_value = mock_student
            mock_loan_query.filter_by().all.return_value = []
            response = client.post("/eleve/1/delete")
            assert response.status_code == 302


# Test suppression de tous les élèves
def test_eleve_delete_all(client, app):
    with app.app_context():
        mock_student = MagicMock(id=1)
        with (
            patch("project.eleve.current_user") as mock_user,
            patch("project.eleve.Student.query") as mock_query,
            patch("project.eleve.Loan.query") as mock_loan_query,
            patch("project.eleve.db.session"),
        ):
            mock_user.id = 1
            mock_query.filter_by().all.return_value = [mock_student]
            mock_loan_query.filter_by().all.return_value = []
            response = client.post("/eleve/delete_all")
            assert response.status_code == 302


# Test recherche preview
def test_search_preview(client, app):
    with app.app_context():
        with (
            patch("project.eleve.current_user") as mock_user,
            patch("project.eleve.Student.query") as mock_query,
        ):
            mock_user.id = 1
            mock_query.filter().limit().all.return_value = []
            response = client.post("/eleve/search-preview", data={"search": "Jean"})
            assert response.status_code == 200


# Test recherche complète
def test_search(client):
    with (
        patch("project.eleve.current_user") as mock_user,
        patch("project.eleve.get_search_all_students_info", return_value=[]),
    ):
        mock_user.id = 1
        response = client.post("/eleve/search", data={"search": "Jean"})
        assert response.status_code == 200
