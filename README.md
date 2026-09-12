# Bibliothèque flask

[English version](README.en.md)

<strong>Ma bibliothèque</strong> est une application web spécialement conçue pour répondre aux
besoins des enseignants dans la gestion de leur bibliothèque de classe. Cette plateforme
intuitive leur permet de centraliser et d’organiser facilement leur collection de livres.
Ils ont la possibilité d’ajouter de nouveaux ouvrages, de modifier les informations existantes
ou de supprimer des livres qui ne sont plus nécessaires. En outre, l'application offre un suivi
détaillé des emprunts effectués par leurs élèves, leur permettant de savoir quels livres ont été
empruntés, par qui et pour combien de temps. Grâce à LivresEnClasse.com, les enseignants peuvent
ainsi encourager la lecture tout en gardant une vue d’ensemble claire et précise sur
l’utilisation des ressources de leur bibliothèque.

## Caractéristiques

- Ajouter, supprimer, modifier un livre
- Ajouter, supprimer, modifier un élève
- Scanner le code-barres d'un livre
- Gestion des emprunts
- Connexion / déconnexion

## Installation

### Créer un environnement virtuel

```bash
python -m venv venv
source venv/bin/activate
```

Puis installer les dépendances :

```bash
pip install -r project/requirements.txt
```

Modifiez le fichier `.env' pour définir les variables d'environnement.
Le fichier `.env.example` contient toutes les valeurs par défaut, il vous suffit de copier le fichier et d'ajouter vos propres valeurs. 
copier le fichier et ajouter vos propres valeurs.

```bash
cp .env.example .env
```

### Création de la base de données

```bash
flask db init
flask db migrate
flask db upgrade
```

> [!TIP]
> Vous pouvez utiliser la commande `flask db --help` pour voir toutes les commandes disponibles.

### Mise à jour de la base de données

Si vous modifiez le modèle de données, vous devez mettre à jour la base de données.

```bash
flask db migrate -m "message"
flask db upgrade
```

### Lancer le serveur

```bash
$env:FLASK_APP = "project"
flask run -p 80 -h 0.0.0.0
```

And go to http://127.0.0.1:80

> [!TIP]
> Vous pouvez utiliser `flask run --help` pour voir toutes les options disponibles.

> [!CAUTION]
> Flask ne lance pas de serveur WSGI, vous devez utiliser un serveur WSGI de production comme Gunicorn.

Si vous avez des problèmes lors du developpement avec le scann.
Il se peut que vous deviez utiliser un server en HTTPS.
Pour cela, vous pouvez utiliser le flag  `--cert=adhoc`.


## Intégration Stripe & Tests Locaux avec Stripe CLI

L'application intègre Stripe Checkout et le Portail Client Stripe (Customer Portal) pour la formule d'abonnement Premium.

### 1. Variables d'environnement (.env)

Renseignez vos identifiants de test dans le fichier `.env` :

```bash
STRIPE_PUBLIC_KEY='pk_test_...'
STRIPE_SECRET_KEY='sk_test_...'
STRIPE_WEBHOOK_SECRET='whsec_...'
STRIPE_PRICE_MONTHLY='price_...'  # ID du tarif mensuel (5.- CHF/mois)
STRIPE_PRICE_YEARLY='price_...'   # ID du tarif annuel (30.- CHF/an)
```

> [!NOTE]
> Les variables `STRIPE_PRICE_ID_YEARLY` et `STRIPE_PRICE_ID_MONTHLY` sont également acceptées pour assurer une compatibilité totale.

### 2. Installer la Stripe CLI

La **Stripe CLI** permet de rediriger les événements de paiement de Stripe directement vers votre serveur Flask local sans configuration de tunnel tiers.

- **Windows** :
  - Via Scoop : `scoop install stripe`
  - Via Chocolatey : `choco install stripe-cli`
  - Ou téléchargez le binaire `stripe.exe` depuis [GitHub Releases](https://github.com/stripe/stripe-cli/releases).
- **macOS** :
  ```bash
  brew install stripe/stripe-cli/stripe
  ```
- **Linux** :
  Téléchargez le paquet `.deb` ou `.rpm` depuis les releases officielles Stripe.

### 3. Authentifier la CLI

Connectez la CLI à votre compte Stripe de test :

```bash
stripe login
```

Suivez les instructions du terminal pour valider l'authentification dans votre navigateur.

### 4. Rediriger les Webhooks vers votre serveur local

Lancez la commande d'écoute en spécifiant le port de votre serveur Flask (par défaut 5000) :

```bash
stripe listen --forward-to localhost:5000/webhook/stripe
```

La CLI affichera immédiatement une clé de signature de test, par exemple :
```text
> Ready! Your webhook signing secret is whsec_1234567890abcdef...
```

Copiez cette valeur `whsec_...` et collez-la dans votre fichier `.env` :
```bash
STRIPE_WEBHOOK_SECRET='whsec_1234567890abcdef...'
```
Puis redémarrez votre serveur Flask pour qu'il prenne en compte le secret.

### 5. Simuler les événements Stripe (Déclenchement CLI)

Ouvrez un second terminal pour déclencher des simulations d'événements Stripe :

- **Paiement réussi & Activation de l'abonnement** :
  ```bash
  stripe trigger checkout.session.completed
  ```
- **Mise à jour d'un abonnement existant** :
  ```bash
  stripe trigger customer.subscription.updated
  ```
- **Résiliation d'abonnement (avec délai de grâce 48h et e-mail)** :
  ```bash
  stripe trigger customer.subscription.deleted
  ```
- **Échec de prélèvement (alerte e-mail de carte)** :
  ```bash
  stripe trigger invoice.payment_failed
  ```

### 6. Tester le paiement dans le navigateur (Cartes de test Stripe)

- Rendez-vous sur la page des tarifs : `http://localhost:5000/tarifs`
- Cliquez sur "Souscrire pour 30.- CHF / an" ou "Choisir la formule mensuelle" pour accéder au récapitulatif `/paiement`.
- Cliquez sur "Procéder au paiement sécurisé" pour être redirigé vers Stripe Checkout.
- Après validation, vous êtes automatiquement redirigé vers la page de félicitations `/subscription/success` et votre classe passe en Premium illimité.

#### Cartes de test fournies par Stripe

Le mode test (avec vos clés `sk_test_...`) est un environnement totalement déconnecté du réseau bancaire réel. Pour valider vos paiements et tester le bon fonctionnement de votre intégration, vous devez utiliser exclusivement les numéros de cartes fictives fournis par Stripe :

- **Paiement réussi (la plus utilisée)** : `4242 4242 4242 4242`
- **Paiement refusé (fonds insuffisants)** : `4000 0000 0000 0002`
- **Paiement refusé (carte perdue/volée)** : `4000 0000 0000 0022`
- **Paiement nécessitant une authentification 3D Secure** : `4000 0000 0000 3020`

Pour la date d'expiration, entrez simplement n'importe quelle date dans le futur (par exemple `12/30`).  
Pour le CVC, tapez n'importe quels 3 chiffres (par exemple `123`).

### 7. Portail Client (Customer Portal)

Un utilisateur Premium peut gérer ses coordonnées bancaires, télécharger ses factures ou résilier à tout moment :
- Directement via la route : `http://localhost:5000/portail-abonne`
- Ou depuis le bouton "Gérer mon abonnement" dans les Réglages (`/reglage`) et la page `/tarifs`.

### 8. Idempotence & Exemption CSRF

- **Exemption CSRF** : Le endpoint `/webhook/stripe` est automatiquement exempté de la vérification de jeton CSRF de Flask-WTF (`@csrf.exempt`) afin d'accepter les requêtes HTTP signées provenant de Stripe.
- **Idempotence** : Si Stripe envoie plusieurs fois le même événement `checkout.session.completed` ou `customer.subscription.updated`, le serveur détecte l'état existant et ne produit aucune modification redondante en base de données.



## Tests et Qualité du code (CI/CD)

Pour que votre code soit accepté lors d'une Pull Request (PR), il doit respecter les standards de formatage et passer tous les tests automatisés. Si ces vérifications échouent, la PR sera bloquée.

### Formater et vérifier le code (Ruff)

Nous utilisons **Ruff** pour le linting (vérification des erreurs) et le formatage du code.

- **Formater automatiquement le code** (à faire avant de commit) :
  ```bash
  ruff format project/
  ```
- **Vérifier les erreurs de style et de lint** :
  ```bash
  ruff check project/
  ```

### Lancer les tests (Pytest)

Assurez-vous que tous les tests réussissent avant de soumettre vos changements :

```bash
pytest project/test/
```


## Publication

Pour publier l'application, j'ai décider d'utiliser [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
, nginx et gunicorn. Cela me permet de publier l'application sur mon serveur personnel et de la rendre accessible sous
un nom de domaine personnalisé [Cloudflare Registrar](https://www.cloudflare.com/fr-fr/products/registrar/).

Pour cela je me suis inspiré de l'article de blog de [austinsnerdythings](https://austinsnerdythings.com/2023/11/01/using-github-actions-to-deploy-a-flask-nginx-cloudflared-tunnel-docker-compose-stack/).
Mais sans utiliser GitHub Actions, libre à vous de l'utiliser.

> [!CAUTION]
> AVERTISSEMENT SUR LA SÉCURITÉ
> Cette solution ne rend pas automatiquement votre application sûre. Vous devez toujours vous concentrer sur la sécurité. Toute vulnérabilité dans votre application web peut permettre à un attaquant de prendre pied dans votre réseau. Votre hôte Docker doit être isolé du reste de votre réseau par un pare-feu, dans un premier temps, afin d'empêcher toute intrusion dans d'autres ordinateurs/services/systèmes de votre réseau. Toutes les étapes suivantes devraient être axées sur les vecteurs d'attaque habituels (injection SQL, mise à jour des systèmes, etc.).

### Shéma de l'infrastructure

![Infrastructure schema](docs/infrastructure.png)

### Lancer l'application

Premièrement, vous devez créer un fichier `docker-compose.yml` à la racine du projet.

```yaml
command: tunnel --no-autoupdate run --token ${CF_TOCKEN}
```

En remplaçant `${CF_TOCKEN}` par votre token Cloudflare.

### Build et lancer l'application

```bash
docker-compose up --build
```

> [!TIP]
> Vous pouvez utiliser l'option `-d` pour lancer les conteneurs en arrière-plan.

### Arrêter l'application

```bash
docker-compose down
```

## Base de données

La base de données est une base de données SQLite. Stockée dans le fichier `instance\db.sqlite`.

### Schéma de la base de données

![Database schema](docs/model.png)

_**User** est un professeur._

## Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE.md) pour plus de détails.

