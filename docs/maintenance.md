# Guide de Maintenance et Résolution des Pannes - Livres en Classe

Ce document décrit les opérations d'exploitation courantes, l'exécution des scripts de maintenance en ligne de commande, la résolution des anomalies fréquentes et les points de supervision de **Livres en Classe**.

---

## Sommaire

1. [Scripts de maintenance en ligne de commande (CLI)](#1-scripts-de-maintenance-en-ligne-de-commande-cli)
2. [Administration des utilisateurs et des quotas](#2-administration-des-utilisateurs-et-des-quotas)
3. [Mise à jour des catalogues de traductions (i18n)](#3-mise-à-jour-des-catalogues-de-traductions-i18n)
4. [Guide de résolution des problèmes fréquents (Troubleshooting)](#4-guide-de-résolution-des-problèmes-fréquents-troubleshooting)
   * [1. La caméra ne se lance pas sur la page de scan](#1-la-caméra-ne-se-lance-pas-sur-la-page-de-scan)
   * [2. Erreur SQLite "database is locked"](#2-erreur-sqlite-database-is-locked)
   * [3. Échec de validation du Webhook Stripe (Erreur 400)](#3-échec-de-validation-du-webhook-stripe-erreur-400)
   * [4. Les nouvelles traductions ne s'affichent pas](#4-les-nouvelles-traductions-ne-saffichent-pas)
   * [5. Le quota de scans augmente alors qu'aucun livre n'est trouvé](#5-le-quota-de-scans-augmente-alors-quaucun-livre-nest-trouvé)
5. [Points de supervision et monitoring](#5-points-de-supervision-et-monitoring)
6. [Questions ouvertes](#6-questions-ouvertes)

---

## 1. Scripts de maintenance en ligne de commande (CLI)

Le dossier [`scripts/`](../scripts) regroupe les utilitaires administratifs exécutables manuellement ou via cron.

### Exécution sous Docker
Toutes les commandes ci-dessous peuvent être lancées au sein du conteneur applicatif en production :
```bash
docker-compose exec flask python scripts/<nom_du_script>.py
```

### 1. `reset_weekly_scans.py`
Réinitialise manuellement le compteur `free_scans_used` à 0 pour tous les utilisateurs du plan gratuit dont la période a expiré (secours au cas où le scheduler d'arrière-plan n'aurait pas tourné) :
```bash
python scripts/reset_weekly_scans.py
```

### 2. `send_trial_ending_reminders.py`
Identifie les enseignants dont la période d'essai gratuit se termine dans 7 jours (J-7) ou dans 24 heures (J-1) et leur envoie un e-mail courtois de rappel sans les bloquer :
```bash
python scripts/send_trial_ending_reminders.py
```

### 3. `cleanup_bots.py`
Purge interactivement les comptes suspects créés par des robots ayant réussi à contourner le formulaire sans jamais enregistrer le moindre livre ni élève :
```bash
python scripts/cleanup_bots.py
```

### 4. `send_founder_announcement.py`
Envoie un e-mail officiel aux utilisateurs historiques enregistrés sous le statut permanent `founder` pour leur annoncer leur accès gratuit à vie sans restriction :
```bash
python scripts/send_founder_announcement.py
```

### 5. `verify_all_users.py`
Passe le statut `is_verified` à `True` pour tous les comptes existants en base (utilitaire de migration) :
```bash
python scripts/verify_all_users.py
```

### 6. `verify_seo_live.py`
Sonde l'ensemble des routes internationales et techniques (`/sitemap.xml`, `/fr/...`, `/en/...`, `/de/...`) pour vérifier les codes HTTP de réponse, la présence des balises canoniques et des balises `hreflang` :
```bash
python scripts/verify_seo_live.py
```

---

## 2. Administration des utilisateurs et des quotas

### Gestion depuis l'interface Web Admin (`/<lang>/admin/users`)
Un administrateur connecté peut agir directement sur n'importe quel compte utilisateur sans manipuler la base SQLite :
* **Changer de plan** : Basculer un utilisateur en `free`, `premium`, ou lui conférer le statut permanent `founder`.
* **Remise à zéro des scans** : Réinitialiser instantanément le compteur de scans hebdomadaires d'un enseignant bloqué.
* **Prolonger la période d'essai** : Modifier la durée `trial_days_left`.

### Quotas dynamiques & Politique de non-destruction des données
* **Libération de place immédiate** : Si un enseignant sur le plan gratuit atteint le plafond de 40 élèves ou 500 livres, la suppression d'un élément libère instantanément une place en base pour en ajouter un nouveau.
* **Comptes expirés** : Si un abonnement Premium arrive à son terme, aucun livre ni élève n'est supprimé ou masqué. L'enseignant conserve l'accès complet en consultation et retour d'emprunts ; seule l'addition de nouveaux éléments au-delà des plafonds gratuits est bloquée.

---

## 3. Mise à jour des catalogues de traductions (i18n)

Lorsque vous ajoutez ou modifiez des chaînes de caractères traduites dans les fichiers Python (`_("...")`) ou dans les gabarits Jinja2 (`{{ _("...") }}`), exécutez impérativement la chaîne de compilation suivante :

```powershell
# 1. Extraire les nouvelles chaînes dans le modèle template .pot
.venv\Scripts\pybabel extract -F babel.cfg -o project\translations\messages.pot .

# 2. Fusionner avec les fichiers .po existants (sans écraser les traductions en place)
.venv\Scripts\pybabel update -i project\translations\messages.pot -d project\translations

# 3. Remplir automatiquement le fichier français (source)
.venv\Scripts\python scripts\fill_fr_translations.py

# 4. Mettre à jour les dictionnaires anglais et allemand si nécessaire
.venv\Scripts\python scripts\fill_en_translations.py
.venv\Scripts\python scripts\fill_de_translations.py

# 5. Compiler les binaires .mo obligatoires pour le chargement au runtime
.venv\Scripts\pybabel compile -d project\translations
```

> [!IMPORTANT]
> Les fichiers `.mo` compilés **doivent être commités dans Git** : la pipeline GitHub Actions bloque les Pull Requests si les `.mo` ne sont pas synchronisés avec les fichiers `.po`.

---

## 4. Guide de résolution des problèmes fréquents (Troubleshooting)

### 1. La caméra ne se lance pas sur la page de scan

* **Symptôme** : Écran noir ou message d'erreur d'autorisation sur `/livre/scann`.
* **Cause** : Pour des raisons de sécurité strictes, les navigateurs modernes (Chrome, Safari, Firefox) interdisent l'accès aux APIs de caméra (`navigator.mediaDevices.getUserMedia`) si la page n'est pas servie sur un contexte sécurisé HTTPS (ou sur `localhost`).
* **Résolution** :
  * **En développement local** : Lancer Flask avec un certificat SSL ad-hoc :
    ```powershell
    flask run -p 80 -h 0.0.0.0 --cert adhoc
    ```
  * **En production** : Vérifier que le tunnel Cloudflare achemine bien le trafic en HTTPS avec un certificat valide sur votre nom de domaine.

### 2. Erreur SQLite "database is locked"

* **Symptôme** : Erreur 500 avec message `sqlite3.OperationalError: database is locked`.
* **Cause** : Concurrence d'accès entre plusieurs workers Gunicorn tentant d'écrire simultanément dans SQLite en mode journal standard.
* **Résolution** :
  1. Activer le mode **WAL (Write-Ahead Logging)** qui autorise les lectures concurrentes pendant une écriture :
     ```bash
     sqlite3 instance/db.sqlite "PRAGMA journal_mode=WAL;"
     ```
  2. Vérifier les permissions du répertoire `instance/` (le processus Flask doit avoir le droit d'écrire et de créer des fichiers temporaires `.sqlite-wal` et `.sqlite-shm`) :
     ```bash
     chmod -R 775 instance/
     ```

### 3. Échec de validation du Webhook Stripe (Erreur 400)

* **Symptôme** : Le tableau de bord Stripe indique des erreurs HTTP 400 sur `https://livresenclasse.com/webhook/stripe`.
* **Cause** : Incohérence entre la clé secrète configurée dans `STRIPE_WEBHOOK_SECRET` et la clé de signature du endpoint Stripe, ou corps de requête altéré par un middleware.
* **Résolution** :
  1. Vérifier sur le tableau de bord Stripe (rubrique **Développeurs** > **Webhooks**) que l'URL enregistrée est bien `https://livresenclasse.com/webhook/stripe`.
  2. Révéler le secret de signature (`whsec_...`) et le copier dans le `.env` de production.
  3. Redémarrer le conteneur Flask (`docker-compose restart flask`).

### 4. Les nouvelles traductions ne s'affichent pas

* **Symptôme** : Les textes modifiés restent dans l'ancienne version ou s'affichent en anglais/français brut sans prise en compte de la locale.
* **Cause** : Flask-Babel charge exclusivement les fichiers binaires `.mo`. Si vous modifiez uniquement un fichier `.po` sans recompiler, les modifications sont ignorées.
* **Résolution** :
  ```bash
  pybabel compile -d project/translations
  docker-compose restart flask
  ```

### 5. Le quota de scans augmente alors qu'aucun livre n'est trouvé

* **Symptôme** : Scanner un code-barres inconnu débite le compteur hebdomadaire de scans d'un compte gratuit.
* **Résolution appliquée** : L'incrémentation a été déplacée :
  * Si le livre est présent dans la classe, `livre_exist` valide et incrémente.
  * Si le livre n'est pas présent, le code est placé en session temporaire. Le débit n'intervient dans `livre_ajout` **que si l'une des APIs (Google Books, BnF, Open Library) parvient à identifier le livre**. En cas d'échec total, aucun quota n'est déduit.

---

## 5. Points de supervision et monitoring

1. **Tableau de bord administrateur (`/<lang>/admin`)** :
   * Nombre total d'utilisateurs inscrits, actifs et vérifiés.
   * Répartition des formules (`free`, `premium`, `founder`).
   * Total des livres catalogués et des emprunts actifs dans toutes les classes.
   * Taux d'ouverture et d'acheminement des campagnes d'e-mails.
2. **Surveillance des journaux d'erreurs** :
   * Consulter les dernières anomalies :
     ```bash
     tail -n 100 logs/app.log
     ```
   * Vérifier l'état du thread scheduler :
     ```bash
     cat instance/.scheduler_last_run.json
     ```
3. **Alertes e-mail automatiques** :
   * Grâce à `MailCriticalHandler`, toute exception non interceptée déclenche immédiatement l'envoi d'un e-mail d'alerte avec la stacktrace complète à l'adresse renseignée dans `MAIL_USERNAME`.

---

## 6. Questions ouvertes

* [ ] **Mode WAL activé par défaut** : Envisager d'exécuter automatiquement `PRAGMA journal_mode=WAL;` lors de l'initialisation de la base SQLite dans `create_app()` pour optimiser les performances de concurrence par défaut.
