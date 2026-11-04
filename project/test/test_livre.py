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
    assert mock_get.call_count == 3
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


def test_scan_counter_not_incremented_when_not_found(client, app):
    """Vérifie que le compteur de scans n'augmente PAS si le livre n'est pas trouvé."""
    from project import db
    from project.models import User

    with app.app_context():
        user = User(
            id=301,
            email="scan_not_found@test.com",
            plan="free",
            free_scans_used=5,
            trial_ends_at=None,
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 301)

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.livre.current_user", u),
            patch("project.livre.get_books_by_barcode", return_value=[]),
            patch("project.livre.get_books_by_isbn", return_value=[]),
            patch("project.livre.get_book_from_api", return_value=None),
            patch("project.livre.Tags.query") as mock_tags,
        ):
            mock_tags.filter_by().all.return_value = []
            # 1. Le scan en base locale renvoie 404
            resp_exist = client.get("/livre/9789999999999/exist")
            assert resp_exist.status_code == 404
            assert u.free_scans_used == 5  # Le compteur NE DOIT PAS avoir augmenté

            # 2. Redirection vers /livre/ajout suite au scan : l'API ne trouve pas le livre
            resp_ajout = client.get("/livre/ajout?isbn=9789999999999")
            assert resp_ajout.status_code == 200
            content = resp_ajout.get_data(as_text=True)
            assert "Informations du livre introuvables automatiquement" in content
            assert "bibliothèque collaborative" in content
            assert u.free_scans_used == 5  # Le compteur reste toujours à 5 !


def test_scan_counter_incremented_when_api_finds_book(client, app):
    """Vérifie que le compteur de scans augmente si le livre est trouvé par l'API suite au scan."""
    from project import db
    from project.models import User

    with app.app_context():
        user = User(
            id=302,
            email="scan_found@test.com",
            plan="free",
            free_scans_used=5,
            trial_ends_at=None,
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 302)

        found_book = {
            "title": "Livre Trouvé",
            "authors": "Auteur",
            "editor": "Éditeur",
            "year": "2024",
            "type": "Roman",
            "isbn": "9782070612758",
        }

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.livre.current_user", u),
            patch("project.livre.get_books_by_barcode", return_value=[]),
            patch("project.livre.get_books_by_isbn", return_value=[]),
            patch("project.livre.get_book_from_api", return_value=found_book),
            patch("project.livre.Tags.query") as mock_tags,
        ):
            mock_tags.filter_by().all.return_value = []
            # 1. Le scan en base locale renvoie 404
            resp_exist = client.get("/livre/9782070612758/exist")
            assert resp_exist.status_code == 404
            assert u.free_scans_used == 5  # Pas encore incrémenté

            # 2. Redirection vers /livre/ajout : l'API trouve le livre
            resp_ajout = client.get("/livre/ajout?isbn=9782070612758")
            assert resp_ajout.status_code == 200
            assert u.free_scans_used == 6  # Incrémenté car le livre a été trouvé !

            # 3. Recharger la page ne doit pas ré-incrémenter (protection anti-double-compte)
            resp_reload = client.get("/livre/ajout?isbn=9782070612758")
            assert resp_reload.status_code == 200
            assert u.free_scans_used == 6


def test_get_book_from_bnf_success():
    from project.livre import get_book_from_bnf

    xml_response = b"""<?xml version="1.0" encoding="UTF-8"?>
    <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:dc="http://purl.org/dc/elements/1.1/">
        <srw:records>
            <srw:record>
                <srw:recordData>
                    <dc:title>Le petit prince / Antoine de Saint-Exup\xc3\xa9ry</dc:title>
                    <dc:creator>Saint-Exup\xc3\xa9ry, Antoine de (1900-1944). Auteur du texte</dc:creator>
                    <dc:publisher>Gallimard (Paris)</dc:publisher>
                    <dc:date>2007</dc:date>
                    <dc:description>Collection : Folio junior ; 100</dc:description>
                </srw:recordData>
            </srw:record>
        </srw:records>
    </srw:searchRetrieveResponse>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_response

    mock_cover_resp = MagicMock()
    mock_cover_resp.status_code = 200
    mock_cover_resp.headers = {"Content-Type": "image/jpeg"}

    with patch("project.livre.requests.get") as mock_get:
        mock_get.side_effect = [mock_resp, mock_cover_resp]
        book = get_book_from_bnf("9782070612758")

        assert book is not None
        assert book["title"] == "Le petit prince"
        assert book["authors"] == "Antoine de Saint-Exupéry"
        assert book["editor"] == "Gallimard"
        assert book["year"] == "2007"
        assert book["type"] == "Folio junior"
        assert "recupererImage" in book["image_url"]


def test_book_image_url_persistence(client, app):
    """Vérifie que le champ image_url est bien persisté lors de l'ajout d'un livre."""
    from project import db
    from project.models import Book, User

    with app.app_context():
        user = User(id=401, email="image_test@test.com", plan="premium")
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 401)

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.livre.current_user", u),
        ):
            resp = client.post(
                "/livre/ajout",
                data={
                    "title": "Livre Illustré",
                    "author": "Illustrateur",
                    "editor": "Éditions Test",
                    "year": "2024",
                    "type": "Album",
                    "isbn": "9782070612758",
                    "image_url": "https://example.com/cover.jpg",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200
            created = Book.query.filter_by(title="Livre Illustré").first()
            assert created is not None
            assert created.image_url == "https://example.com/cover.jpg"


def test_user_show_book_covers_setting(client, app):
    """Vérifie que l'utilisateur peut activer ou désactiver l'affichage des couvertures."""
    from project import db
    from project.models import User

    with app.app_context():
        user = User(
            id=402,
            email="covers_pref@test.com",
            name="Prof Test",
            plan="free",
            show_book_covers=True,
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 402)

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.auth.current_user", u),
        ):
            # 1. Désactiver les couvertures (décocher la case)
            resp = client.post(
                "/reglage",
                data={
                    "name": "Prof Test",
                    "email": "covers_pref@test.com",
                    "preferred_language": "fr",
                    # absence de show_book_covers = case décochée
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200
            u_updated = db.session.get(User, 402)
            assert u_updated.show_book_covers is False

            # 2. Réactiver les couvertures
            resp2 = client.post(
                "/reglage",
                data={
                    "name": "Prof Test",
                    "email": "covers_pref@test.com",
                    "preferred_language": "fr",
                    "show_book_covers": "1",
                },
                follow_redirects=True,
            )
            assert resp2.status_code == 200
            u_updated2 = db.session.get(User, 402)
            assert u_updated2.show_book_covers is True


def test_ajouter_livre_with_unsubmitted_tags_in_raw_input(client, app):
    """Vérifie qu'un tag saisi dans tags_input_raw (sans avoir appuyé sur Entrée) est bien enregistré."""
    from unittest.mock import patch

    from project import db
    from project.models import Book, BookTags, Tags, User

    with app.app_context():
        user = User(
            id=410,
            email="tagstest@test.com",
            name="Prof Tags",
            plan="free",
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 410)

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.livre.current_user", u),
        ):
            resp = client.post(
                "/livre/ajout",
                data={
                    "title": "Livre avec Tag non validé par Enter",
                    "author": "Auteur Test",
                    "tags": "",  # champ masqué vide car pas de clic Enter
                    "tags_input_raw": "Aventure, Fantastique",  # texte restant dans le champ
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            book = Book.query.filter_by(
                title="Livre avec Tag non validé par Enter", user_id=410
            ).first()
            assert book is not None

            book_tags = BookTags.query.filter_by(book_id=book.id).all()
            tag_ids = [bt.tag_id for bt in book_tags]
            tags_in_db = Tags.query.filter(Tags.id.in_(tag_ids)).all()
            tag_names = {t.name for t in tags_in_db}
            assert "Aventure" in tag_names
            assert "Fantastique" in tag_names

            from project.query import get_book_tags

            fetched_tags = get_book_tags(410, book.id)
            fetched_names = [t.name for t in fetched_tags]
            assert "Aventure" in fetched_names
            assert "Fantastique" in fetched_names

            # Vérifie que la page d'édition GET reçoit et affiche bien les tags
            resp_edit_get = client.get(f"/livre/{book.id}/edit")
            assert resp_edit_get.status_code == 200
            content = resp_edit_get.get_data(as_text=True)
            assert "Aventure" in content
            assert "Fantastique" in content


def test_edit_livre_with_unsubmitted_tags_in_raw_input(client, app):
    """Vérifie que la modification d'un livre prend en compte le texte saisi dans tags_input_raw."""
    from unittest.mock import patch

    from project import db
    from project.models import Book, BookTags, Tags, User

    with app.app_context():
        user = User(
            id=411,
            email="tagstest_edit@test.com",
            name="Prof Tags Edit",
            plan="free",
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 411)

        book = Book(
            id=510,
            title="Livre Avant Edit",
            user_id=411,
        )
        db.session.add(book)
        db.session.commit()

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.livre.current_user", u),
        ):
            resp = client.post(
                "/livre/510/edit",
                data={
                    "title": "Livre Après Edit",
                    "tags": "Roman",
                    "tags_input_raw": "Policier",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            book_tags = BookTags.query.filter_by(book_id=510).all()
            tag_ids = [bt.tag_id for bt in book_tags]
            tags_in_db = Tags.query.filter(Tags.id.in_(tag_ids)).all()
            tag_names = {t.name for t in tags_in_db}
            assert "Roman" in tag_names
            assert "Policier" in tag_names


def test_reglage_next_redirection(client, app):
    """Vérifie que la sauvegarde des réglages redirige vers le paramètre next si fourni."""
    from unittest.mock import patch

    from project import db
    from project.models import User

    with app.app_context():
        user = User(
            id=412,
            email="reglage_next@test.com",
            name="Prof Next",
            plan="free",
        )
        db.session.add(user)
        db.session.commit()
        u = db.session.get(User, 412)

        with (
            patch("flask_login.utils._get_user", return_value=u),
            patch("project.auth.current_user", u),
        ):
            resp = client.post(
                "/reglage",
                data={
                    "name": "Prof Next Modifié",
                    "email": "reglage_next@test.com",
                    "preferred_language": "fr",
                    "next": "/livre",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 302
            assert resp.headers["Location"] == "/livre"
            u_updated = db.session.get(User, 412)
            assert u_updated.name == "Prof Next Modifié"


def test_livre_exist_loaned_status(client, app):
    from datetime import UTC, datetime

    from project import db
    from project.models import Book, Loan, Student, User

    with app.app_context():
        user = User.query.filter_by(email="test@test.com").first()
        if not user:
            user = User(email="test@test.com", password="hash", name="Test")
            db.session.add(user)
            db.session.commit()

        book = Book(title="Livre Emprunte", user_id=user.id, isbn="9780000000001")
        student = Student(name="Martin", firstname="Sophie", user_id=user.id)
        db.session.add_all([book, student])
        db.session.commit()

        loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=datetime.now(tz=UTC).date(),
        )
        db.session.add(loan)
        db.session.commit()

        with patch("project.livre.current_user", user):
            resp = client.get("/livre/9780000000001/exist")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["id"] == book.id
            assert data["is_loaned"] is True
            assert data["loan_id"] == loan.id
            assert data["borrower_name"] == "Sophie Martin"
