# Guide de contribution — LivresEnClasse.com

Merci de l'intérêt que vous portez au projet **LivresEnClasse.com** (Bibliothèque-Flask). Ce document présente les règles, outils et conventions nécessaires pour contribuer efficacement à la code base.

---

## 1. Cadre légal & Licence

Le projet est distribué sous licence **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**.
Toute contribution (code, documentation, correctif) est soumise aux conditions de cette licence :
- **Autorisé** : Usage personnel, éducatif, pédagogique, associatif et contributions communautaires non commerciales.
- **Interdit** : Toute exploitation commerciale, monétisation, revente ou hébergement SaaS payant concurrent sans accord écrit préalable.

En soumettant une Pull Request, vous acceptez que vos contributions soient intégrées sous ces termes.

---

## 2. Configuration de l'environnement de développement

### Prérequis
- **Python 3.12** (version recommandée et alignée avec la CI GitHub Actions)
- **Git**
- *(Optionnel)* **Docker** et **Docker Compose** pour tester l'environnement conteneurisé.

### Installation locale pas-à-pas

```bash
# 1. Cloner le dépôt
git clone https://github.com/Forestierr/Bibliotheque-Flask.git
cd Bibliotheque-Flask

# 2. Créer et activer l'environnement virtuel
# Sur Linux / macOS :
python -m venv venv
source venv/bin/activate
# Sur Windows (PowerShell) :
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Installer les dépendances applicatives et d'outillage
pip install --upgrade pip
pip install -r project/requirements.txt
pip install ruff pytest

# 4. Configurer les variables d'environnement
cp .env.example .env

# 5. Initialiser la base de données SQLite locale
export FLASK_APP=project   # Sous Windows: $env:FLASK_APP="project"
flask db upgrade

# 6. Lancer le serveur local
flask run -p 5000 -h 127.0.0.1
```

> **Astuce caméra & scan :** Pour tester la caméra du scanner de code-barres sur mobile ou réseau local, les navigateurs exigent HTTPS. Lancez le serveur avec un certificat ad-hoc :
> `flask run -p 5000 -h 0.0.0.0 --cert adhoc`

---

## 3. Normes de code & Formatage (Ruff)

Nous utilisons **[Ruff](https://docs.astral.sh/ruff/)** pour assurer un formatage homogène et un linting strict du code Python.

Avant tout commit, appliquez systématiquement :

```bash
# Formater automatiquement le code
ruff format project/

# Analyser et corriger les erreurs de linting
ruff check project/

# Pour appliquer automatiquement les correctifs suggérés par le linter :
ruff check --fix project/
```

> **Attention :** Le workflow de validation CI (`pr-validation.yml`) exécute `ruff format --check project/` et `ruff check project/`. Toute infraction de style bloquera la Pull Request.

---

## 4. Internationalisation (Flask-Babel) — Étape critique CI ⚠️

L'application supporte le français (`fr`), l'anglais (`en`) et l'allemand (`de`).
Toute nouvelle chaîne visible dans un template HTML ou message Python (`flash`) doit être marquée pour traduction :

- **Dans un template Jinja2** : `{{ _("Mon texte") }}`
- **Dans un fichier Python** : `from flask_babel import gettext as _` puis `_("Mon message")`

### Pipeline de mise à jour des traductions

Lorsque vous ajoutez ou modifiez des chaînes traduites :

```bash
# 1. Extraire les nouvelles chaînes dans le template .pot
pybabel extract -F babel.cfg -o project/translations/messages.pot .

# 2. Fusionner avec les fichiers .po existants
pybabel update -i project/translations/messages.pot -d project/translations

# 3. (Optionnel) Exécuter les scripts de remplissage si nécessaire
python scripts/fill_fr_translations.py

# 4. COMPILATION OBLIGATOIRE (binaire .mo)
pybabel compile -d project/translations
```

> **🚨 RÈGLE D'OR CI :**  
> Les fichiers binaires compilés `.mo` (`project/translations/<lang>/LC_MESSAGES/messages.mo`) **DOIVENT être commiés** avec vos modifications.  
> La CI GitHub Actions vérifie via `git status` qu'aucun `.mo` n'a été oublié. Si les fichiers `.mo` ne sont pas à jour avec les `.po`, **la CI échoue immédiatement**.

---

## 5. Exécution des tests automatisés (Pytest)

Le projet dispose d'une suite de tests complète couvrant les blueprints, l'authentification, les emprunts, les quotas freemium et Stripe.

```bash
# Lancer l'intégralité de la suite de tests
pytest project/test/

# Lancer un module de test spécifique
pytest project/test/test_livre.py

# Afficher les sorties détaillées et les logs
pytest -v -s project/test/
```

Tous les tests doivent être au vert (`passed`) avant l'ouverture d'une Pull Request.

---

## 6. Workflow Git et Pull Requests

1. **Créer une branche dédiée** :
   ```bash
   git checkout -b feature/nom-de-la-fonctionnalite
   # ou
   git checkout -b fix/description-du-correctif
   ```
2. **Écrire des commits clairs et atomiques** :
   - Utilisez des messages explicites en français ou en anglais (ex : `feat(scan): ajout du support BnF Dublin Core`, `fix(quota): blocage de l'incrémentation en cas d'échec de scan`).
3. **Checklist avant de pousser vos commits** :
   - [ ] `ruff format project/` exécuté sans modification résiduelle.
   - [ ] `ruff check project/` ne remonte aucun avertissement ni erreur.
   - [ ] `pybabel compile -d project/translations` exécuté et `.mo` commiés si vous avez touché aux traductions ou templates.
   - [ ] `pytest project/test/` passe à 100%.
   - [ ] Aucun secret ni fichier sensible commité (`.env`, `instance/db.sqlite`, logs).
4. **Ouvrir une Pull Request** :
   - Décrivez précisément le contexte, le problème résolu et les tests manuels effectués.
   - Si votre travail est en cours, ouvrez-la en mode **Draft** (la CI s'exécutera une fois marquée *Ready for review*).
   - Surveillez les statuts d'exécution de `PR Validation` sur GitHub.
