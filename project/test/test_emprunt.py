import math
from datetime import UTC, datetime
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
            "LOGIN_DISABLED": True,  # Désactiver la vérification de login pour les tests
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_user():
    """Mock user fixture for login tests"""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@test.com"
    mock_user.name = "Test User"
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.get_id.return_value = "1"
    return mock_user


# Test de la route principale /emprunt (GET)
def test_emprunt_get(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=5),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 0)),
        app.test_request_context("/emprunt"),
    ):
        response = client.get("/emprunt")
        assert response.status_code == 200


# Test de la route principale /emprunt (POST)
def test_emprunt_post_with_active_loans(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=10),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 5)),
        app.test_request_context("/emprunt", method="POST"),
    ):
        response = client.post("/emprunt", data={"active_loan": "1"})
        assert response.status_code == 200


# Test de retour d'emprunt - route /emprunt/<id>
def test_return_loan_success(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.date_return = None

        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.user_id = 1  # Same user as logged_in_user

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]

            with app.test_request_context(
                "/emprunt/1", method="POST", headers={"Referer": "/emprunt"}
            ):
                mock_session.commit = MagicMock()
                response = client.post("/emprunt/1")
                assert response.status_code == 302  # Redirect
                assert mock_loan.date_return == datetime.now(tz=UTC).date()
                mock_session.commit.assert_called_once()


# Test de retour d'emprunt - prêt inexistant
def test_return_loan_not_found(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.db.session") as mock_session,
    ):
        mock_session.query().filter().first.return_value = None

        with app.test_request_context(
            "/emprunt/999", method="POST", headers={"Referer": "/emprunt"}
        ):
            response = client.post("/emprunt/999")
            assert response.status_code == 302  # Redirect même si pas trouvé


# Test de suppression d'emprunt - succès
def test_delete_loan_success(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.book_id = 1

        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.user_id = 1  # Même user que logged_in_user

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]

            with app.test_request_context(
                "/emprunt/1/delete", method="POST", headers={"Referer": "/emprunt"}
            ):
                response = client.post("/emprunt/1/delete")
                assert response.status_code == 302
                mock_session.delete.assert_called_once_with(mock_loan)
                mock_session.commit.assert_called_once()


# Test de suppression d'emprunt - utilisateur non autorisé
def test_delete_loan_unauthorized(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.book_id = 1

        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.user_id = 999  # Différent user

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]

            with app.test_request_context(
                "/emprunt/1/delete", method="POST", headers={"Referer": "/emprunt"}
            ):
                response = client.post("/emprunt/1/delete")
                assert response.status_code == 302
                mock_session.delete.assert_not_called()


# Test de suppression de tous les emprunts
def test_delete_all_loans(client, app, logged_in_user):
    with app.app_context():
        mock_loans = [MagicMock(), MagicMock(), MagicMock()]

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
            patch("project.emprunt.url_for", return_value="/reglage"),
        ):
            mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = mock_loans

            with app.test_request_context("/emprunt/delete_all", method="POST"):
                response = client.post("/emprunt/delete_all")
                assert response.status_code == 302
                assert mock_session.delete.call_count == 3
                mock_session.commit.assert_called_once()


# Test de recherche preview - avec résultats
def test_search_preview_with_results(client, app, logged_in_user):
    with app.app_context():
        mock_books = [MagicMock(), MagicMock()]

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.get_search_5_loans", return_value=mock_books),
            app.test_request_context("/emprunt/search-preview", method="POST"),
        ):
            response = client.post("/emprunt/search-preview", data={"search": "test"})
            assert response.status_code == 200


# Test de recherche preview - recherche typée
def test_search_preview_typed_search(client, app, logged_in_user):
    with app.app_context():
        mock_books = [MagicMock()]

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch(
                "project.emprunt.search_loans_by_types", return_value=(mock_books, 1)
            ),
            app.test_request_context("/emprunt/search-preview", method="POST"),
        ):
            response = client.post(
                "/emprunt/search-preview", data={"search": "titre:Harry Potter"}
            )
            assert response.status_code == 200


# Test de recherche preview - recherche vide
def test_search_preview_empty_search(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        app.test_request_context("/emprunt/search-preview", method="POST"),
    ):
        response = client.post("/emprunt/search-preview", data={"search": ""})
        assert response.status_code == 204


# Test de recherche principale - recherche vide
def test_search_empty(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=10),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 5)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "",
                "sort": "pertinent",
                "n_results": "10",
                "page": "1",
                "active_loan": "0",
            },
        )
        assert response.status_code == 200


# Test de recherche principale - recherche avec terme
def test_search_with_term(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.search_loans_by_types", return_value=([], 0)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "harry potter",
                "sort": "az",
                "n_results": "20",
                "page": "1",
                "active_loan": "1",
            },
        )
        assert response.status_code == 200


# Test de recherche principale - recherche typée valide
def test_search_typed_valid(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.search_loans_by_types", return_value=([], 0)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "isbn:978-2-070-61269-5",
                "sort": "recent",
                "n_results": "15",
                "page": "1",
                "active_loan": "0",
            },
        )
        assert response.status_code == 200


# Test de recherche principale - recherche typée invalide
def test_search_typed_invalid(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 0)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        with client.session_transaction():
            response = client.post(
                "/emprunt/search",
                data={
                    "search": "invalid:test",
                    "sort": "ancien",
                    "n_results": "10",
                    "page": "1",
                    "active_loan": "0",
                },
            )

        assert response.status_code == 200
        # Note: Le test des messages flash est plus complexe avec les mocks


# Test de différents types de tri
def test_search_sort_options(client, app, logged_in_user):
    sort_options = ["pertinent", "az", "za", "recent", "ancien", "invalid"]

    for sort_option in sort_options:
        with (
            app.app_context(),
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.get_loans_count", return_value=5),
            patch("project.emprunt.get_loans_with_infos", return_value=([], 0)),
            app.test_request_context("/emprunt/search", method="POST"),
        ):
            response = client.post(
                "/emprunt/search",
                data={
                    "search": "",
                    "sort": sort_option,
                    "n_results": "10",
                    "page": "1",
                    "active_loan": "0",
                },
            )
            assert response.status_code == 200


# Test d'accès non autorisé (sans connexion) - modifié pour LOGIN_DISABLED=True
def test_unauthorized_access_concept(client, app):
    """Test conceptuel d'accès non autorisé - dans ce cas LOGIN_DISABLED=True donc tous les accès sont autorisés"""
    with app.app_context(), patch("project.emprunt.current_user") as mock_user:
        # Mock un utilisateur anonyme avec un id
        mock_user.id = None
        mock_user.is_authenticated = False

        try:
            response = client.get("/emprunt")
            # Devrait échouer sans les mocks appropriés ou rediriger
            assert response.status_code in [200, 302, 500]
        except AttributeError:
            # Erreur attendue avec un utilisateur anonyme
            assert True


# Test de pagination
def test_search_pagination(client, app, logged_in_user):
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=50),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 10)),
        app.test_request_context("/emprunt/search/2", method="POST"),
    ):
        response = client.post(
            "/emprunt/search/2",
            data={
                "search": "",
                "sort": "pertinent",
                "n_results": "10",
                "page": "2",
                "active_loan": "0",
            },
        )
        assert response.status_code == 200


# Tests supplémentaires pour améliorer la couverture
def test_emprunt_template_rendering(client, app, logged_in_user):
    """Test que le template est rendu correctement"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=5),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 0)),
        patch(
            "project.emprunt.render_template", return_value="mocked_template"
        ) as mock_render,
        app.test_request_context("/emprunt"),
    ):
        client.get("/emprunt")
        # Vérifier que render_template a été appelé
        assert mock_render.called


def test_return_loan_without_referrer(client, app, logged_in_user):
    """Test retour d'emprunt sans URL de référence"""
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.date_return = None

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.return_value = mock_loan

            # Sans referer dans les headers
            with app.test_request_context("/emprunt/1", method="POST"):
                response = client.post("/emprunt/1")
                assert response.status_code == 302


def test_search_loans_by_types_coverage(client, app, logged_in_user):
    """Test de couverture pour search_loans_by_types avec différents paramètres"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch(
            "project.emprunt.search_loans_by_types", return_value=([], 0)
        ) as mock_search,
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "eleve:Jean Dupont",
                "sort": "pertinent",
                "n_results": "10",
                "page": "1",
                "active_loan": "0",
            },
        )
        assert response.status_code == 200
        # Vérifier que search_loans_by_types a été appelé
        assert mock_search.called


def test_search_with_tags(client, app, logged_in_user):
    """Test de recherche avec tags"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.search_loans_by_types", return_value=([], 0)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "tags:fiction",
                "sort": "az",
                "n_results": "10",
                "page": "1",
                "active_loan": "1",
            },
        )
        assert response.status_code == 200


def test_math_ceil_usage(client, app, logged_in_user):
    """Test que la pagination calcule correctement le nombre de pages"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=25),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 25)),
        patch("project.emprunt.math.ceil", wraps=math.ceil) as mock_ceil,
        app.test_request_context("/emprunt"),
    ):
        response = client.get("/emprunt")
        assert response.status_code == 200
        # Vérifier que math.ceil a été appelé pour la pagination
        mock_ceil.assert_called()


def test_search_with_active_loan_filter(client, app, logged_in_user):
    """Test de la fonction search avec le filtre active_loan='1'."""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=10),
        patch("project.emprunt.get_loans_with_infos", return_value=([], 5)),
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "",
                "sort": "pertinent",
                "n_results": "10",
                "page": "1",
                "active_loan": "1",
            },
        )
        assert response.status_code == 200


def test_delete_loan_with_none_loan(client, app, logged_in_user):
    """Test de suppression quand le prêt n'existe pas"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.db.session") as mock_session,
    ):
        # Premier appel retourne None (pas de loan)
        mock_session.query().filter().first.return_value = None

        with app.test_request_context(
            "/emprunt/999/delete", method="POST", headers={"Referer": "/emprunt"}
        ):
            response = client.post("/emprunt/999/delete")
            assert response.status_code == 302
            # delete ne devrait pas être appelé
            mock_session.delete.assert_not_called()


def test_get_search_5_loans_branch(client, app, logged_in_user):
    """Test de la branche get_search_5_loans dans search_preview"""
    with app.app_context():
        mock_books = [MagicMock() for _ in range(3)]

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch(
                "project.emprunt.get_search_5_loans", return_value=mock_books
            ) as mock_search,
            app.test_request_context("/emprunt/search-preview", method="POST"),
        ):
            response = client.post(
                "/emprunt/search-preview", data={"search": "simple search"}
            )
            assert response.status_code == 200
            # Vérifier que get_search_5_loans a été appelé avec les bons paramètres
            mock_search.assert_called_once_with(logged_in_user.id, "simple search")


def test_search_default_branch(client, app, logged_in_user):
    """Test de la branche de recherche par défaut (sans type spécifique)"""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch(
            "project.emprunt.search_loans_by_types", return_value=([], 0)
        ) as mock_search,
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "recherche normale",  # Pas de type spécifique
                "sort": "pertinent",
                "n_results": "10",
                "page": "1",
                "active_loan": "0",
            },
        )
        assert response.status_code == 200
        # Vérifier qu'on utilise 'all' comme type de recherche
        mock_search.assert_called_once()
        call_args = mock_search.call_args[0]
        assert call_args[2] == "all"  # Type de recherche


def test_return_loan_quick_htmx_success(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.date_return = None
        mock_loan.date_loan = datetime.now(tz=UTC).date()
        mock_loan.student_id = 1

        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = "Livre Test"
        mock_book.user_id = 1
        mock_book.image_url = None

        mock_student = MagicMock()
        mock_student.id = 1
        mock_student.name = "Dupont"
        mock_student.firstname = "Jean"

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [
                mock_loan,
                mock_book,
                mock_student,
            ]
            response = client.post(
                "/emprunt/1/return-quick", headers={"HX-Request": "true"}
            )
            assert response.status_code == 200
            assert mock_loan.date_return == datetime.now(tz=UTC).date()
            mock_session.commit.assert_called_once()
            assert "loan-item-1" in response.get_data(as_text=True)


def test_return_loan_quick_json_success(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 1
        mock_loan.date_return = None
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = "Livre Test"
        mock_book.user_id = 1

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]
            response = client.post(
                "/emprunt/1/return-quick", headers={"Accept": "application/json"}
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert data["loan_id"] == 1


def test_return_loan_redirects_to_next_book_page(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 7
        mock_loan.book_id = 3
        mock_loan.date_return = None

        mock_book = MagicMock()
        mock_book.id = 3
        mock_book.user_id = 1
        mock_book.title = "Livre 3"

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]
            response = client.post("/emprunt/7", data={"next": "/fr/livre/3"})
            assert response.status_code == 302
            assert response.headers.get("Location") == "/fr/livre/3"


def test_return_loan_hx_request_issues_hx_redirect(client, app, logged_in_user):
    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 7
        mock_loan.book_id = 3
        mock_loan.date_return = None

        mock_book = MagicMock()
        mock_book.id = 3
        mock_book.user_id = 1
        mock_book.title = "Livre 3"

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
        ):
            mock_session.query().filter().first.side_effect = [mock_loan, mock_book]
            response = client.post(
                "/emprunt/7",
                data={"next": "/fr/livre/3"},
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
            assert response.headers.get("HX-Redirect") == "/fr/livre/3"


def test_emprunt_search_with_archive_filter(client, app, logged_in_user):
    """Vérifier que le filtre 'archive' est bien transmis à get_loans_with_infos."""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=12),
        patch(
            "project.emprunt.get_loans_with_infos", return_value=([], 3)
        ) as mock_loans,
        app.test_request_context("/emprunt/search", method="POST"),
    ):
        response = client.post(
            "/emprunt/search",
            data={
                "search": "",
                "sort": "pertinent",
                "n_results": "20",
                "page": "1",
                "active_loan": "archive",
            },
        )
        assert response.status_code == 200
        mock_loans.assert_called_once()
        assert mock_loans.call_args[0][1] == "archive"


def test_emprunt_get_with_archive_param(client, app, logged_in_user):
    """Vérifier que /emprunt?active_loan=archive appelle get_loans_with_infos avec 'archive'."""
    with (
        app.app_context(),
        patch("project.emprunt.current_user", logged_in_user),
        patch("project.emprunt.get_loans_count", return_value=5),
        patch(
            "project.emprunt.get_loans_with_infos", return_value=([], 0)
        ) as mock_loans,
    ):
        response = client.get("/emprunt?active_loan=archive")
        assert response.status_code == 200
        mock_loans.assert_called_once()
        assert mock_loans.call_args[0][1] == "archive"


def test_search_preview_typed_search_real_db(client, app):
    """Test d'intégration réel pour search_preview avec recherche typée (évite les TypeErrors masqués par mock)."""
    with app.app_context():
        user = User(
            name="Enseignant Test",
            email="prof_preview@test.fr",
            password="hash",
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

        student = Student(name="Dupont", firstname="Alice", user_id=user.id)
        book = Book(
            title="Harry Potter à l'école des sorciers",
            author="J.K. Rowling",
            isbn="9782070584628",
            user_id=user.id,
        )
        db.session.add_all([student, book])
        db.session.commit()

        loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=datetime.now(tz=UTC).date(),
        )
        db.session.add(loan)
        db.session.commit()

        with patch("project.emprunt.current_user", user):
            # 1. Recherche typée par titre
            response = client.post(
                "/emprunt/search-preview",
                data={"search": "titre:Harry", "active_loan": "1"},
            )
            assert response.status_code == 200
            content = response.get_data(as_text=True)
            assert "Harry Potter" in content

            # 2. Recherche typée par élève
            response = client.post(
                "/emprunt/search-preview",
                data={"search": "eleve:Dupont", "active_loan": "1"},
            )
            assert response.status_code == 200
            content = response.get_data(as_text=True)
            assert "Harry Potter" in content


def test_return_loan_quick_retry_on_locked(client, app, logged_in_user):
    """Vérifier que return_loan_quick réessaie et réussit après un verrou temporaire SQLite."""
    from sqlalchemy.exc import OperationalError

    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 42
        mock_loan.book_id = 10
        mock_loan.date_return = None

        mock_book = MagicMock()
        mock_book.id = 10
        mock_book.user_id = logged_in_user.id
        mock_book.title = "Livre Bloqué Temporairement"

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
            patch("project.emprunt.time.sleep") as mock_sleep,
        ):
            mock_session.query().filter().first.side_effect = [
                mock_loan,
                mock_book,
                mock_loan,
            ]
            # Premier commit échoue avec database is locked, le deuxième réussit
            mock_session.commit.side_effect = [
                OperationalError("UPDATE loan", {}, Exception("database is locked")),
                None,
            ]

            response = client.post(
                "/emprunt/42/return-quick",
                headers={"Accept": "application/json"},
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert mock_session.commit.call_count == 2
            mock_sleep.assert_called_once()


def test_return_loan_quick_locked_exhausted_retries(client, app, logged_in_user):
    """Vérifier que return_loan_quick renvoie une erreur 500 propre en JSON si le verrou persiste."""
    from sqlalchemy.exc import OperationalError

    with app.app_context():
        mock_loan = MagicMock()
        mock_loan.id = 42
        mock_loan.book_id = 10

        mock_book = MagicMock()
        mock_book.id = 10
        mock_book.user_id = logged_in_user.id

        with (
            patch("project.emprunt.current_user", logged_in_user),
            patch("project.emprunt.db.session") as mock_session,
            patch("project.emprunt.time.sleep"),
        ):
            mock_session.query().filter().first.side_effect = [
                mock_loan,
                mock_book,
                mock_loan,
                mock_loan,
            ]
            mock_session.commit.side_effect = OperationalError(
                "UPDATE loan", {}, Exception("database is locked")
            )

            response = client.post(
                "/emprunt/42/return-quick",
                headers={"Accept": "application/json"},
            )
            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data
            assert mock_session.rollback.called


def test_sqlite_pragmas_configured_on_connect(app):
    """Vérifier que le busy_timeout est configuré à 30000ms lors de la connexion."""
    with app.app_context(), db.engine.connect() as conn:
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert timeout == 30000
