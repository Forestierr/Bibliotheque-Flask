import pytest

from project import create_app, db
from project.models import User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
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
            email="prof@ecole.fr",
            name="Professeur Tournesol",
            password="fake-hashed-password",
            is_verified=True,
            newsletter_subscribed=True,
        )
        db.session.add(user)
        db.session.commit()
        # Refresh to keep in session or detached with ID
        user_id = user.id
        return user_id


def test_unsubscribe_tokens(app, sample_user):
    with app.app_context():
        user = db.session.get(User, sample_user)
        token = user.get_unsubscribe_token()
        assert token is not None
        assert isinstance(token, str)

        # Validate with correct token
        validated = User.validate_unsubscribe_token(token, user.id)
        assert validated is not None
        assert validated.id == user.id

        # Validate with wrong token
        assert User.validate_unsubscribe_token("invalid-token", user.id) is None

        # Validate with wrong user_id
        assert User.validate_unsubscribe_token(token, 99999) is None


def test_unsubscribe_flow(client, app, sample_user):
    with app.app_context():
        user = db.session.get(User, sample_user)
        token = user.get_unsubscribe_token()
        uid = user.id

    # 1. GET confirms intent
    res = client.get(f"/unsubscribe/{token}/{uid}")
    assert res.status_code == 200
    assert (
        b"Confirmer votre d\xc3\xa9sabonnement" in res.data or b"Confirmer" in res.data
    )
    assert b"prof@ecole.fr" in res.data

    # 2. POST executes unsubscription
    res = client.post(f"/unsubscribe/{token}/{uid}")
    assert res.status_code == 200
    assert (
        "Vous êtes désabonné".encode() in res.data
        or "d\xc3\xa9sabonn\xc3\xa9".encode() in res.data
    )

    # Check database state
    with app.app_context():
        user_db = db.session.get(User, uid)
        assert user_db.newsletter_subscribed is False

    # 3. GET when already unsubscribed
    res = client.get(f"/unsubscribe/{token}/{uid}")
    assert res.status_code == 200
    assert (
        "Déjà désabonné".encode() in res.data
        or "d\xc3\xa9j\xc3\xa0".encode() in res.data
    )

    # 4. POST resubscribe
    res = client.post(f"/resubscribe/{token}/{uid}")
    assert res.status_code == 200
    assert (
        "R\xc3\xa9abonnement confirm\xc3\xa9".encode() in res.data
        or "confirmé".encode() in res.data
    )

    with app.app_context():
        user_db = db.session.get(User, uid)
        assert user_db.newsletter_subscribed is True


def test_unsubscribe_invalid_token(client):
    res = client.get("/unsubscribe/fake-token/12345")
    assert res.status_code == 200
    assert "Lien invalide ou expiré".encode() in res.data or b"invalide" in res.data


def test_reglage_newsletter_preference(client, app, sample_user):
    with app.app_context():
        user = db.session.get(User, sample_user)
        uid = user.id

    # Simulate logged-in user
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True

    # 1. Uncheck newsletter
    res = client.post(
        "/reglage",
        data={
            "name": "Professeur Tournesol",
            "email": "prof@ecole.fr",
            # newsletter_subscribed omitted -> False
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    with app.app_context():
        user_db = db.session.get(User, uid)
        assert user_db.newsletter_subscribed is False

    # 2. Check newsletter
    res = client.post(
        "/reglage",
        data={
            "name": "Professeur Tournesol",
            "email": "prof@ecole.fr",
            "newsletter_subscribed": "1",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    with app.app_context():
        user_db = db.session.get(User, uid)
        assert user_db.newsletter_subscribed is True


def test_admin_emails_preview(client, app, sample_user):
    res = client.post(
        "/admin/emails",
        data={
            "subject": "Test Sujet Newsletter",
            "target": "verified_subscribed",
            "template_choice": "newsletter.html",
            "message": "<p>Bienvenue sur notre newsletter de test !</p>",
            "action": "preview",
        },
    )
    assert res.status_code == 200
    assert b"Test Sujet Newsletter" in res.data
    assert b"Bienvenue sur notre newsletter de test !" in res.data
    assert b"/unsubscribe/" in res.data


def test_admin_emails_filtering(app):
    with app.app_context():
        # User 1: verified + subscribed
        u1 = User(email="u1@test.com", is_verified=True, newsletter_subscribed=True)
        # User 2: unverified + subscribed
        u2 = User(email="u2@test.com", is_verified=False, newsletter_subscribed=True)
        # User 3: verified + unsubscribed
        u3 = User(email="u3@test.com", is_verified=True, newsletter_subscribed=False)
        db.session.add_all([u1, u2, u3])
        db.session.commit()

        # Test verified_subscribed target
        recipients_verif_sub = User.query.filter_by(
            is_verified=True, newsletter_subscribed=True
        ).all()
        emails_verif = [u.email for u in recipients_verif_sub]
        assert "u1@test.com" in emails_verif
        assert "u2@test.com" not in emails_verif
        assert "u3@test.com" not in emails_verif

        # Test all_subscribed target
        recipients_all_sub = User.query.filter_by(newsletter_subscribed=True).all()
        emails_all = [u.email for u in recipients_all_sub]
        assert "u1@test.com" in emails_all
        assert "u2@test.com" in emails_all
        assert "u3@test.com" not in emails_all
