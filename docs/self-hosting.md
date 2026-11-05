# Guide d'Auto-hébergement & Développement Local — Livres en Classe

Ce guide s'adresse aux développeurs et administrateurs système souhaitant installer, exécuter ou auto-héberger une instance de **LivresEnClasse.com**.

> [!NOTE]
> **LivresEnClasse.com** est principalement conçu et maintenu comme un service hébergé en ligne prêt à l'emploi à destination des enseignants.  
> Le projet est distribué sous licence [PolyForm Noncommercial 1.0.0](../LICENSE.md) (*Source-Available*) : son utilisation personnelle, pédagogique et contributive est encouragée, mais toute commercialisation ou hébergement payant concurrent est strictement interdit sans accord préalable.

---

## Sommaire

1. [Prérequis système](#1-prérequis-système)
2. [APIs & Services externes requis](#2-apis--services-externes-requis)
3. [Installation locale en 5 étapes](#3-installation-locale-en-5-étapes)
4. [Lancement avec Docker Compose](#4-lancement-avec-docker-compose)
5. [Particularités importantes (Caméra HTTPS & PWA)](#5-particularités-importantes-caméra-https--pwa)
6. [Dépannage & Questions fréquentes](#6-dépannage--questions-fréquentes)

---

## 1. Prérequis système

* **Python** : Version 3.12 recommandée (3.11+ compatible).
* **Base de données** : SQLite 3 (inclus par défaut, fichier stocké dans `instance/db.sqlite`).
* **Navigateur moderne** : Chrome, Firefox, Safari ou Edge avec support des API caméra (`getUserMedia`) et Service Worker.

---

## 2. APIs & Services externes requis

Pour faire fonctionner l'ensemble des fonctionnalités de la plateforme, plusieurs services tiers doivent être configurés dans le fichier `.env` :

| Service | Rôle | Obligatoire en dev local ? | Notes de configuration |
| :--- | :--- | :---: | :--- |
| **BnF SRU API** | Récupération des métadonnées officielles des livres par code ISBN. | **Non** (accès public ouvert) | API ouverte de la Bibliothèque nationale de France (format Dublin Core). |
| **Google Books API** | Recherche de livres et couvertures alternatives. | **Non** (fallback anonyme) | Clé API optionnelle mais recommandée pour éviter les quotas d'IP. |
| **Open Library** | Couvertures de livres distantes. | **Non** (accès public ouvert) | URLs directes `covers.openlibrary.org`. |
| **Serveur SMTP** | Envoi des e-mails d'activation de compte et notifications. | **Recommandé** | SMTP Gmail ou service transactionnel (Mailjet, Brevo, Sendgrid). En mode dev, les comptes peuvent être vérifiés directement en base via `is_verified=True`. |
| **hCaptcha** | Protection anti-robot sur les formulaires d'inscription et contact. | **Optionnel en local** | Des clés de test sont disponibles dans la documentation hCaptcha. |
| **Stripe** | Gestion des abonnements et portail de facturation. | **Optionnel** | En mode test local, renseignez vos clés de test Stripe (`pk_test_...` et `sk_test_...`) et écoutez les webhooks via la CLI Stripe (`stripe listen --forward-to localhost:5000/webhook/stripe`). |

---

## 3. Installation locale en 5 étapes

### Étape 1 : Cloner le dépôt

```bash
git clone https://github.com/Forestierr/Bibliotheque-Flask.git
cd Bibliotheque-Flask
```

### Étape 2 : Créer et activer l'environnement virtuel

```bash
# Création de l'environnement virtuel
python -m venv venv

# Activation :
# Sur Linux / macOS :
source venv/bin/activate

# Sur Windows (PowerShell) :
.\venv\Scripts\Activate.ps1
```

### Étape 3 : Installer les dépendances

```bash
pip install --upgrade pip
pip install -r project/requirements.txt
pip install ruff pytest
```

### Étape 4 : Configurer les variables d'environnement

Copiez le modèle d'environnement et adaptez-le selon vos besoins :

```bash
cp .env.example .env
```

Générez une clé secrète pour Flask :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Puis renseignez cette valeur dans le paramètre `SECRET_KEY` de votre fichier `.env`.

### Étape 5 : Initialiser la base de données et démarrer

```bash
# Définir l'application Flask
export FLASK_APP=project     # Windows PowerShell: $env:FLASK_APP="project"

# Appliquer les migrations de base de données Alembic
flask db upgrade

# Compiler les catalogues de langues Gettext (fr, en, de)
pybabel compile -d project/translations

# Lancer le serveur de développement
flask run -p 5000 -h 127.0.0.1
```

L'application est accessible à l'adresse : **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

---

## 4. Lancement avec Docker Compose

Pour exécuter l'application dans un conteneur Docker :

```bash
# Construire et démarrer le conteneur en arrière-plan
docker compose up --build -d

# Vérifier les logs
docker compose logs -f

# Arrêter les services
docker compose down
```

Pour une mise en production orchestrée avec Traefik, Let's Encrypt et Cloudflare Tunnel, consultez le guide complet : [**docs/deploiement.md**](deploiement.md).

---

## 5. Particularités importantes (Caméra HTTPS & PWA)

* **Accès à la caméra pour le scan des livres** :  
  Les navigateurs modernes (Chrome, iOS Safari, Firefox) **bloquent l'accès à la caméra sur les connexions HTTP non sécurisées**, sauf pour `localhost` et `127.0.0.1`.  
  Si vous testez le scanner depuis votre smartphone connecté sur le même réseau Wi-Fi local que votre PC, vous devez impérativement démarrer Flask avec un certificat HTTPS temporaire :
  ```bash
  flask run -p 5000 -h 0.0.0.0 --cert adhoc
  ```
  *(Installez `cryptography` via `pip install cryptography` si demandé par Flask).*

* **Internationalisation (i18n)** :  
  L'application utilise Flask-Babel 4 et des routes avec préfixe de langue (`/fr/`, `/en/`, `/de/`). Si vous modifiez des gabarits ou des textes, n'oubliez pas de recompiler les catalogues :
  ```bash
  pybabel compile -d project/translations
  ```

---

## 6. Dépannage & Questions fréquentes

- **Erreur `sqlite3.OperationalError: no such column...`** :  
  La base de données n'est pas à jour. Exécutez `flask db upgrade` pour appliquer toutes les migrations Alembic en attente.
- **Les images de couverture ne s'affichent pas** :  
  Vérifiez que votre connexion Internet autorise l'accès à `covers.openlibrary.org` et `books.google.com`.
- **E-mails non envoyés en local** :  
  En développement, si aucun serveur SMTP n'est renseigné, vous pouvez activer manuellement les comptes d'utilisateurs créés via l'interpréteur Python :
  ```python
  from project import create_app, db
  from project.models import User
  app = create_app()
  with app.app_context():
      u = User.query.filter_by(email="votre@email.fr").first()
      if u:
          u.is_verified = True
          db.session.commit()
          print("Compte activé !")
  ```
