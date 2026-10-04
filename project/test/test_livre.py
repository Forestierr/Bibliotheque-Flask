from unittest.mock import MagicMock, patch

import pytest
import requests

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
    assert mock_get.call_args[1].get("timeout") == 5


@patch("project.livre.requests.get")
def test_get_book_from_api_not_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"totalItems": 0}
    mock_get.return_value = mock_response
    result = get_book_from_api("0000000000")
    assert result is None


@patch("project.livre.requests.get")
def test_get_book_from_api_timeout(mock_get):
    mock_get.side_effect = requests.Timeout("Connection timed out")
    result = get_book_from_api("9782800127279")
    assert result is None
    assert mock_get.call_count == 2
    for call_obj in mock_get.call_args_list:
        assert call_obj[1].get("timeout") == 5


@patch("project.livre.requests.get")
def test_get_book_from_api_request_exception(mock_get):
    mock_get.side_effect = requests.RequestException("Network unreachable")
    result = get_book_from_api("9782800127279")
    assert result is None


@patch("project.livre.requests.get")
def test_get_book_from_api_invalid_json(mock_get):
    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError("Invalid JSON response")
    mock_get.return_value = mock_response
    result = get_book_from_api("9782800127279")
    assert result is None


@patch.dict("os.environ", {"GOOGLE_BOOK_API_KEY": "test-key"})
@patch("project.livre.requests.get")
def test_get_book_from_api_with_api_key(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"totalItems": 0}
    mock_get.return_value = mock_response
    result = get_book_from_api("9782800127279")
    assert result is None
    google_url = mock_get.call_args_list[0][0][0]
    assert "&key=test-key" in google_url


@patch.dict("os.environ", {}, clear=True)
@patch("project.livre.requests.get")
def test_get_book_from_api_without_api_key(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"totalItems": 0}
    mock_get.return_value = mock_response
    result = get_book_from_api("9782800127279")
    assert result is None
    google_url = mock_get.call_args_list[0][0][0]
    assert "&key=" not in google_url


@patch.dict("os.environ", {"CONTACT_EMAIL": "contact@example.org"})
@patch("project.livre.requests.get")
def test_get_book_from_api_open_library_fallback(mock_get):
    google_response = MagicMock()
    google_response.json.return_value = {"totalItems": 0}

    ol_response = MagicMock()
    ol_response.json.return_value = {
        "ISBN:9782253168522": {
            "title": "Steve Jobs",
            "authors": [{"name": "Walter Isaacson"}],
            "publishers": [{"name": "Librairie générale française"}],
            "publish_date": "2012",
        }
    }
    mock_get.side_effect = [google_response, ol_response]

    result = get_book_from_api("9782253168522")
    assert result is not None
    assert result["title"] == "Steve Jobs"
    assert result["authors"] == "Walter Isaacson"
    assert result["editor"] == "Librairie générale française"
    assert result["year"] == "2012"
    assert result["isbn"] == "9782253168522"
    ol_call_headers = mock_get.call_args_list[1][1].get("headers", {})
    assert "User-Agent" in ol_call_headers
    assert (
        ol_call_headers["User-Agent"] == "Bibliotheque-Flask/1.0 (contact@example.org)"
    )


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


@patch("project.livre.requests.get")
@patch("project.livre.current_user")
def test_livre_ajout_with_isbn_timeout(mock_user, mock_get, client, app):
    mock_user.id = 1
    mock_get.side_effect = requests.Timeout("Connection timed out")
    with app.app_context(), patch("project.livre.Tags.query") as mock_tags:
        mock_tags.filter_by().all.return_value = []
        response = client.get("/livre/ajout?isbn=9782800127279")
        assert response.status_code == 200
        assert b"9782800127279" in response.data


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


# Test existence d'un livre par code-barre personnalisé (BAC-A-001)
@patch("project.livre.current_user")
@patch("project.livre.get_books_by_barcode")
def test_livre_exist_by_barcode(mock_get_barcode, mock_user, client):
    mock_user.id = 1
    mock_get_barcode.return_value = [MagicMock(id=99)]
    response = client.get("/livre/BAC-A-001/exist")
    assert response.status_code == 200
    assert b"99" in response.data


# Test existence renvoyant flag is_isbn pour code 978...
@patch("project.livre.current_user")
@patch("project.livre.get_books_by_barcode", return_value=[])
@patch("project.livre.get_books_by_isbn", return_value=[])
def test_livre_exist_is_isbn_flag(mock_isbn, mock_barcode, mock_user, client):
    mock_user.id = 1
    # Pour un ISBN officiel non trouvé
    resp_isbn = client.get("/livre/9782070612758/exist")
    assert resp_isbn.status_code == 404
    data_isbn = resp_isbn.get_json()
    assert data_isbn["is_isbn"] is True

    # Pour un code custom non trouvé
    resp_custom = client.get("/livre/BAC-A-001/exist")
    assert resp_custom.status_code == 404
    data_custom = resp_custom.get_json()
    assert data_custom["is_isbn"] is False
