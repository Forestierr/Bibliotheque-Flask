# LivresEnClasse.com — Gestion de bibliothèque de classe

[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/flask-3.0-lightgrey.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-green.svg)](LICENSE.md)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Testing](https://img.shields.io/badge/tests-pytest-yellow.svg)](project/test/)

[English version](README.en.md)

**LivresEnClasse.com** (Bibliothèque-Flask) est une application web conçue spécialement pour les enseignants afin de gérer facilement leur bibliothèque de classe, suivre les emprunts des élèves et enrichir leur catalogue grâce au scan de codes-barres.

---

## Sommaire

- [Fonctionnalités clés](#fonctionnalités-clés)
- [Stack technique](#stack-technique)
- [Démarrage rapide en local (Quickstart)](#démarrage-rapide-en-local-quickstart)
- [Documentation technique](#documentation-technique)
- [Qualité du code & Tests](#qualité-du-code--tests)
- [Licence](#licence)

---

## Fonctionnalités clés

- **Scan code-barres & enrichissement multi-APIs** : Reconnaissance instantanée par webcam/smartphone (HTML5-QRCode) avec recherche en cascade sur la **Bibliothèque nationale de France (BnF SRU Dublin Core)**, **Google Books** et **Open Library**.
- **Gestion des élèves & prêts** : Emprunts et retours en un clic, historique des lectures, indicateurs d'ouvrages en retard.
- **Outils de classe & impressions** : Génération de planches de codes-barres vectoriels et d'étiquettes thématiques pour les bacs de livres.
- **Modèle SaaS Freemium & Stripe** : Quotas gratuits (40 élèves, 500 livres, 30 scans/semaine), période d'essai de 30 jours, statut Fondateur à vie et abonnement Premium illimité opéré par Stripe Checkout et le Portail Client Stripe.
- **Multi-langue & SEO international** : Support complet du Français 🇫🇷, Anglais 🇬🇧 et Allemand 🇩🇪 avec URLs dédiées (`/fr/`, `/en/`, `/de/`) et balises `hreflang`.
- **Sécurité & Confidentialité** : Authentification sécurisée (Werkzeug/Scrypt), protection anti-brute force et anti-spam (hCaptcha), isolation stricte des données par enseignant et politique de non-destruction des données.

---

## Stack technique

- **Backend** : Python 3.12, Flask 3, Flask-Login, Flask-WTF, Flask-Babel 4
- **ORM & Base de données** : SQLAlchemy, Flask-Migrate (Alembic), SQLite (stocké dans `instance/db.sqlite`)
- **Frontend** : Jinja2, HTML5 sémantique, CSS3 responsive (design système fluide), Vanilla JavaScript
- **Production & Conteneurisation** : Gunicorn, Traefik (reverse proxy & TLS Let's Encrypt), Authelia (2FA /admin), Docker Compose, Cloudflare Tunnel

---

## Démarrage rapide en local (Quickstart)

Pour lancer le projet en environnement de développement local en 5 étapes :

```bash
# 1. Cloner le dépôt et entrer dans le dossier
git clone https://github.com/Forestierr/Bibliotheque-Flask.git
cd Bibliotheque-Flask

# 2. Créer et activer l'environnement virtuel Python 3.12
python -m venv venv
# Sur Linux / macOS : source venv/bin/activate
# Sur Windows (PowerShell) : .\venv\Scripts\Activate.ps1

# 3. Installer les dépendances applicatives et d'outillage
pip install --upgrade pip
pip install -r project/requirements.txt
pip install ruff pytest

# 4. Configurer les variables d'environnement
cp .env.example .env

# 5. Appliquer les migrations de base de données et lancer le serveur
export FLASK_APP=project   # Windows PowerShell: $env:FLASK_APP="project"
flask db upgrade
flask run -p 5000 -h 127.0.0.1
```

Accédez ensuite à l'application dans votre navigateur à l'adresse : **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

> **Note Caméra / HTTPS :** Les navigateurs modernes restreignent l'accès à la webcam aux contextes sécurisés (HTTPS ou localhost). Pour tester le scanner sur un smartphone connecté à votre réseau local, lancez le serveur avec :
> ```bash
> flask run -p 5000 -h 0.0.0.0 --cert adhoc
> ```

---

## Documentation technique

Pour approfondir le fonctionnement, l'architecture et la maintenance du projet, consultez les guides détaillés situés dans le dossier [`/docs`](docs/) :

| Document | Description |
| :--- | :--- |
| [**Architecture logicielle**](docs/architecture.md) | Découpage en 11 Blueprints, diagramme Mermaid du cycle HTTP, filtres Jinja2, middlewares et scheduler multi-workers. |
| [**Base de données**](docs/base-de-donnees.md) | Diagramme relationnel complet (`erDiagram`), détail des 9 tables, gestion des migrations Alembic et stratégie de sauvegarde SQLite. |
| [**Déploiement en production**](docs/deploiement.md) | Guide pas-à-pas pour serveur de production, stack Traefik, Authelia, Cloudflare Tunnel, images GHCR et persistance. |
| [**APIs Externes & Intégrations**](docs/apis-externes.md) | Spécifications des requêtes BnF SRU (Dublin Core), Google Books, Open Library, webhooks Stripe et hCaptcha (dont obligations légales BnF). |
| [**Configuration & Variables**](docs/configuration.md) | Répertoire exhaustif des variables `.env`, constantes métiers de tarification (`config_plans.py`), cookies de session et drapeaux d'environnement. |
| [**Exploitation & Maintenance**](docs/maintenance.md) | Utilitaire des scripts CLI (`scripts/`), gestion manuelle des quotas et des comptes Fondateurs, supervision et résolution des pannes courantes. |

---

## Qualité du code & Tests

Le projet intègre un pipeline strict de validation CI/CD sur GitHub Actions ([`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)) :

- **Formatage & Linting** :
  ```bash
  ruff format project/
  ruff check project/
  ```
- **Tests unitaires & d'intégration** :
  ```bash
  pytest project/test/
  ```
- **Internationalisation (i18n)** :  
  Avant de soumettre une modification touchant aux traductions, les fichiers `.mo` compilés doivent impérativement être mis à jour :
  ```bash
  pybabel compile -d project/translations
  ```

Consultez le guide [**CONTRIBUTING.md**](CONTRIBUTING.md) pour découvrir les règles complètes de contribution.

---

## Licence

Ce projet est distribué sous licence **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)** (Source-Available) — voir le fichier [LICENSE.md](LICENSE.md).

- **Autorisé** : Utilisation personnelle, pédagogique, éducative (écoles, enseignants, médiathèques), recherche et contributions open source non commerciales.
- **Interdit** : Toute exploitation commerciale, monétisation directe ou indirecte, revente ou hébergement SaaS payant concurrent sans autorisation écrite préalable de l'auteur.
