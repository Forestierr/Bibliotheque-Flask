from datetime import UTC, datetime
from io import BytesIO

import openpyxl
import pytest

from project import create_app, db
from project.models import Book, Loan, Student, User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "secret-export-tests",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_export_requires_authentication(client):
    """Vérifie que les routes d'export requièrent une authentification."""
    for endpoint in [
        "/export/books",
        "/export/students_reads",
        "/export/active_loans",
        "/export/all_loans",
    ]:
        resp = client.get(endpoint, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


def test_export_requires_premium(client, app):
    """Vérifie que les utilisateurs gratuits sont bloqués par @premium_required et redirigés vers /tarifs."""
    with app.app_context():
        user = User(id=1, email="free_teacher@test.com", password="hash", plan="free")
        db.session.add(user)
        db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = "1"

    for endpoint in [
        "/export/books",
        "/export/students_reads",
        "/export/active_loans",
        "/export/all_loans",
    ]:
        resp = client.get(endpoint, follow_redirects=False)
        assert resp.status_code == 302
        assert "/tarifs" in resp.headers.get("Location", "")


def test_export_empty_library_generates_valid_excel(client, app):
    """Cas limite : une bibliothèque complètement vide (0 livre, 0 élève, 0 prêt) génère un fichier .xlsx intègre."""
    with app.app_context():
        user = User(
            id=2,
            email="empty_library@test.com",
            password="hash",
            plan="premium",
            stripe_subscription_status="active",
        )
        db.session.add(user)
        db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = "2"

    for endpoint in [
        "/fr/export/books",
        "/fr/export/students_reads",
        "/fr/export/active_loans",
        "/fr/export/all_loans",
    ]:
        resp = client.get(endpoint)
        assert resp.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            in resp.content_type
        )
        # Vérification de l'intégrité du classeur Excel
        wb = openpyxl.load_workbook(BytesIO(resp.data))
        assert len(wb.sheetnames) >= 1


def test_export_with_data_and_unicode(client, app):
    """Vérifie le contenu structuré des 4 fichiers Excel avec accents, prêts en cours et retours archivés."""
    with app.app_context():
        user = User(
            id=3,
            email="active_teacher@test.com",
            password="hash",
            plan="premium",
            stripe_subscription_status="active",
        )
        db.session.add(user)
        db.session.commit()

        # Livres avec caractères accentués et spéciaux
        book1 = Book(
            id=1,
            title="L'Odyssée d'Homère & Chants",
            author="Homère",
            editor="Hachette",
            year=2020,
            type="Classique",
            isbn="9782010000001",
            user_id=3,
        )
        book2 = Book(
            id=2,
            title="Le Petit Prince",
            author="Antoine de Saint-Exupéry",
            editor="Gallimard",
            year=1943,
            type="Conte",
            isbn="9782070612758",
            user_id=3,
        )
        student1 = Student(id=1, name="François", firstname="Zoé", user_id=3)
        student2 = Student(id=2, name="Éléonore", firstname="Léo", user_id=3)
        db.session.add_all([book1, book2, student1, student2])
        db.session.commit()

        # Prêt 1 : en cours (pas de date de retour)
        loan1 = Loan(
            id=1,
            book_id=1,
            student_id=1,
            date_loan=datetime.now(UTC).date(),
            date_return=None,
        )
        # Prêt 2 : terminé (avec date de retour)
        loan2 = Loan(
            id=2,
            book_id=2,
            student_id=2,
            date_loan=datetime.now(UTC).date(),
            date_return=datetime.now(UTC).date(),
        )
        db.session.add_all([loan1, loan2])
        db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = "3"

    # 1. Export des livres
    resp_books = client.get("/fr/export/books")
    assert resp_books.status_code == 200
    wb_books = openpyxl.load_workbook(BytesIO(resp_books.data))
    ws_books = wb_books["Livres"]
    assert ws_books.max_row == 3  # Entête + 2 livres
    assert ws_books.cell(row=2, column=1).value in [
        "L'Odyssée d'Homère & Chants",
        "Le Petit Prince",
    ]

    # 2. Export des lectures des élèves
    resp_reads = client.get("/fr/export/students_reads")
    assert resp_reads.status_code == 200
    wb_reads = openpyxl.load_workbook(BytesIO(resp_reads.data))
    ws_reads = wb_reads["Lectures des élèves"]
    assert ws_reads.max_row == 3  # Entête + 2 prêts

    # 3. Export des prêts en cours uniquement
    resp_active = client.get("/fr/export/active_loans")
    assert resp_active.status_code == 200
    wb_active = openpyxl.load_workbook(BytesIO(resp_active.data))
    ws_active = wb_active["Prêts en cours"]
    assert ws_active.max_row == 2  # Entête + 1 seul prêt actif

    # 4. Export de tous les prêts (avec colonne Statut)
    resp_all = client.get("/fr/export/all_loans")
    assert resp_all.status_code == 200
    wb_all = openpyxl.load_workbook(BytesIO(resp_all.data))
    ws_all = wb_all["Tous les prêts"]
    assert ws_all.max_row == 3  # Entête + 2 prêts
