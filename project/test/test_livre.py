from unittest.mock import MagicMock, patch

import pytest

# On suppose que tu as une factory create_app dans project/__init__.py
from project import create_app
from project.livre import get_book_from_api


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


# Test de la fonction utilitaire get_book_from_api
@patch("project.livre.requests.get")
def test_get_book_from_api_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "totalItems": 1,
        "items": [
            {
                "volumeInfo": {
                    "title": "Test Book",
                    "authors": ["Author 1", "Author 2"],
                    "publisher": "Test Publisher",
                    "publishedDate": "2020",
                    "subtitle": "Roman",
                }
            }
        ],
    }
    mock_get.return_value = mock_response
    result = get_book_from_api("1234567890")
    assert result["title"] == "Test Book"
    assert result["authors"] == "Author 1, Author 2"
    assert result["editor"] == "Test Publisher"
    assert result["year"] == "2020"
    assert result["type"] == "Roman"
    assert result["isbn"] == "1234567890"


@patch("project.livre.requests.get")
def test_get_book_from_api_not_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"totalItems": 0}
    mock_get.return_value = mock_response
    result = get_book_from_api("0000000000")
    assert result is None


# Test d'accès à la page principale des livres
@patch("project.livre.db")
@patch("project.livre.current_user")
def test_livre_db_route(mock_user, mock_db, client):
    mock_user.id = 1
    mock_db.session.query().filter().count.return_value = 0
    with (
        patch("project.livre.get_books_student_tags", return_value=[]),
        patch("project.livre.get_students", return_value=[]),
        patch("project.livre.get_tags", return_value=[]),
    ):
        response = client.get("/livre")
        assert response.status_code == 200
        assert b"livre" in response.data or b"Livre" in response.data


# Test ajout d'un livre (GET)
@patch("project.livre.current_user")
def test_livre_ajout_get(mock_user, client, app):
    mock_user.id = 1
    with app.app_context(), patch("project.livre.Tags.query") as mock_tags:
        mock_tags.filter_by().all.return_value = []
        response = client.get("/livre/ajout")
        assert response.status_code == 200
        assert b"ajouter" in response.data or b"Ajouter" in response.data


# Test suppression d'un livre inexistant
@patch("project.livre.current_user")
@patch("project.livre.get_book_by_id", return_value=None)
def test_livre_infos_not_found(mock_get_book, mock_user, client):
    mock_user.id = 1
    response = client.get("/livre/999")
    assert response.status_code == 302  # Redirection


# Test suppression de tous les livres (POST)
@patch("project.livre.current_user")
@patch("project.livre.get_books", return_value=[])
def test_livre_delete_all(mock_get_books, mock_user, client):
    mock_user.id = 1
    with patch("project.livre.db.session"):
        response = client.post("/livre/delete_all")
        assert response.status_code == 302


# Test recherche preview (POST)
@patch("project.livre.current_user")
def test_search_preview_empty(mock_user, client):
    mock_user.id = 1
    response = client.post("/livre/search-preview", data={"search": ""})
    assert response.status_code == 204


# Test recherche preview avec résultat
@patch("project.livre.current_user")
def test_search_preview_with_result(mock_user, client):
    mock_user.id = 1
    # Création d'un mock qui simule la structure attendue par le template
    mock_book = MagicMock()
    mock_book.Book.title = "Test"
    with patch("project.livre.get_search_5_books", return_value=[mock_book]):
        response = client.post("/livre/search-preview", data={"search": "Test"})
        assert response.status_code == 200
        assert b"Test" in response.data


# Test existence d'un livre par ISBN
@patch("project.livre.current_user")
@patch("project.livre.get_books_by_isbn")
def test_livre_exist_found(mock_get_books, mock_user, client):
    mock_user.id = 1
    mock_get_books.return_value = [MagicMock(id=42)]
    response = client.get("/livre/1234567890/exist")
    assert response.status_code == 200
    assert b"42" in response.data


@patch("project.livre.current_user")
@patch("project.livre.get_books_by_isbn", return_value=[])
def test_livre_exist_not_found(mock_get_books, mock_user, client):
    mock_user.id = 1
    response = client.get("/livre/0000000000/exist")
    assert response.status_code == 404
    assert b"Book not found" in response.data
