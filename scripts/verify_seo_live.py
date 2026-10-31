import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import xml.etree.ElementTree as ET

from project import create_app

app = create_app()
client = app.test_client()


def test_sitemap():
    print("=== Testing sitemap.xml ===")
    res = client.get("/sitemap.xml")
    assert res.status_code == 200, f"Sitemap returned {res.status_code}"
    content = res.get_data(as_text=True)
    assert "<lastmod>2026-09-12</lastmod>" in content, "Missing lastmod in sitemap"
    assert "/install" in content, "Missing /install in sitemap"

    # Parse XML
    root = ET.fromstring(content)
    namespaces = {
        "ns": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "xhtml": "http://www.w3.org/1999/xhtml",
    }
    urls = [loc.text for loc in root.findall(".//ns:loc", namespaces)]
    print(f"Total URLs in sitemap: {len(urls)}")

    # Test all URLs from sitemap
    for url in urls:
        path = url.replace("https://livresenclasse.com", "").replace(
            "http://localhost", ""
        )
        r = client.get(path)
        assert r.status_code == 200, f"URL {path} returned {r.status_code}"
        # Ensure correct hreflang alternate tags on html pages
        if not path.endswith((".xml", ".txt", ".ico", ".png", ".json")):
            html = r.get_data(as_text=True)
            assert 'rel="alternate" hreflang="fr"' in html, (
                f"Missing hreflang fr in {path}"
            )
            assert 'rel="alternate" hreflang="x-default"' in html, (
                f"Missing hreflang x-default in {path}"
            )
            if not any(
                res_tool in path
                for res_tool in (
                    "marque-pages",
                    "diplome-de-lecture",
                    "fiche-de-lecture",
                    "charte-coin-lecture",
                    "defi-lecture-bingo",
                    "passeport-de-lecture",
                )
            ):
                assert 'rel="alternate" hreflang="en"' in html, (
                    f"Missing hreflang en in {path}"
                )
                assert 'rel="alternate" hreflang="de"' in html, (
                    f"Missing hreflang de in {path}"
                )
    print("All sitemap URLs verified with HTTP 200 and hreflang tags.")


def test_multilingual_blog():
    print("=== Testing Multilingual Blog Articles ===")
    articles = [
        "comment-classer-livres",
        "donner-envie-lire",
        "meilleurs-livres-cp",
        "gestion-bibliotheque-classe",
        "logiciel-bcd-ecole",
        "application-scan-code-barre-livre",
        "suivi-emprunts-livres-eleves",
    ]

    for slug in articles:
        # FR
        r_fr = client.get(f"/fr/blog/{slug}")
        assert r_fr.status_code == 200, f"/fr/blog/{slug} returned {r_fr.status_code}"
        html_fr = r_fr.get_data(as_text=True)
        assert 'lang="fr"' in html_fr, f"html lang not fr for {slug}"
        assert "Sommaire" in html_fr or "Accueil" in html_fr, (
            f"French content missing for {slug}"
        )

        # EN
        r_en = client.get(f"/en/blog/{slug}")
        assert r_en.status_code == 200, f"/en/blog/{slug} returned {r_en.status_code}"
        html_en = r_en.get_data(as_text=True)
        assert 'lang="en"' in html_en, f"html lang not en for {slug}"
        assert "Table of Contents" in html_en or "Home" in html_en, (
            f"English content missing for {slug}"
        )
        assert 'inLanguage": "en"' in html_en, f"Schema inLanguage not en for {slug}"

        # DE
        r_de = client.get(f"/de/blog/{slug}")
        assert r_de.status_code == 200, f"/de/blog/{slug} returned {r_de.status_code}"
        html_de = r_de.get_data(as_text=True)
        assert 'lang="de"' in html_de, f"html lang not de for {slug}"
        assert "Inhaltsverzeichnis" in html_de or "Startseite" in html_de, (
            f"German content missing for {slug}"
        )
        assert 'inLanguage": "de"' in html_de, f"Schema inLanguage not de for {slug}"

        print(f"Article {slug}: verified FR, EN, and DE versions!")


def test_enseignants():
    print("=== Testing /enseignants in FR, EN, DE ===")
    # FR
    r_fr = client.get("/fr/enseignants")
    assert r_fr.status_code == 200
    html_fr = r_fr.get_data(as_text=True)
    assert "Espace Enseignants" in html_fr
    assert "Gérer la Bibliothèque" in html_fr

    # EN
    r_en = client.get("/en/enseignants")
    assert r_en.status_code == 200
    html_en = r_en.get_data(as_text=True)
    assert "Teachers Area" in html_en
    assert "Manage the Library" in html_en

    # DE
    r_de = client.get("/de/enseignants")
    assert r_de.status_code == 200
    html_de = r_de.get_data(as_text=True)
    assert "Lehrerbereich" in html_de or "Bereich für Lehrkräfte" in html_de
    assert "Bibliothek verwalten" in html_de
    print("/enseignants verified in all 3 languages.")


def test_schema_org():
    print("=== Testing Schema.org JSON-LD Structured Data ===")
    # Aide FAQPage
    r_aide = client.get("/fr/aide")
    assert r_aide.status_code == 200
    html_aide = r_aide.get_data(as_text=True)
    assert '"@type": "FAQPage"' in html_aide
    assert '"mainEntity"' in html_aide
    assert '"@type": "Question"' in html_aide
    assert '"@type": "Answer"' in html_aide

    # Blog CollectionPage
    r_blog = client.get("/fr/blog")
    assert r_blog.status_code == 200
    html_blog = r_blog.get_data(as_text=True)
    assert '"Blog"' in html_blog
    assert '"CollectionPage"' in html_blog

    # Ressources CollectionPage
    r_ressources = client.get("/fr/ressources")
    assert r_ressources.status_code == 200
    html_ressources = r_ressources.get_data(as_text=True)
    assert '"@type": "CollectionPage"' in html_ressources

    # Contact ContactPage
    r_contact = client.get("/fr/contact")
    assert r_contact.status_code == 200, (
        f"Public /contact returned {r_contact.status_code}"
    )
    html_contact = r_contact.get_data(as_text=True)
    assert '"@type": "ContactPage"' in html_contact
    assert "livresenclasse@gmail.com" in html_contact

    # Apropos AboutPage
    r_apropos = client.get("/fr/apropos")
    assert r_apropos.status_code == 200
    html_apropos = r_apropos.get_data(as_text=True)
    assert '"@type": "AboutPage"' in html_apropos
    assert "Robin Forestier" in html_apropos

    # Tarifs Product & Offer
    r_tarifs = client.get("/fr/tarifs")
    assert r_tarifs.status_code == 200
    html_tarifs = r_tarifs.get_data(as_text=True)
    assert '"@type": "Product"' in html_tarifs
    assert '"@type": "AggregateOffer"' in html_tarifs
    assert '"priceCurrency": "CHF"' in html_tarifs

    # Mentions légales WebPage
    r_mentions = client.get("/fr/mentions_legales")
    assert r_mentions.status_code == 200
    html_mentions = r_mentions.get_data(as_text=True)
    assert '"@type": "WebPage"' in html_mentions
    print("All Schema.org JSON-LD structured data verified.")


def test_meta_and_performance():
    print("=== Testing Open Graph, Twitter Cards, and Preconnect ===")
    r = client.get("/fr/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'property="og:site_name" content="Livres en Classe"' in html
    assert 'property="og:type" content="website"' in html
    assert 'property="og:image"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert 'name="twitter:title"' in html
    assert 'name="twitter:description"' in html
    assert 'name="twitter:image"' in html
    assert 'rel="preconnect" href="https://cdnjs.cloudflare.com"' in html
    assert 'rel="preconnect" href="https://kit.fontawesome.com"' in html
    assert "Logiciel de gestion de bibliothèque de classe gratuit" in html
    assert "bibliothèque de classe gratuit pour les enseignants" in html
    print("Open Graph, Twitter Cards, and preconnect tags verified.")


def test_robots():
    print("=== Testing robots.txt ===")
    r = client.get("/robots.txt")
    assert r.status_code == 200
    txt = r.get_data(as_text=True)
    assert "Allow: /" in txt
    assert "Sitemap: https://livresenclasse.com/sitemap.xml" in txt
    print("robots.txt verified.")


def test_bing_indexnow():
    print("=== Testing Bing Webmaster & IndexNow ===")
    r = client.get("/744d589148a54a93bfd6c066fce258a6.txt")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "text/plain" in r.content_type
    key_content = r.get_data(as_text=True).strip()
    assert key_content == "744d589148a54a93bfd6c066fce258a6", (
        f"Unexpected content: {key_content}"
    )

    # Verify Bing meta tag in homepage
    r_home = client.get("/fr/")
    assert r_home.status_code == 200
    html = r_home.get_data(as_text=True)
    assert (
        '<meta name="msvalidate.01" content="744d589148a54a93bfd6c066fce258a6"/>'
        in html
    )
    print("Bing Webmaster & IndexNow verified successfully.")


if __name__ == "__main__":
    test_robots()
    test_bing_indexnow()
    test_sitemap()
    test_meta_and_performance()
    test_multilingual_blog()
    test_enseignants()
    test_schema_org()
    print("\nALL SEO VERIFICATIONS PASSED SUCCESSFULLY!")
