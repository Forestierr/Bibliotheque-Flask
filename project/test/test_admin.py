import pytest

from project import create_app, db
from project.models import Book, Feedback, Student, User


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        # Seed test data
        u1 = User(
            id=1,
            email="prof1@test.com",
            name="Alice Prof",
            plan="free",
            is_verified=True,
        )
        u2 = User(
            id=2,
            email="prof2@test.com",
            name="Bob Enseignant",
            plan="premium",
            stripe_subscription_status="active",
            is_verified=True,
        )
        db.session.add_all([u1, u2])

        b1 = Book(id=1, title="Le Petit Prince", author="Saint-Exupéry", user_id=1)
        b2 = Book(id=2, title="Harry Potter", author="J.K. Rowling", user_id=2)
        db.session.add_all([b1, b2])

        s1 = Student(id=1, name="Dupont", firstname="Lucas", user_id=1)
        s2 = Student(id=2, name="Martin", firstname="Emma", user_id=2)
        db.session.add_all([s1, s2])

        fb1 = Feedback(
            id=1,
            user_id=1,
            subject="Super outil",
            message="J'adore la bibliothèque !",
            category="suggestion",
            status="nouveau",
        )
        db.session.add(fb1)
        db.session.commit()

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_admin_dashboard(client):
    """Vérifie l'affichage du nouveau tableau de bord avec les cartes métriques et les graphiques financiers."""
    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Tableau de Bord" in html
    assert "Utilisateurs" in html
    assert "Abonnements" in html
    assert "Catalogue Global" in html
    assert "Dernières inscriptions" in html
    assert "Derniers retours &amp; bugs" in html or "Derniers retours & bugs" in html
    assert "Nouvelles Inscriptions (30 derniers jours)" in html
    assert "Répartition des Formules" in html
    assert "signupsChart" in html
    assert "plansChart" in html

    # Section Financière & Graphiques revenus / abonnements actifs par type
    assert (
        "Revenus &amp; Performance des Abonnements" in html
        or "Revenus & Performance des Abonnements" in html
    )
    assert "MRR (Mensuel)" in html
    assert "ARR (Annuel)" in html
    assert "Total Encaissé" in html
    assert "Abonnements Payants" in html
    assert "revenueChart" in html
    assert "Évolution des Revenus Encaissés" in html
    assert "Abonnements Actifs par Type" in html

    # Graphique divergent Flux des Abonnements & Résiliations
    assert (
        "Flux des Abonnements &amp; Résiliations" in html
        or "Flux des Abonnements & Résiliations" in html
    )
    assert "subFlowChart" in html
    assert "Nouveaux abonnements" in html
    assert "Résiliations" in html
    assert "Solde net" in html
    assert "Rétention" in html
    assert "Churn" in html


def test_admin_users_view(client):
    """Vérifie la page dédiée de gestion des utilisateurs."""
    res = client.get("/admin/utilisateurs")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Gestion des Utilisateurs" in html
    assert "prof1@test.com" in html
    assert "prof2@test.com" in html
    assert "Alice Prof" in html

    # Vérification des correctifs d'affichage du dropdown et du z-index
    assert "admin-users-card" in html
    assert "admin-actions-dropdown-content" in html
    assert "setupActionDropdowns" in html
    assert "has-dropdown-open" in html
    assert "modalEditPlan" in html


def test_admin_livres_view_and_search(client):
    """Vérifie la page catalogue des livres et la recherche."""
    res = client.get("/admin/livres")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Catalogue des Livres" in html
    assert "Le Petit Prince" in html
    assert "Harry Potter" in html

    # Recherche
    res_search = client.get("/admin/livres?q=Prince")
    assert res_search.status_code == 200
    html_search = res_search.get_data(as_text=True)
    assert "Le Petit Prince" in html_search
    assert "Harry Potter" not in html_search


def test_admin_eleves_view_and_search(client):
    """Vérifie la page répertoire des élèves et la recherche."""
    res = client.get("/admin/eleves")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Répertoire des Élèves" in html
    assert "Lucas" in html
    assert "Dupont" in html

    # Recherche
    res_search = client.get("/admin/eleves?q=Emma")
    assert res_search.status_code == 200
    html_search = res_search.get_data(as_text=True)
    assert "Emma" in html_search
    assert "Lucas" not in html_search


def test_admin_parametres_view(client):
    """Vérifie la page de paramètres système et constantes freemium."""
    res = client.get("/admin/parametres")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert (
        "Paramètres &amp; Configuration Système" in html
        or "Paramètres & Configuration Système" in html
    )
    assert "Passerelle Stripe" in html
    assert (
        "Constantes Freemium &amp; Abonnements" in html
        or "Constantes Freemium & Abonnements" in html
    )
    assert "Élèves max gratuits" in html
    assert "Livres max gratuits" in html


def test_admin_coupons_view(client):
    """Vérifie la vue des codes promos avec le nouveau layout sidebar."""
    res = client.get("/admin/coupons")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert (
        "Codes Promo &amp; Coupons Stripe" in html
        or "Codes Promo & Coupons Stripe" in html
    )


def test_admin_feedbacks_view(client):
    """Vérifie la vue des feedbacks avec le nouveau layout sidebar."""
    res = client.get("/admin/feedbacks")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert (
        "Retours Utilisateurs &amp; Anomalies" in html
        or "Retours Utilisateurs & Anomalies" in html
    )
    assert "Super outil" in html


def test_admin_dashboard_financial_breakdown(client, app):
    """Vérifie le calcul et l'affichage des abonnements mensuels et annuels sur le tableau de bord."""
    with app.app_context():
        u_monthly = User(
            email="monthly@ecole.fr",
            name="Monthly Prof",
            plan="premium",
            stripe_subscription_status="active",
            stripe_price_id="monthly",
            is_verified=True,
        )
        u_yearly = User(
            email="yearly@ecole.fr",
            name="Yearly Prof",
            plan="premium",
            stripe_subscription_status="active",
            stripe_price_id="yearly",
            is_verified=True,
        )
        db.session.add_all([u_monthly, u_yearly])
        db.session.commit()

    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    # Both monthly and yearly subscriptions should be reflected
    assert "Mensuel" in html
    assert "Annuel" in html
    assert "revenueChart" in html
    assert "subTypesChart" in html
