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
    with (
        app.app_context(),
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
    with (
        app.app_context(),
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
    with (
        app.app_context(),
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


def test_eleve_infos_and_delete_not_found(client, app):
    """Vérifie que la consultation et suppression d'un élève inexistant redirigent avec un message d'erreur au lieu de crasher."""
    with (
        app.app_context(),
        patch("project.eleve.current_user") as mock_user,
        patch("project.eleve.get_student_infos", return_value=(None, [], [])),
        patch("project.eleve.Student.query") as mock_query,
    ):
        mock_user.id = 1
        mock_query.filter_by().first.return_value = None

        with client:
            resp_info = client.get("/eleve/99999", follow_redirects=True)
            assert resp_info.status_code == 200
            flashed = get_flashed_messages()
            assert any("Élève introuvable." in msg for msg in flashed)

        with client:
            resp_del = client.post("/eleve/99999/delete", follow_redirects=True)
            assert resp_del.status_code == 200
            flashed = get_flashed_messages()
            assert any("Élève introuvable." in msg for msg in flashed)


def test_eleve_multi_tenant_isolation():
    """Test d'intégration réel : un enseignant ne peut ni consulter ni supprimer l'élève d'un autre enseignant."""
    from project import db
    from project.models import Student, User

    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "secret-eleve-isolation",
        }
    )
    with app.app_context():
        db.create_all()

        user1 = User(id=1, email="prof1@ecole.ch", password="hash")
        user2 = User(id=2, email="prof2@ecole.ch", password="hash")
        student_prof1 = Student(id=10, name="Dupond", firstname="Alice", user_id=1)
        db.session.add_all([user1, user2, student_prof1])
        db.session.commit()

        client = app.test_client()

        # Connecté en tant que Prof 2
        with client.session_transaction() as sess:
            sess["_user_id"] = "2"

        # Prof 2 tente de consulter l'élève de Prof 1
        resp_view = client.get("/eleve/10", follow_redirects=False)
        assert resp_view.status_code == 302
        assert "/eleve" in resp_view.headers.get("Location", "")

        # Prof 2 tente de supprimer l'élève de Prof 1
        resp_del = client.post("/eleve/10/delete", follow_redirects=False)
        assert resp_del.status_code == 302

        # L'élève de Prof 1 est TOUJOURS en base de données intact
        assert db.session.get(Student, 10) is not None
        assert db.session.get(Student, 10).user_id == 1
