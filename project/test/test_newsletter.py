from unittest.mock import patch

import pytest

from project import create_app, db
from project.admin import send_newsletter_async
from project.models import NewsletterCampaign, NewsletterDelivery, User


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


@patch("project.admin.mail.send")
@patch("project.admin.time.sleep")
def test_send_newsletter_async(mock_sleep, mock_send, app):
    with app.app_context():
        campaign = NewsletterCampaign(
            subject="Info rentrée",
            content="<p>Bienvenue</p>",
            template="newsletter.html",
            target="verified_subscribed",
            total_recipients=1,
        )
        db.session.add(campaign)
        db.session.flush()

        delivery = NewsletterDelivery(
            campaign_id=campaign.id,
            email="test@example.com",
            tracking_token="token123",
            status="pending",
        )
        db.session.add(delivery)
        db.session.commit()

        recipient_data = [
            {
                "id": 1,
                "delivery_id": delivery.id,
                "email": "test@example.com",
                "name": "Jean Test",
                "unsubscribe_url": "http://localhost/unsubscribe/token/1",
                "tracking_pixel_url": "http://localhost/email/track/token123.png",
            }
        ]
        send_newsletter_async(
            app,
            campaign.id,
            subject="Info rentrée",
            sender="admin@livresenclasse.com",
            template_path="email/newsletter.html",
            message_content="<p>Bienvenue</p>",
            recipient_data=recipient_data,
            feedback_idea_url="http://localhost/feedback?type=idea",
            feedback_bug_url="http://localhost/feedback?type=bug",
            reglage_url="http://localhost/reglage",
        )
        assert mock_send.called
        sent_msg = mock_send.call_args[0][0]
        assert sent_msg.subject == "Info rentrée"
        assert sent_msg.recipients == ["test@example.com"]
        assert "http://localhost/unsubscribe/token/1" in sent_msg.html
        assert "http://localhost/feedback?type=idea" in sent_msg.html
        assert "http://localhost/feedback?type=bug" in sent_msg.html
        assert "http://localhost/reglage" in sent_msg.html
        assert "http://localhost/email/track/token123.png" in sent_msg.html

        # Check DB state
        db.session.expire_all()
        delivery_db = db.session.get(NewsletterDelivery, delivery.id)
        assert delivery_db.status == "sent"
        assert delivery_db.sent_at is not None

        campaign_db = db.session.get(NewsletterCampaign, campaign.id)
        assert campaign_db.sent_count == 1


@patch("project.admin.Thread")
def test_admin_emails_send_flow(mock_thread, client, app, sample_user):
    res = client.post(
        "/admin/emails",
        data={
            "subject": "Nouvelle mise à jour",
            "target": "verified_subscribed",
            "template_choice": "newsletter.html",
            "message": "<p>Voici les nouveautés !</p>",
            "action": "send",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert mock_thread.called
    args = mock_thread.call_args[1]["args"]
    # args: [app, campaign.id, subject, sender, template_path, message_content, recipient_data, ...]
    assert args[2] == "Nouvelle mise à jour"
    assert len(args[6]) == 1
    assert args[6][0]["email"] == "prof@ecole.fr"
    assert "/unsubscribe/" in args[6][0]["unsubscribe_url"]
    assert "/email/track/" in args[6][0]["tracking_pixel_url"]
    assert "/feedback?type=idea" in args[7]
    assert "/feedback?type=bug" in args[8]
    assert "/reglage" in args[9]

    # Verify campaign was saved in database
    with app.app_context():
        campaign = NewsletterCampaign.query.filter_by(
            subject="Nouvelle mise à jour"
        ).first()
        assert campaign is not None
        assert campaign.total_recipients == 1
        assert len(campaign.deliveries) == 1
        assert campaign.deliveries[0].email == "prof@ecole.fr"


def test_email_tracking_pixel(client, app):
    with app.app_context():
        campaign = NewsletterCampaign(
            subject="Test Tracking",
            content="<p>Test</p>",
            template="newsletter.html",
            target="all",
            total_recipients=1,
            sent_count=1,
        )
        db.session.add(campaign)
        db.session.flush()

        delivery = NewsletterDelivery(
            campaign_id=campaign.id,
            email="prof@test.com",
            tracking_token="unique-test-token-12345",
            status="sent",
        )
        db.session.add(delivery)
        db.session.commit()
        delivery_id = delivery.id
        campaign_id = campaign.id

    # 1. First request to tracking pixel
    res = client.get("/email/track/unique-test-token-12345.png")
    assert res.status_code == 200
    assert res.content_type == "image/png"
    assert "no-cache" in res.headers.get("Cache-Control", "")

    with app.app_context():
        d1 = db.session.get(NewsletterDelivery, delivery_id)
        c1 = db.session.get(NewsletterCampaign, campaign_id)
        assert d1.opened_at is not None
        assert d1.open_count == 1
        assert c1.open_count == 1
        assert c1.open_rate == 100.0

    # 2. Second request (same user re-opens)
    res2 = client.get("/email/track/unique-test-token-12345.png")
    assert res2.status_code == 200

    with app.app_context():
        d2 = db.session.get(NewsletterDelivery, delivery_id)
        c2 = db.session.get(NewsletterCampaign, campaign_id)
        assert d2.open_count == 2
        assert c2.open_count == 1  # Unique open count remains 1!


def test_campaign_details_api_and_deletion(client, app):
    with app.app_context():
        campaign = NewsletterCampaign(
            subject="Campagne API",
            content="<p>Corps de test</p>",
            template="newsletter_update.html",
            target="verified",
            total_recipients=1,
            sent_count=1,
            open_count=1,
        )
        db.session.add(campaign)
        db.session.flush()

        delivery = NewsletterDelivery(
            campaign_id=campaign.id,
            email="dest@test.com",
            tracking_token="token-api-test",
            status="sent",
        )
        db.session.add(delivery)
        db.session.commit()
        cid = campaign.id

    # Test GET details API
    res = client.get(f"/admin/campaigns/{cid}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["subject"] == "Campagne API"
    assert data["template"] == "newsletter_update.html"
    assert len(data["deliveries"]) == 1
    assert data["deliveries"][0]["email"] == "dest@test.com"

    # Test POST delete
    res_del = client.post(
        f"/admin/campaigns/{cid}/delete",
        follow_redirects=True,
    )
    assert res_del.status_code == 200

    with app.app_context():
        assert db.session.get(NewsletterCampaign, cid) is None
        assert NewsletterDelivery.query.filter_by(campaign_id=cid).first() is None
