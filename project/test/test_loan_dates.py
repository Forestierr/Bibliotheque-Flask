from datetime import UTC, datetime, timedelta
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
            "LOGIN_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_user(app):
    user = User(
        email="teacher@test.com",
        password="hash",
        name="Professeur",
        default_loan_duration_days=14,
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_loan_is_late_and_days_late(app, test_user):
    with app.app_context():
        book = Book(title="Livre 1", user_id=test_user.id)
        student = Student(name="Dupont", firstname="Alice", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        today = datetime.now(UTC).date()

        # Prêt en retard de 5 jours
        late_loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=today - timedelta(days=20),
            expected_return_date=today - timedelta(days=5),
        )
        # Prêt à jour (retour dans 10 jours)
        ontime_loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=today - timedelta(days=4),
            expected_return_date=today + timedelta(days=10),
        )
        # Prêt à échéance proche (dans 2 jours)
        due_soon_loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=today - timedelta(days=12),
            expected_return_date=today + timedelta(days=2),
        )
        # Prêt retourné (même si date dépassée, il n'est plus en retard)
        returned_loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=today - timedelta(days=20),
            expected_return_date=today - timedelta(days=5),
            date_return=today - timedelta(days=2),
        )

        db.session.add_all([late_loan, ontime_loan, due_soon_loan, returned_loan])
        db.session.commit()

        assert late_loan.is_late is True
        assert late_loan.days_late == 5
        assert late_loan.is_due_soon is False

        assert ontime_loan.is_late is False
        assert ontime_loan.days_late == 0
        assert ontime_loan.is_due_soon is False

        assert due_soon_loan.is_late is False
        assert due_soon_loan.is_due_soon is True

        assert returned_loan.is_late is False
        assert returned_loan.days_late == 0


def test_livre_edit_student_sets_expected_date(app, client, test_user):
    with app.app_context():
        book = Book(title="Livre Test", user_id=test_user.id)
        student = Student(name="Durand", firstname="Bob", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        with (
            patch("project.livre.current_user", test_user),
            patch("flask_login.utils._get_user", return_value=test_user),
        ):
            # 1. Prêt avec date explicite
            client.post(
                f"/livre/{book.id}/edit-student",
                data={
                    "student_id": student.id,
                    "expected_return_date": "2026-11-20",
                },
            )
            loan = Loan.query.filter_by(book_id=book.id).first()
            assert loan is not None
            assert str(loan.expected_return_date) == "2026-11-20"


def test_livre_edit_student_fallback_duration(app, client, test_user):
    with app.app_context():
        test_user.default_loan_duration_days = 21
        db.session.commit()

        book = Book(title="Livre Test 2", user_id=test_user.id)
        student = Student(name="Durand", firstname="Bob", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        today = datetime.now(UTC).date()

        with (
            patch("project.livre.current_user", test_user),
            patch("flask_login.utils._get_user", return_value=test_user),
        ):
            # 2. Prêt sans date explicite -> fallback sur default_loan_duration_days (21j)
            client.post(
                f"/livre/{book.id}/edit-student",
                data={
                    "student_id": student.id,
                },
            )
            loan = Loan.query.filter_by(book_id=book.id).first()
            assert loan is not None
            assert loan.expected_return_date == today + timedelta(days=21)


def test_reglage_updates_default_loan_duration(app, client, test_user):
    with app.app_context(), patch("project.auth.current_user", test_user):
        response = client.post(
            "/reglage",
            data={
                "name": "Professeur Modifié",
                "email": "teacher@test.com",
                "default_loan_duration_days": "28",
            },
        )
        assert response.status_code == 200
        updated_user = db.session.get(User, test_user.id)
        assert updated_user.default_loan_duration_days == 28


def test_livre_infos_renders_clean_chips_and_loan_history(app, client, test_user):
    with app.app_context():
        test_user.default_loan_duration_days = 180
        db.session.commit()

        book = Book(title="Mon Beau Livre", user_id=test_user.id)
        student = Student(name="Martin", firstname="Clara", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        today = datetime.now(UTC).date()
        expected_date = today + timedelta(days=180)

        with (
            patch("project.livre.current_user", test_user),
            patch("flask_login.utils._get_user", return_value=test_user),
        ):
            response = client.get(f"/livre/{book.id}")
            assert response.status_code == 200
            html = response.data.decode("utf-8")

            # Pas de mention anxiogène ou polluante '(défaut)'
            assert "(défaut)" not in html
            assert "180 jours" in html
            # '2 semaines' ne doit pas apparaître si le défaut est personnalisé (180j)
            assert "2 semaines" not in html
            # La date calculée est pré-remplie dès le rendu serveur
            assert expected_date.strftime("%Y-%m-%d") in html
            # Boutons d'action dans le hero
            assert "Modifier" in html
            assert "Dupliquer" in html

        # Ajout d'un prêt actif
        active_loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=today,
            expected_return_date=expected_date,
        )
        db.session.add(active_loan)
        db.session.commit()

        with (
            patch("project.livre.current_user", test_user),
            patch("flask_login.utils._get_user", return_value=test_user),
        ):
            response = client.get(f"/livre/{book.id}")
            assert response.status_code == 200
            html = response.data.decode("utf-8")
            assert "Actuellement prêté à" in html
            assert "Rendre le livre" in html
            assert "Clara" in html
