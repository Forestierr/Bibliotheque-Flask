import pytest

from project import create_app


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    # other setup can go here

    yield app

    # clean up / reset resources here


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200


def test_homepage_freemium_section(client):
    """Vérifie que la section comparative Gratuit vs Premium est présente sur l'accueil avec liens vers tarifs."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Titre de la section
    assert "Une formule adaptée à votre classe" in html

    # Offre gratuite et quotas
    assert "Version Gratuite" in html
    assert "40" in html
    assert "500" in html
    assert "30" in html
    assert "10" in html

    # Offre Premium et lien vers tarifs
    assert "Abonnement Premium" in html
    assert "/tarifs" in html
    assert (
        "Voir le détail des tarifs &amp; offres" in html
        or "Voir le détail des tarifs & offres" in html
    )


def test_dashboard_premium_shows_loans_count(app):
    """Vérifie que le dashboard affiche 'Prêts enregistrés' pour un membre premium."""
    from project import db
    from project.models import User

    with app.app_context():
        user = User(
            id=77,
            email="premium_dash@test.com",
            plan="premium",
            stripe_subscription_status="active",
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = "77"

        res = client.get("/dashboard")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Prêts enregistrés" in html
