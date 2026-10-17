"""Script CLI pour soumettre des URLs à IndexNow (Bing, Yandex, Naver, Seznam).

Usage:
    # 1. Simuler l'envoi de toutes les URLs du sitemap rendu (mode dry-run)
    python scripts/submit_indexnow.py --dry-run

    # 2. Soumettre toutes les URLs du sitemap à l'API IndexNow
    python scripts/submit_indexnow.py

    # 3. Soumettre des URLs spécifiques
    python scripts/submit_indexnow.py --urls https://livresenclasse.com/fr/ https://livresenclasse.com/fr/tarifs
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests

DEFAULT_HOST = "livresenclasse.com"
DEFAULT_KEY = os.getenv("INDEXNOW_KEY", "744d589148a54a93bfd6c066fce258a6")
DEFAULT_ENDPOINT = "https://api.indexnow.org/IndexNow"


def get_rendered_sitemap_urls(
    from_live: bool = False, host: str = DEFAULT_HOST
) -> list[str]:
    """Récupère et parse les URLs du sitemap XML (soit via le template Flask rendu, soit en ligne)."""
    if from_live:
        url = f"https://{host}/sitemap.xml"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        xml_content = res.text
    else:
        from flask import render_template

        from project import create_app

        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
            }
        )
        with app.app_context(), app.test_request_context():
            xml_content = render_template("utils/sitemap.xml")

    root = ET.fromstring(xml_content)
    namespaces = {
        "ns": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "xhtml": "http://www.w3.org/1999/xhtml",
    }
    urls = []
    for loc in root.findall(".//ns:loc", namespaces):
        if loc.text:
            cleaned = loc.text.strip()
            if cleaned not in urls:
                urls.append(cleaned)
    return urls


def submit_to_indexnow(
    host: str,
    key: str,
    key_location: str,
    url_list: list[str],
    endpoint: str = DEFAULT_ENDPOINT,
    dry_run: bool = False,
) -> dict:
    """Envoie une requête POST à l'API IndexNow."""
    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": url_list,
    }

    if dry_run:
        print("[DRY-RUN] Payload qui serait envoyé à IndexNow :")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return {"status_code": 0, "message": "Dry-run terminé avec succès"}

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "LivresEnClasse-IndexNow/1.0",
    }

    print(f"Envoi de {len(url_list)} URL(s) vers {endpoint}...")
    response = requests.post(
        endpoint,
        data=json.dumps(payload),
        headers=headers,
        timeout=15,
    )

    status_meanings = {
        200: "OK — URLs soumises avec succès.",
        202: "Accepted — URLs reçues, validation de la clé en cours.",
        400: "Bad Request — Format de requête invalide.",
        403: "Forbidden — Clé IndexNow invalide ou introuvable.",
        422: "Unprocessable Entity — Les URLs n'appartiennent pas à l'hôte spécifié.",
        429: "Too Many Requests — Quota dépassé (trop de requêtes).",
    }

    meaning = status_meanings.get(
        response.status_code, f"Code HTTP inattendu : {response.status_code}"
    )
    print(f"Réponse HTTP {response.status_code} : {meaning}")
    if response.text and response.status_code not in (200, 202):
        print(f"Détail : {response.text}")

    return {
        "status_code": response.status_code,
        "reason": meaning,
        "response_text": response.text,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Soumission d'URLs à Bing et aux moteurs de recherche via IndexNow"
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Nom de domaine hôte (défaut: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--key",
        default=DEFAULT_KEY,
        help="Clé API IndexNow (défaut: lue depuis env ou configurée)",
    )
    parser.add_argument(
        "--key-location",
        default=None,
        help="URL absolue du fichier clé (défaut: https://<host>/<key>.txt)",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Endpoint de l'API IndexNow (défaut: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--urls",
        nargs="*",
        default=None,
        help="Liste d'URLs spécifiques à soumettre (optionnel)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Télécharge le sitemap depuis https://<host>/sitemap.xml au lieu de le rendre localement",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le payload sans envoyer de requête HTTP",
    )

    args = parser.parse_args()

    key_location = args.key_location or f"https://{args.host}/{args.key}.txt"

    if args.urls:
        urls = args.urls
    else:
        try:
            urls = get_rendered_sitemap_urls(from_live=args.live, host=args.host)
        except Exception as e:  # noqa: BLE001
            print(f"Erreur lors de la récupération du sitemap : {e}", file=sys.stderr)
            sys.exit(1)

    if not urls:
        print("Aucune URL à soumettre.", file=sys.stderr)
        sys.exit(1)

    print("--- IndexNow Submission ---")
    print(f"Hôte : {args.host}")
    print(f"Clé : {args.key}")
    print(f"Emplacement de la clé : {key_location}")
    print(f"Nombre d'URLs : {len(urls)}")

    res = submit_to_indexnow(
        host=args.host,
        key=args.key,
        key_location=key_location,
        url_list=urls,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
    )

    if not args.dry_run and res["status_code"] not in (200, 202):
        sys.exit(1)


if __name__ == "__main__":
    main()
