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
    assert (
        "Nouvelles Inscriptions (12 dernières semaines)" in html
        or "Nouvelles Inscriptions" in html
    )
    assert "Taux d'Activation" in html
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


def test_admin_feedbacks_departure_analytics(client, app):
    """Vérifie l'analyse des départs et le graphique des motifs de résiliation dans /admin/feedbacks."""
    with app.app_context():
        fb_depart1 = Feedback(
            subject="Départ : Tarif trop élevé / trop cher",
            message="Formule au départ : free\n\nCommentaire : Trop cher pour mon budget",
            category="depart",
            departure_reason="too_expensive",
            author_name="Départ 1",
            author_email="depart1@ecole.fr",
            status="nouveau",
        )
        fb_depart2 = Feedback(
            subject="Départ : Tarif trop élevé / trop cher",
            message="Formule au départ : premium",
            category="depart",
            departure_reason="too_expensive",
            author_name="Départ 2",
            author_email="depart2@ecole.fr",
            status="nouveau",
        )
        fb_depart3 = Feedback(
            subject="Départ : Quotas de la version gratuite trop limités",
            message="Formule au départ : free",
            category="depart",
            departure_reason="free_limits",
            author_name="Départ 3",
            author_email="depart3@ecole.fr",
            status="nouveau",
        )
        db.session.add_all([fb_depart1, fb_depart2, fb_depart3])
        db.session.commit()

    res = client.get("/admin/feedbacks")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Vérification de la carte d'analyse des motifs de départ
    assert (
        "Analyse des Départs &amp; Churn" in html
        or "Analyse des Départs & Churn" in html
    )
    assert "departureReasonsChart" in html
    assert "Tarif trop élevé / trop cher" in html
    assert "Principal déclencheur de départ" in html
    assert "Départs enregistrés" in html
    assert "depart1@ecole.fr" in html

    # Vérification du filtre par catégorie "depart"
    res_filter = client.get("/admin/feedbacks?category=depart")
    assert res_filter.status_code == 200
    html_filter = res_filter.get_data(as_text=True)
    assert "depart1@ecole.fr" in html_filter
    assert "Super outil" not in html_filter


def test_admin_dashboard_to_process_block(client, app):
    """Vérifie le bloc « À traiter » du tableau de bord (état apaisé et éléments actionnables)."""
    with app.app_context():
        # Création d'utilisateurs test avec quota max de scans et essai expirant bientôt
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        u_max_scans = User(
            email="maxscans@test.fr",
            name="Max Scans User",
            plan="free",
            free_scans_used=30,
            is_verified=True,
        )
        u_expiring_trial = User(
            email="expiring@test.fr",
            name="Expiring Trial User",
            plan="free",
            trial_ends_at=now + timedelta(days=3),
            is_verified=True,
        )
        fb_unread = Feedback(
            subject="Bug critique scan",
            message="Le scanner ne s'ouvre plus sur Android",
            category="bug",
            author_name="Prof Bug",
            author_email="bug@test.fr",
            status="nouveau",
        )
        db.session.add_all([u_max_scans, u_expiring_trial, fb_unread])
        db.session.commit()

    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "À traiter" in html
    assert "nouveau(x) retour(s)" in html
    assert "compte(s) à 30/30 scans" in html
    assert "essai(s) expirant" in html
    assert "/admin/feedbacks?status=nouveau" in html
    assert "/admin/utilisateurs?scans=max" in html
    assert "/admin/utilisateurs?trial=expiring" in html


def test_admin_users_query_filters(client, app):
    """Vérifie le filtrage d'utilisateurs via paramètres d'URL (plan, scans, trial, activation)."""
    with app.app_context():
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        u_free = User(
            email="free_teacher@test.fr",
            name="Prof Free",
            plan="free",
            free_scans_used=5,
            is_verified=True,
        )
        u_scans_max = User(
            email="quota_teacher@test.fr",
            name="Prof Quota Max",
            plan="free",
            free_scans_used=30,
            is_verified=True,
        )
        u_trial_soon = User(
            email="trial_soon@test.fr",
            name="Prof Trial Soon",
            plan="free",
            trial_ends_at=now + timedelta(days=2),
            is_verified=True,
        )
        db.session.add_all([u_free, u_scans_max, u_trial_soon])
        db.session.commit()

    # Test filtre scans=max
    res_scans = client.get("/admin/utilisateurs?scans=max")
    assert res_scans.status_code == 200
    html_scans = res_scans.get_data(as_text=True)
    assert "quota_teacher@test.fr" in html_scans
    assert "free_teacher@test.fr" not in html_scans
    assert "Filtre actif" in html_scans

    # Test filtre trial=expiring
    res_trial = client.get("/admin/utilisateurs?trial=expiring")
    assert res_trial.status_code == 200
    html_trial = res_trial.get_data(as_text=True)
    assert "trial_soon@test.fr" in html_trial
    assert "free_teacher@test.fr" not in html_trial

    # Test filtre plan=premium
    res_premium = client.get("/admin/utilisateurs?plan=premium")
    assert res_premium.status_code == 200
    html_premium = res_premium.get_data(as_text=True)
    assert "Prof Free" not in html_premium


def test_admin_export_users_csv(client, app):
    """Vérifie l'export CSV des utilisateurs et le respect des filtres."""
    res = client.get("/admin/utilisateurs/export")
    assert res.status_code == 200
    assert res.headers["Content-Type"].startswith("text/csv")
    content = res.get_data(as_text=True)
    assert (
        "Nom;Email;Date d'inscription;Formule;Statut;Livres;Élèves;Scans cette semaine;Newsletter;Client Stripe"
        in content
    )
    assert "prof1@test.com" in content


def test_admin_user_detail_and_actions(client, app):
    """Vérifie la page de détail utilisateur et la modification de formule."""
    with app.app_context():
        u = User.query.filter_by(email="prof1@test.com").first()
        u_id = u.id

    res = client.get(f"/admin/utilisateurs/{u_id}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "prof1@test.com" in html
    assert "Actions Rapides" in html
    assert "Livres de la classe" in html

    # Changement de formule
    res_change = client.post(
        f"/admin/users/{u_id}/change-plan",
        data={"plan": "premium", "scans": "15"},
        follow_redirects=True,
    )
    assert res_change.status_code == 200
    with app.app_context():
        u_updated = db.session.get(User, u_id)
        assert u_updated.plan == "premium"
        assert u_updated.free_scans_used == 15


def test_admin_backup_db(client):
    """Vérifie l'accès à la route de sauvegarde de la base de données."""
    res = client.get("/admin/backup-db", follow_redirects=True)
    assert res.status_code == 200


def test_admin_dashboard_periods_and_series(client):
    """Vérifie le fonctionnement du sélecteur unifié de période et des 4 séries de métriques."""
    for period in ("7d", "30d", "12w", "12m"):
        res = client.get(f"/admin?range={period}")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Croissance &amp; Activité" in html or "Croissance & Activité" in html
        assert 'data-metric="users"' in html
        assert 'data-metric="books"' in html
        assert 'data-metric="students"' in html
        assert 'data-metric="loans"' in html


def test_admin_dashboard_saas_metrics(client, app):
    """Vérifie les 4 nouvelles métriques SaaS (WAU, santé ISBN, radar à paywalls)."""
    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Classes Actives Hebdomadaires (WAU)" in html
    assert (
        "Qualité &amp; Santé du Scan ISBN" in html
        or "Qualité & Santé du Scan ISBN" in html
    )
    assert "Radar à Paywalls (Conversion Freemium)" in html


def test_admin_toggle_user_test_and_exclude_filter(client, app):
    """Vérifie le marquage de compte de test et l'interrupteur global d'exclusion."""
    with app.app_context():
        u = User.query.filter_by(email="prof1@test.com").first()
        u_id = u.id
        assert not u.is_test

    # Basculer le compte en compte de test
    res_toggle = client.post(
        f"/admin/utilisateurs/{u_id}/toggle-test", follow_redirects=True
    )
    assert res_toggle.status_code == 200
    with app.app_context():
        u_test = db.session.get(User, u_id)
        assert u_test.is_test is True

    # Vérifier l'exclusion sur le dashboard
    res_dash_ex = client.get("/admin?exclude_tests=1")
    assert res_dash_ex.status_code == 200

    # Vérifier dans la liste des utilisateurs avec filtre statut test
    res_users = client.get("/admin/utilisateurs?status=test")
    assert res_users.status_code == 200
    assert "prof1@test.com" in res_users.get_data(as_text=True)
