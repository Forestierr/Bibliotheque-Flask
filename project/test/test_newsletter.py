from unittest.mock import patch

import pytest

from project import create_app, db
from project.admin import get_user_pseudo, replace_pseudo, send_newsletter_async
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


def test_replace_pseudo_and_get_user_pseudo():
    # 1. get_user_pseudo with dict
    assert get_user_pseudo({"name": "Alice", "email": "alice@ecole.fr"}) == "Alice"
    assert get_user_pseudo({"name": "  Bob  ", "email": "bob@ecole.fr"}) == "Bob"
    assert get_user_pseudo({"name": "", "email": "charlie@ecole.fr"}) == "charlie"
    assert get_user_pseudo({"name": None, "email": "dave@ecole.fr"}) == "dave"
    assert get_user_pseudo({"name": None, "email": "invalid"}) == "Enseignant"
    assert get_user_pseudo({"name": None, "email": ""}) == "Enseignant"
    assert (
        get_user_pseudo({"name": None, "email": ""}, fallback="Professeur")
        == "Professeur"
    )

    # 2. replace_pseudo basics & synonyms
    text = "Bonjour [pseudo], bienvenue {PSEUDO} ! Salut [nom], {NOM}, [name], {NAME}."
    replaced = replace_pseudo(text, "Élodie")
    assert (
        replaced
        == "Bonjour Élodie, bienvenue Élodie ! Salut Élodie, Élodie, Élodie, Élodie."
    )

    # 3. HTML escaping
    xss_pseudo = "<script>alert('xss')</script>"
    safe_html = replace_pseudo("Bonjour [pseudo] !", xss_pseudo, is_html=True)
    assert "<script>" not in safe_html
    assert "&lt;script&gt;" in safe_html

    # Raw text (not html) should preserve characters
    raw_text = replace_pseudo("Bonjour [pseudo] !", xss_pseudo, is_html=False)
    assert raw_text == f"Bonjour {xss_pseudo} !"

    # Empty text handling
    assert replace_pseudo("", "Élodie") == ""
    assert replace_pseudo(None, "Élodie") is None


@patch("project.admin.Thread")
def test_admin_emails_language_filtering(mock_thread, client, app):
    with app.app_context():
        u_fr = User(
            email="fr_user@ecole.fr",
            name="Prof FR",
            is_verified=True,
            newsletter_subscribed=True,
            preferred_language="fr",
        )
        u_en = User(
            email="en_user@school.uk",
            name="Teacher EN",
            is_verified=True,
            newsletter_subscribed=True,
            preferred_language="en",
        )
        u_de = User(
            email="de_user@schule.de",
            name="Lehrer DE",
            is_verified=True,
            newsletter_subscribed=True,
            preferred_language="de",
        )
        db.session.add_all([u_fr, u_en, u_de])
        db.session.commit()

    # 1. Send targeted to EN only
    res_en = client.post(
        "/admin/emails",
        data={
            "subject": "Hello [pseudo]",
            "target": "verified_subscribed",
            "target_lang": "en",
            "template_choice": "newsletter.html",
            "message": "<p>English content for [pseudo]</p>",
            "action": "send",
        },
        follow_redirects=True,
    )
    assert res_en.status_code == 200
    assert mock_thread.called
    args_en = mock_thread.call_args[1]["args"]
    recipients_en = args_en[6]
    assert len(recipients_en) == 1
    assert recipients_en[0]["email"] == "en_user@school.uk"
    assert recipients_en[0]["lang"] == "en"

    # Verify campaign record has target_lang="en"
    with app.app_context():
        camp_en = NewsletterCampaign.query.filter_by(subject="Hello [pseudo]").first()
        assert camp_en is not None
        assert camp_en.target_lang == "en"

    # 2. Send targeted to DE only
    mock_thread.reset_mock()
    res_de = client.post(
        "/admin/emails",
        data={
            "subject": "Hallo [pseudo]",
            "target": "verified_subscribed",
            "target_lang": "de",
            "template_choice": "newsletter.html",
            "message": "<p>Deutscher Inhalt für [pseudo]</p>",
            "action": "send",
        },
        follow_redirects=True,
    )
    assert res_de.status_code == 200
    assert mock_thread.called
    args_de = mock_thread.call_args[1]["args"]
    recipients_de = args_de[6]
    assert len(recipients_de) == 1
    assert recipients_de[0]["email"] == "de_user@schule.de"
    assert recipients_de[0]["lang"] == "de"

    # 3. Send targeted to ALL languages
    mock_thread.reset_mock()
    res_all = client.post(
        "/admin/emails",
        data={
            "subject": "Global Update",
            "target": "verified_subscribed",
            "target_lang": "all",
            "template_choice": "newsletter.html",
            "message": "<p>Global message</p>",
            "action": "send",
        },
        follow_redirects=True,
    )
    assert res_all.status_code == 200
    assert mock_thread.called
    args_all = mock_thread.call_args[1]["args"]
    recipients_all = args_all[6]
    assert len(recipients_all) == 3
    emails_sent = {r["email"] for r in recipients_all}
    assert emails_sent == {
        "fr_user@ecole.fr",
        "en_user@school.uk",
        "de_user@schule.de",
    }


def test_admin_emails_duplicate_prefill(client, app):
    with app.app_context():
        campaign = NewsletterCampaign(
            subject="Lettre de rentrée",
            content="<p>Bienvenue pour cette nouvelle année !</p>",
            template="newsletter_promo.html",
            target="all_subscribed",
            target_lang="fr",
            total_recipients=10,
        )
        db.session.add(campaign)
        db.session.commit()
        cid = campaign.id

    # Duplicate with language prefill 'de'
    res = client.get(f"/admin/emails?duplicate_id={cid}&target_lang=de")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Lettre de rentrée" in html
    assert "Bienvenue pour cette nouvelle année !" in html
    assert 'value="newsletter_promo.html"' in html
    assert 'value="all_subscribed" selected' in html
    assert 'value="de" selected' in html


@patch("project.admin.mail.send")
@patch("project.admin.time.sleep")
def test_send_newsletter_async_pseudo_and_force_locale(mock_sleep, mock_send, app):
    with app.app_context():
        campaign = NewsletterCampaign(
            subject="Welcome [pseudo]!",
            content="<p>Hello [pseudo], here are our latest news.</p>",
            template="newsletter.html",
            target="verified_subscribed",
            target_lang="en",
            total_recipients=1,
        )
        db.session.add(campaign)
        db.session.flush()

        delivery = NewsletterDelivery(
            campaign_id=campaign.id,
            email="sarah@oxford.uk",
            tracking_token="token-sarah-123",
            status="pending",
        )
        db.session.add(delivery)
        db.session.commit()

        recipient_data = [
            {
                "id": 1,
                "delivery_id": delivery.id,
                "email": "sarah@oxford.uk",
                "name": "Sarah Connor",
                "lang": "en",
                "unsubscribe_url": "http://localhost/unsubscribe/token/1",
                "tracking_pixel_url": "http://localhost/email/track/token-sarah-123.png",
            }
        ]

        send_newsletter_async(
            app,
            campaign.id,
            subject="Welcome [pseudo]!",
            sender="admin@livresenclasse.com",
            template_path="email/newsletter.html",
            message_content="<p>Hello [pseudo], here are our latest news.</p>",
            recipient_data=recipient_data,
            feedback_idea_url="http://localhost/feedback?type=idea",
            feedback_bug_url="http://localhost/feedback?type=bug",
            reglage_url="http://localhost/reglage",
        )

        assert mock_send.called
        sent_msg = mock_send.call_args[0][0]

        # 1. Check pseudo substitution in subject
        assert sent_msg.subject == "Welcome Sarah Connor!"

        # 2. Check pseudo substitution in HTML content
        assert "<p>Hello Sarah Connor, here are our latest news.</p>" in sent_msg.html

        # 3. Check force_locale localized chrome strings in English
        assert "School library management platform" in sent_msg.html
        assert "The Livres en Classe Team" in sent_msg.html
        assert "Your feedback matters to us" in sent_msg.html
        assert "Manage my preferences" in sent_msg.html
        assert "Unsubscribe" in sent_msg.html

        # 4. Check text body fallback localization & pseudo replacement
        assert "Welcome Sarah Connor!" in sent_msg.body
        assert "To unsubscribe:" in sent_msg.body
        assert "Give your feedback:" in sent_msg.body

        # 5. Check DB delivery status updated to 'sent'
        db.session.expire_all()
        delivery_db = db.session.get(NewsletterDelivery, delivery.id)
        assert delivery_db.status == "sent"
        assert delivery_db.sent_at is not None
