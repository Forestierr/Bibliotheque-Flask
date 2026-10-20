import pytest

from project import create_app, db


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-key-blog",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_blog_index_has_100_classes_card(client):
    """Vérifie que la page index du blog affiche la nouvelle carte d'article dans les 3 langues."""
    # Français
    res_fr = client.get("/fr/blog")
    assert res_fr.status_code == 200
    html_fr = res_fr.get_data(as_text=True)
    assert "/blog/cap-100-classes" in html_fr
    assert "Cap des 100 classes franchi" in html_fr

    # Anglais
    res_en = client.get("/en/blog")
    assert res_en.status_code == 200
    html_en = res_en.get_data(as_text=True)
    assert "/blog/cap-100-classes" in html_en
    assert "Milestone of 100 Classes Reached" in html_en

    # Allemand
    res_de = client.get("/de/blog")
    assert res_de.status_code == 200
    html_de = res_de.get_data(as_text=True)
    assert "/blog/cap-100-classes" in html_de
    assert "Meilenstein von 100 Klassen erreicht" in html_de


def test_cap_100_classes_article_french(client):
    """Vérifie le contenu et le balisage de l'article en français."""
    res = client.get("/fr/blog/cap-100-classes")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Cap des 100 classes franchi : merci pour votre confiance !" in html
    assert "Robin Forestier" in html
    assert "Créateur de Livres en classe" in html
    assert "+10 000" in html
    assert "~1 000" in html
    assert "+1 000" in html
    assert "membres fondateurs" in html
    assert "maman, enseignante" in html
    assert '"@type": "BlogPosting"' in html


def test_cap_100_classes_article_english(client):
    """Vérifie le contenu et le balisage de l'article en anglais."""
    res = client.get("/en/blog/cap-100-classes")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Milestone of 100 Classes Reached: Thank You for Your Trust!" in html
    assert "Robin Forestier" in html
    assert "Creator of Livres en classe" in html
    assert "+10,000" in html
    assert "~1,000" in html
    assert "+1,000" in html
    assert "founding members" in html
    assert "elementary school teacher" in html or "mother" in html
    assert '"@type": "BlogPosting"' in html


def test_cap_100_classes_article_german(client):
    """Vérifie le contenu et le balisage de l'article en allemand."""
    res = client.get("/de/blog/cap-100-classes")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Meilenstein von 100 Klassen erreicht: Danke für Ihr Vertrauen!" in html
    assert "Robin Forestier" in html
    assert "Gründer von Livres en classe" in html
    assert "+10.000" in html
    assert "~1.000" in html
    assert "+1.000" in html
    assert "Gründungsmitgliedern" in html
    assert "Grundschullehrerin" in html or "Mutter" in html
    assert '"@type": "BlogPosting"' in html


def test_sitemap_contains_cap_100_classes(client):
    """Vérifie que le sitemap liste bien l'article pour chaque langue avec balises hreflang."""
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    xml = res.get_data(as_text=True)

    assert "https://livresenclasse.com/fr/blog/cap-100-classes" in xml
    assert "https://livresenclasse.com/en/blog/cap-100-classes" in xml
    assert "https://livresenclasse.com/de/blog/cap-100-classes" in xml
    assert 'hreflang="fr" href="https://livresenclasse.com/fr/blog/cap-100-classes"' in xml
    assert 'hreflang="en" href="https://livresenclasse.com/en/blog/cap-100-classes"' in xml
    assert 'hreflang="de" href="https://livresenclasse.com/de/blog/cap-100-classes"' in xml
