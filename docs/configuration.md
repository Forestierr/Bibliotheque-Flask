# Référentiel de Configuration - Livres en Classe

Ce document recense l'intégralité des variables d'environnement, options de paramétrage et constantes métier régissant le fonctionnement de **Livres en Classe**.

---

## Sommaire

1. [Principes de configuration](#1-principes-de-configuration)
2. [Tableau exhaustif des variables d'environnement (.env)](#2-tableau-exhaustif-des-variables-denvironnement-env)
3. [Constantes applicatives et quotas métier (config_plans.py)](#3-constantes-applicatives-et-quotas-métier-config_planspy)
4. [Configuration des sessions et cookies de sécurité](#4-configuration-des-sessions-et-cookies-de-sécurité)
5. [Journalisation et niveaux de logs](#5-journalisation-et-niveaux-de-logs)
6. [Questions ouvertes](#6-questions-ouvertes)

---

## 1. Principes de configuration

* **Fichier `.env`** : Situé à la racine du projet, chargé automatiquement au démarrage par `python-dotenv`.
* **Sécurité des secrets** : Le fichier `.env` est exclu du contrôle de version via `.gitignore`. En production, ses permissions doivent être restreintes (`chmod 600 .env`).
* **Valeurs par défaut sécurisées** : Si une variable optionnelle est omise, l'application applique un comportement par défaut sécurisé ou désactive gracieusement la fonctionnalité dépendante (par exemple, désactivation de hCaptcha en local).

---

## 2. Tableau exhaustif des variables d'environnement (.env)

| Variable | Rôle / Description | Obligatoire | Valeur par défaut si omise | Exemple factice |
| :--- | :--- | :---: | :--- | :--- |
| `SECRET_KEY` | Clé secrète cryptographique utilisée pour signer les sessions Flask, les cookies d'authentification et les jetons temporels (`itsdangerous`). | **Oui** | `'dev-secret-key'` | `'b9d7e3a8f1c42...99a'` |
| `FLASK_ENV` | Environnement d'exécution. Si défini à `'production'`, désactive `db.create_all()` au profit d'Alembic et active les cookies HTTPS `Secure`. | Non | None / `'development'` | `'production'` |
| `ENV` | Alias alternatif pour définir le mode production (vérifié dans `__init__.py`). | Non | None | `'production'` |
| `SKIP_DB_CREATE_ALL` | Force l'omission de `db.create_all()` au démarrage (`true`, `1`, `yes`). | Non | `'false'` | `'true'` |
| `SQLALCHEMY_DATABASE_URI`| Chaîne de connexion à la base de données SQLAlchemy. | Non | `'sqlite:///db.sqlite'` | `'sqlite:///db.sqlite'` |
| `LOG_LEVEL` | Niveau de sévérité minimal des journaux (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | Non | `'INFO'` | `'INFO'` |
| `MAIL_SERVER` | Hôte du serveur SMTP d'envoi d'e-mails (validation, alertes, notifications). | Non | None | `'smtp.gmail.com'` |
| `MAIL_PORT` | Port d'écoute du serveur SMTP. | Non | `465` | `465` |
| `MAIL_USERNAME` | Identifiant de connexion SMTP et adresse de l'expéditeur système. | Non | None | `'contact@livresenclasse.com'` |
| `MAIL_PASSWORD` | Mot de passe d'authentification SMTP (ou mot de passe d'application). | Non | None | `'abcd efgh ijkl mnop'` |
| `MAIL_USE_TLS` | Activation du protocole STARTTLS. | Non | `False` | `False` |
| `MAIL_USE_SSL` | Activation du protocole SSL direct. | Non | `True` | `True` |
| `CONTACT_EMAIL` | Adresse e-mail de contact déclarée dans le User-Agent auprès d'Open Library. | Non | `MAIL_USERNAME` | `'support@livresenclasse.com'` |
| `BASE_URL` | URL racine publique du site utilisée pour composer les liens absolus dans les e-mails de campagne. | Non | Dérivé de la requête hôte | `'https://livresenclasse.com'` |
| `APP_URL` | Alias alternatif pour `BASE_URL`. | Non | None | `'https://livresenclasse.com'` |
| `GOOGLE_BOOK_API_KEY` | Clé d'API Google Cloud pour relever le quota de requêtes sur Google Books. | Non | None (mode anonyme) | `'AIzaSyD-1234567890abcdef'` |
| `CF_TOCKEN` | Jeton d'authentification Cloudflare Zero Trust pour lancer le conteneur `cloudflared`. *(Note: orthographe historique avec CK).* | **Oui** (en prod) | None | `'eyJhIjoiY2...12345'` |
| `CF_TOKEN` | Nom standardisé du jeton Cloudflare Tunnel (injecté dans l'environnement du conteneur). | Non | None | `'eyJhIjoiY2...12345'` |
| `HCAPTCHA_SITE_KEY` | Clé publique du widget anti-bot hCaptcha injectée dans les templates HTML. | Non | `''` (désactivé) | `'10000000-ffff-ffff-ffff-1234567890ab'` |
| `HCAPTCHA_SECRET_KEY` | Clé secrète de vérification côté serveur envoyée à l'API hCaptcha. | Non | `''` (validation contournée) | `'0x0000000000000000000000000000000000000000'` |
| `STRIPE_PUBLIC_KEY` | Clé publiable Stripe (`pk_...`) pour initialiser Stripe Elements ou Checkout. | Non | None | `'pk_live_51...1234'` |
| `STRIPE_SECRET_KEY` | Clé secrète Stripe (`sk_...`) pour exécuter les opérations de facturation serveur. | Non | None | `'sk_live_51...abcd'` |
| `STRIPE_WEBHOOK_SECRET` | Secret de signature des webhooks (`whsec_...`) pour authentifier les événements Stripe. | Non | None | `'whsec_1234567890abcdef...'` |
| `STRIPE_PRICE_MONTHLY` | Identifiant du tarif d'abonnement mensuel (5.- CHF/mois) créé dans Stripe. | Non | None | `'price_1Oxxxxxxxxxxxxxxxxxxxx'` |
| `STRIPE_PRICE_ID_MONTHLY` | Alias alternatif accepté pour `STRIPE_PRICE_MONTHLY`. | Non | None | `'price_1Oxxxxxxxxxxxxxxxxxxxx'` |
| `STRIPE_PRICE_YEARLY` | Identifiant du tarif d'abonnement annuel (30.- CHF/an) créé dans Stripe. | Non | None | `'price_1Pxxxxxxxxxxxxxxxxxxxx'` |
| `STRIPE_PRICE_ID_YEARLY` | Alias alternatif accepté pour `STRIPE_PRICE_YEARLY`. | Non | None | `'price_1Pxxxxxxxxxxxxxxxxxxxx'` |

---

## 3. Constantes applicatives et quotas métier (config_plans.py)

Les plafonds du modèle freemium et les règles de tarification sont centralisés dans [`project/config_plans.py`](../project/config_plans.py). Modifier ce fichier applique instantanément les changements à l'ensemble du site :

| Constante | Valeur par défaut | Description métier |
| :--- | :---: | :--- |
| `MAX_FREE_STUDENTS` | `40` | Nombre maximum d'élèves enregistrables sous la formule gratuite. |
| `MAX_FREE_BOOKS` | `500` | Nombre maximum de livres catalogables sous la formule gratuite. |
| `MAX_FREE_SCANS` | `30` | Quota de scans de codes-barres réussis autorisés par semaine pour les comptes gratuits. |
| `FREE_HISTORY_MONTHS` | `10` | Période d'historique des prêts consultable en clair en mode gratuit (les prêts antérieurs sont masqués par un flou bienveillant). |
| `TRIAL_PERIOD_DAYS` | `0` | Durée de la période d'essai automatique accordée aux nouveaux inscrits (en jours). |
| `DEFAULT_CURRENCY` | `'CHF'` | Devise d'affichage et de facturation (Franc suisse). |
| `PRICE_MONTHLY_AMOUNT` | `5.0` | Tarif mensuel TTC en Francs suisses (5.00 CHF). |
| `PRICE_YEARLY_AMOUNT` | `30.0` | Tarif annuel TTC en Francs suisses (30.00 CHF). |
| `GAUGE_WARNING_PERCENT` | `80` | Seuil (en %) à partir duquel les barres de progression de quotas passent en alerte visuelle jaune/orange. |

---

## 4. Configuration des sessions et cookies de sécurité

Dans [`project/__init__.py`](../project/__init__.py), les cookies d'authentification et de session bénéficient d'un durcissement conforme aux recommandations OWASP :

```python
is_prod = os.getenv("FLASK_ENV") == "production"

# Cookie de session Flask
app.config["SESSION_COOKIE_SECURE"] = is_prod  # Transmis uniquement sur HTTPS en prod
app.config["SESSION_COOKIE_HTTPONLY"] = (
    True  # Inaccessible via document.cookie (anti-XSS)
)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Protection CSRF native

# Cookie de reconnexion automatique "Se souvenir de moi"
app.config["REMEMBER_COOKIE_SECURE"] = is_prod
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

# Durées de vie
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Session active 7 jours
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)  # Mémorisation 30 jours
app.config["REMEMBER_COOKIE_REFRESH_EACH_REQUEST"] = True  # Renouvellement glissant
```

---

## 5. Journalisation et niveaux de logs

* **Fichier de journalisation** : `logs/app.log`.
* **Rotation automatique** : Gérée par un `RotatingFileHandler` d'une taille maximale de **1 Mo**, conservant **10 fichiers d'archives** compressés/tournants (`app.log.1`, etc.).
* **Format des lignes** : `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.
* **Alerte d'incident critique** : La classe `MailCriticalHandler` intercepte automatiquement tout événement de niveau `CRITICAL` ou `ERROR` (notamment les exceptions HTTP 500 non interceptées) et envoie la stacktrace détaillée à `MAIL_USERNAME`.

---

## 6. Questions ouvertes

* [ ] **Unification de `CF_TOCKEN` et `CF_TOKEN`** : Il est recommandé de standardiser `CF_TOKEN` dans le fichier `.env.example` et le `docker-compose.yml` pour éviter toute confusion lors d'un déploiement sur une nouvelle machine.
