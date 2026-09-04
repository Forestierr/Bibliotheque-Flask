import pytest
from werkzeug.security import generate_password_hash

from project import create_app, db
from project.models import Feedback, User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key-feedback",
            "MAIL_USERNAME": "admin@livresenclasse.com",
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
def sample_user(app):
    with app.app_context():
        user = User(
            email="enseignant@ecole.fr",
            name="Jean Rostand",
            password=generate_password_hash("password123"),
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_feedback_requires_login(client):
    # GET sans session -> redirection vers login
    res_get = client.get("/feedback")
    assert res_get.status_code == 302
    assert "/login" in res_get.headers["Location"]

    # POST sans session -> redirection vers login
    res_post = client.post(
        "/feedback",
        data={"category": "bug", "subject": "Test", "message": "Test message"},
    )
    assert res_post.status_code == 302
    assert "/login" in res_post.headers["Location"]


def test_feedback_get_authenticated(client, sample_user):
    login(client, sample_user)
    res = client.get("/feedback")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Donner votre avis" in html
    assert "enseignant@ecole.fr" in html


def test_feedback_post_success(app, client, sample_user):
    login(client, sample_user)
    res = client.post(
        "/feedback",
        data={
            "category": "bug",
            "subject": "Problème affichage scanner",
            "message": "Le bouton de scan ne réagit pas sur tablette.",
            "page_url": "/livre",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Votre retour a été transmis avec succès" in res.get_data(as_text=True)

    with app.app_context():
        fb = Feedback.query.filter_by(subject="Problème affichage scanner").first()
        assert fb is not None
        assert fb.user_id == sample_user
        assert fb.category == "bug"
        assert fb.page_url == "/livre"
        assert fb.status == "nouveau"
        assert "Le bouton de scan" in fb.message


def test_feedback_post_validation(app, client, sample_user):
    login(client, sample_user)
    # Sujet vide
    res = client.post(
        "/feedback",
        data={
            "category": "suggestion",
            "subject": "",
            "message": "Une suggestion sans sujet.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Veuillez renseigner" in res.get_data(as_text=True)

    with app.app_context():
        assert Feedback.query.count() == 0


def test_admin_feedbacks_management(app, client, sample_user):
    # Créer deux retours en base
    with app.app_context():
        fb1 = Feedback(
            user_id=sample_user,
            category="suggestion",
            subject="Ajout filtre par auteur",
            message="Serait-il possible de filtrer les livres par auteur ?",
            status="nouveau",
        )
        fb2 = Feedback(
            user_id=sample_user,
            category="bug",
            subject="Erreur 500 sur export",
            message="L'export CSV plante quand il y a plus de 50 élèves.",
            status="nouveau",
        )
        db.session.add_all([fb1, fb2])
        db.session.commit()
        fb1_id = fb1.id
        fb2_id = fb2.id

    # Consultation de la liste dans l'administration
    res = client.get("/admin/feedbacks")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Ajout filtre par auteur" in html
    assert "Erreur 500 sur export" in html

    # Filtrer par statut ou catégorie
    res_bug = client.get("/admin/feedbacks?category=bug")
    assert res_bug.status_code == 200
    html_bug = res_bug.get_data(as_text=True)
    assert "Erreur 500 sur export" in html_bug
    assert "Ajout filtre par auteur" not in html_bug

    # Mise à jour de statut (nouveau -> en_cours)
    res_update = client.post(
        f"/admin/feedback/{fb1_id}/status",
        data={"status": "en_cours"},
        follow_redirects=True,
    )
    assert res_update.status_code == 200

    with app.app_context():
        fb1_updated = db.session.get(Feedback, fb1_id)
        assert fb1_updated.status == "en_cours"

    # Suppression d'un feedback
    res_del = client.post(f"/admin/feedback/{fb2_id}/delete", follow_redirects=True)
    assert res_del.status_code == 200

    with app.app_context():
        assert db.session.get(Feedback, fb2_id) is None
        assert db.session.get(Feedback, fb1_id) is not None
