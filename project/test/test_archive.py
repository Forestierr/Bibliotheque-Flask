from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from project import create_app, db
from project.config_plans import MAX_FREE_STUDENTS
from project.models import AcademicYearArchive, Book, Loan, Student, User
from project.query import get_students, get_students_count


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_user(app):
    user = User(
        id=1,
        email="teacher_archive@test.com",
        password="hash",
        name="Mme Forestier",
        plan="free",
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def client(app, test_user):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = str(test_user.id)
        sess["_fresh"] = True
    return c


def test_wizard_step1_blocked_if_active_loans_remain(app, client, test_user):
    with app.app_context():
        book = Book(title="Le Petit Prince", user_id=test_user.id)
        student = Student(name="Dupont", firstname="Léa", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        # Un emprunt non rendu
        loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=datetime.now(UTC).date() - timedelta(days=5),
            date_return=None,
        )
        db.session.add(loan)
        db.session.commit()

    # Accès à l'étape 2 alors qu'un encours existe sans arbitrage -> redirection vers l'étape 1
    response = client.get("/archive/wizard?step=2", follow_redirects=True)
    assert response.status_code == 200
    assert "Des livres sont encore empruntés" in response.get_data(as_text=True)
    assert "Le Petit Prince" in response.get_data(as_text=True)


def test_wizard_check_loans_actions(app, client, test_user):
    with app.app_context():
        book1 = Book(title="Livre A", user_id=test_user.id)
        book2 = Book(title="Livre B", user_id=test_user.id)
        student = Student(name="Martin", firstname="Hugo", user_id=test_user.id)
        db.session.add_all([book1, book2, student])
        db.session.commit()

        loan1 = Loan(
            book_id=book1.id,
            student_id=student.id,
            date_loan=datetime.now(UTC).date() - timedelta(days=10),
        )
        loan2 = Loan(
            book_id=book2.id,
            student_id=student.id,
            date_loan=datetime.now(UTC).date() - timedelta(days=12),
        )
        db.session.add_all([loan1, loan2])
        db.session.commit()
        loan1_id = loan1.id
        loan2_id = loan2.id

    # 1. Rendre le livre 1
    res1 = client.post(
        "/archive/wizard/check-loans",
        data={"loan_id": loan1_id, "action": "return"},
        follow_redirects=True,
    )
    assert res1.status_code == 200

    with app.app_context():
        l1 = db.session.get(Loan, loan1_id)
        assert l1.date_return is not None
        assert l1.notes is None

    # 2. Déclarer perdu le livre 2
    res2 = client.post(
        "/archive/wizard/check-loans",
        data={"loan_id": loan2_id, "action": "lost"},
        follow_redirects=True,
    )
    assert res2.status_code == 200

    with app.app_context():
        l2 = db.session.get(Loan, loan2_id)
        assert l2.date_return is not None
        assert l2.notes == "perdu"


def test_wizard_commit_full_flow_and_statistics(app, client, test_user):
    with app.app_context():
        # Création de 4 élèves et 3 livres
        s1 = Student(name="Alain", firstname="Arthur", user_id=test_user.id)
        s2 = Student(name="Benoit", firstname="Béatrice", user_id=test_user.id)
        s3 = Student(
            name="Caron", firstname="Chloé", user_id=test_user.id
        )  # restera en CE2 (cours double)
        s4 = Student(
            name="Durand", firstname="David", user_id=test_user.id
        )  # restera en CE2

        b1 = Book(title="Harry Potter 1", author="J.K. Rowling", user_id=test_user.id)
        b2 = Book(title="Tintin au Tibet", author="Hergé", user_id=test_user.id)
        b3 = Book(title="Astérix le Gaulois", author="Goscinny", user_id=test_user.id)

        db.session.add_all([s1, s2, s3, s4, b1, b2, b3])
        db.session.commit()

        # Arthur (s1) lit 3 livres (Harry Potter x2, Tintin x1)
        l1 = Loan(
            book_id=b1.id,
            student_id=s1.id,
            date_loan=date(2025, 10, 1),
            date_return=date(2025, 10, 15),
        )
        l2 = Loan(
            book_id=b1.id,
            student_id=s1.id,
            date_loan=date(2025, 11, 1),
            date_return=date(2025, 11, 15),
        )
        l3 = Loan(
            book_id=b2.id,
            student_id=s1.id,
            date_loan=date(2025, 12, 1),
            date_return=date(2025, 12, 15),
        )

        # Béatrice (s2) lit 2 livres (Tintin x1, Astérix x1)
        l4 = Loan(
            book_id=b2.id,
            student_id=s2.id,
            date_loan=date(2026, 1, 10),
            date_return=date(2026, 1, 20),
        )
        l5 = Loan(
            book_id=b3.id,
            student_id=s2.id,
            date_loan=date(2026, 2, 5),
            date_return=date(2026, 2, 15),
        )

        # Chloé (s3) lit 1 livre (Astérix x1)
        l6 = Loan(
            book_id=b3.id,
            student_id=s3.id,
            date_loan=date(2026, 3, 1),
            date_return=date(2026, 3, 10),
        )

        db.session.add_all([l1, l2, l3, l4, l5, l6])
        db.session.commit()

        s1_id, s2_id, s3_id, s4_id = s1.id, s2.id, s3.id, s4.id

    # Clôture : Arthur (s1) et Béatrice (s2) quittent la classe. Chloé (s3) et David (s4) restent.
    response = client.post(
        "/archive/wizard/commit",
        data={
            "year_label": "2025-2026",
            "start_date": "2025-09-01",
            "end_date": "2026-07-05",
            "confirmation": "ARCHIVER",
            "archived_students": [str(s1_id), str(s2_id)],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "clôturée avec succès" in html or "Bilan Promotion 2025-2026" in html

    with app.app_context():
        # Vérification de l'archive créée
        archive = AcademicYearArchive.query.filter_by(
            user_id=test_user.id, year_label="2025-2026"
        ).first()
        assert archive is not None
        assert archive.total_students == 4  # effectif total de la promo avant clôture
        assert archive.total_loans == 6
        assert archive.average_loans_per_student == 1.5

        # Champion livres : Harry Potter (2) ou Tintin (2) ou Astérix (2)
        assert archive.most_read_book_count == 2
        # Champion lecteur : Arthur (3 prêts)
        assert "Arthur Alain" in archive.top_reader_name
        assert archive.top_reader_count == 3

        # Vérification du soft-delete
        arthur = db.session.get(Student, s1_id)
        beatrice = db.session.get(Student, s2_id)
        chloe = db.session.get(Student, s3_id)
        david = db.session.get(Student, s4_id)

        assert arthur.is_archived is True
        assert arthur.archived_year_id == archive.id
        assert arthur.archived_at is not None

        assert beatrice.is_archived is True
        assert beatrice.archived_year_id == archive.id

        # Élèves de cours double conservés
        assert chloe.is_archived is False
        assert chloe.archived_year_id is None
        assert david.is_archived is False
        assert david.archived_year_id is None

        # Quota réinitialisé : seuls les 2 élèves actifs sont comptabilisés
        assert get_students_count(test_user.id) == 2
        active_list = get_students(test_user.id)
        assert len(active_list) == 2
        assert {s.id for s in active_list} == {s3_id, s4_id}


def test_freemium_quota_reset_allows_adding_students(app, client, test_user):
    with app.app_context():
        # Création de 40 élèves (quota gratuit max atteint)
        students = [
            Student(name=f"Nom{i}", firstname=f"Prenom{i}", user_id=test_user.id)
            for i in range(MAX_FREE_STUDENTS)
        ]
        db.session.add_all(students)
        db.session.commit()
        assert get_students_count(test_user.id) == MAX_FREE_STUDENTS

    # Tentative d'ajout avant archivage -> bloquée par le quota
    res_blocked = client.post(
        "/eleve/ajout",
        data={"name": "Nouveau", "firstname": "Eleve"},
        follow_redirects=True,
    )
    assert "Vous avez atteint la limite" in res_blocked.get_data(as_text=True)

    with app.app_context():
        all_ids = [s.id for s in Student.query.filter_by(user_id=test_user.id).all()]

    # Clôture d'année : on archive 35 élèves, 5 restent
    to_archive = [str(sid) for sid in all_ids[:35]]
    client.post(
        "/archive/wizard/commit",
        data={
            "year_label": "2024-2025",
            "start_date": "2024-09-01",
            "end_date": "2025-07-05",
            "confirmation": "ARCHIVER",
            "archived_students": to_archive,
        },
        follow_redirects=True,
    )

    with app.app_context():
        assert get_students_count(test_user.id) == 5

    # Après archivage, l'enseignant peut immédiatement ajouter de nouveaux élèves
    res_ok = client.post(
        "/eleve/ajout",
        data={"name": "Nouveau", "firstname": "Eleve"},
        follow_redirects=True,
    )
    assert res_ok.status_code == 200

    with app.app_context():
        assert get_students_count(test_user.id) == 6


def test_book_loans_preserved_after_student_archived(app, client, test_user):
    with app.app_context():
        book = Book(title="Le Petit Prince", user_id=test_user.id)
        student = Student(name="Dupont", firstname="Alice", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        # Un prêt rendu
        loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=date(2025, 9, 10),
            date_return=date(2025, 9, 20),
        )
        db.session.add(loan)
        db.session.commit()

        student_id = student.id
        book_id = book.id

    # Archivage de l'élève
    client.post(
        "/archive/wizard/commit",
        data={
            "year_label": "2025-2026",
            "start_date": "2025-09-01",
            "end_date": "2026-07-05",
            "confirmation": "ARCHIVER",
            "archived_students": [str(student_id)],
        },
        follow_redirects=True,
    )

    # La fiche du livre affiche toujours le prêt passé
    res_book = client.get(f"/livre/{book_id}")
    assert res_book.status_code == 200
    html = res_book.get_data(as_text=True)
    assert "Prêté 1 fois" in html or "1 fois" in html

    # La fiche de l'élève archivé affiche le badge d'archive
    res_student = client.get(f"/eleve/{student_id}")
    assert res_student.status_code == 200
    html_student = res_student.get_data(as_text=True)
    assert "Archivé" in html_student
    assert "Promo 2025-2026" in html_student
    assert "Le Petit Prince" in html_student


def test_cannot_archive_student_with_unreturned_loan(app, client, test_user):
    with app.app_context():
        book = Book(title="Livre Non Rendu", user_id=test_user.id)
        student = Student(name="Rebelle", firstname="Max", user_id=test_user.id)
        db.session.add_all([book, student])
        db.session.commit()

        loan = Loan(
            book_id=book.id,
            student_id=student.id,
            date_loan=date(2026, 5, 1),
            date_return=None,
        )
        db.session.add(loan)
        db.session.commit()
        sid = student.id

    # Tentative d'archivage avec confirmation ARCHIVER
    res = client.post(
        "/archive/wizard/commit",
        data={
            "year_label": "2025-2026",
            "start_date": "2025-09-01",
            "end_date": "2026-07-05",
            "confirmation": "ARCHIVER",
            "archived_students": [str(sid)],
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert (
        "Impossible d&#39;archiver les élèves suivants car ils ont encore des livres empruntés"
        in res.get_data(as_text=True)
        or "empruntés" in res.get_data(as_text=True)
    )

    with app.app_context():
        assert db.session.get(Student, sid).is_archived is False


def test_archive_delete_restores_students(app, client, test_user):
    with app.app_context():
        student = Student(name="Durand", firstname="Léo", user_id=test_user.id)
        db.session.add(student)
        db.session.commit()
        sid = student.id

    # Clôture
    client.post(
        "/archive/wizard/commit",
        data={
            "year_label": "2025-2026",
            "start_date": "2025-09-01",
            "end_date": "2026-07-05",
            "confirmation": "ARCHIVER",
            "archived_students": [str(sid)],
        },
        follow_redirects=True,
    )

    with app.app_context():
        archive = AcademicYearArchive.query.filter_by(user_id=test_user.id).first()
        assert archive is not None
        arch_id = archive.id
        assert db.session.get(Student, sid).is_archived is True

    # Suppression de l'archive de secours
    res_del = client.post(f"/archive/{arch_id}/delete", follow_redirects=True)
    assert res_del.status_code == 200

    with app.app_context():
        assert db.session.get(AcademicYearArchive, arch_id) is None
        student_restored = db.session.get(Student, sid)
        assert student_restored.is_archived is False
        assert student_restored.archived_year_id is None
        assert student_restored.archived_at is None


def test_print_and_excel_require_premium(app, client, test_user):
    with app.app_context():
        archive = AcademicYearArchive(
            user_id=test_user.id,
            year_label="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 5),
            archived_at=datetime.now(UTC),
            total_students=10,
            total_loans=50,
        )
        db.session.add(archive)
        db.session.commit()
        arch_id = archive.id

    # 1. Utilisateur Gratuit -> redirection vers les tarifs
    res_print = client.get(f"/archive/{arch_id}/print")
    assert res_print.status_code == 302
    assert "/tarifs" in res_print.location

    res_excel = client.get(f"/archive/{arch_id}/export-excel")
    assert res_excel.status_code == 302
    assert "/tarifs" in res_excel.location

    # 2. Utilisateur Premium -> accès autorisé
    mock_prem = MagicMock()
    mock_prem.id = test_user.id
    mock_prem.name = test_user.name
    mock_prem.email = test_user.email
    mock_prem.plan = "premium"
    mock_prem.is_authenticated = True
    mock_prem.is_premium = True
    mock_prem.preferred_language = "fr"

    with patch("flask_login.utils._get_user", return_value=mock_prem):
        res_print_prem = client.get(f"/archive/{arch_id}/print", follow_redirects=True)
        assert res_print_prem.status_code == 200
        assert "Bilan Officiel de Lecture" in res_print_prem.get_data(as_text=True)

        res_excel_prem = client.get(
            f"/archive/{arch_id}/export-excel", follow_redirects=True
        )
        assert res_excel_prem.status_code == 200
        assert (
            res_excel_prem.headers.get("Content-Type")
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
