# Guide Opérationnel Pinterest & Tracking Matomo — Lead Magnets "Livres en Classe"

Ce guide détaille le plan d'action pas à pas pour déployer votre stratégie Pinterest (Étape 2), animer vos tableaux, publier vos épingles à fort engagement et analyser votre trafic grâce aux objectifs Matomo.

---

## Sommaire

1. [Configuration du Compte Pinterest Business](#1-configuration-du-compte-pinterest-business)
2. [Architecture des 4 Tableaux Thématiques (SEO Pinterest)](#2-architecture-des-4-tableaux-thématiques-seo-pinterest)
3. [Kit d'Épingles Prêtes à l'Emploi (Titres, Descriptions, Tags Matomo)](#3-kit-dépingles-prêtes-à-lemploi)
4. [Configuration des 3 Objectifs (Goals) dans Matomo](#4-configuration-des-3-objectifs-goals-dans-matomo)
5. [Calendrier & Rythme de Publication (1 à 2 épingles / semaine)](#5-calendrier--rythme-de-publication)

---

## 1. Configuration du Compte Pinterest Business

### A. Créer ou convertir son compte (100% gratuit)
1. Rendez-vous sur [pinterest.com/business/create](https://www.pinterest.com/business/create/).
2. Nom de profil recommandé : **Livres en Classe | Outils & Gestion Bibliothèque de Classe**
3. Photo de profil : Logo carré haute résolution (`logo-w-512x512.png`).
4. Bio de profil :
   > *Outils gratuits et imprimables pour enseignants du primaire (CP à CM2) : marque-pages, diplômes, affiches et application de gestion de bibliothèque de classe par scan de codes-barres.*

### B. Revendiquer votre site web (`livresenclasse.com`)
1. Dans vos paramètres Pinterest > **Comptes revendiqués** (Claimed accounts) > **Sites web** > Cliquez sur **Revendiquer**.
2. Choisissez l'option **Ajouter une balise HTML**.
3. Pinterest vous fournit une balise du type :
   ```html
   <meta name="p:domain_verify" content="VOTRE_CODE_PINTEREST" />
   ```
4. Insérez cette balise dans le bloc `<head>` de `project/templates/base.html`.
5. Validez sur Pinterest. En quelques heures, une icône de globe vérifié apparaîtra à côté de votre URL de profil, ce qui améliore la distribution algorithmique de vos épingles.

---

## 2. Architecture des 4 Tableaux Thématiques (SEO Pinterest)

Créez ces 4 tableaux sur votre profil. Remplissez scrupuleusement les descriptions pour que l'algorithme de recherche Pinterest indexe vos tableaux sur les requêtes enseignantes courantes.

### Tableau 1 : Bibliothèque de classe & BCD primaire
- **Titre** : `Bibliothèque de classe & BCD école primaire`
- **Description** :
  > *Idées d'aménagement pour le coin lecture, gestion de la bibliothèque de classe, rituels de prêt de livres en primaire (maternelle, CP, CE1, CE2, CM1, CM2), charte de classe, étiquettes de bacs et fiches d'emprunt.*
- **Contenu à y épingler** : Marque-pages, charte du coin lecture, étiquettes de bacs, fiches coup de cœur.

### Tableau 2 : Rallye lecture & Défis littéraires (CP-CM2)
- **Titre** : `Rallye lecture & Défis de lecture (CP à CM2)`
- **Description** :
  > *Ressources pédagogiques pour animer un rallye lecture en classe : diplômes de lecture à imprimer, fiches de suivi d'emprunt, défis lecture des vacances, passeports de lecteur et idées pour donner le goût de lire aux enfants.*
- **Contenu à y épingler** : Diplôme de lecture, défi bingo lecture, passeport de lecteur.

### Tableau 3 : Outils & Imprimables gratuits pour enseignants
- **Titre** : `Imprimables gratuits pour prof des écoles (TeamPE)`
- **Description** :
  > *Fiches et outils prêts à imprimer au format A4 pour les enseignants : marque-pages personnalisables, diplômes d'encouragement, affiches de classe et matériel pour simplifier la vie de classe au quotidien.*
- **Contenu à y épingler** : Tous vos formats imprimables gratuits.

### Tableau 4 : Donner le goût de lire aux enfants
- **Titre** : `Donner le goût de lire aux enfants & Littérature jeunesse`
- **Description** :
  > *Sélections de livres jeunesse, astuces de lecture offerte, recommandations de lecture entre pairs, fiches avis coup de cœur et activités littéraires pour susciter l'autonomie et le plaisir de lire dès le CP.*
- **Contenu à y épingler** : Fiches coup de cœur, articles du blog (meilleurs livres CP, donner envie de lire).

---

## 3. Kit d'Épingles Prêtes à l'Emploi

Pour chaque épingle :
- Téléversez l'image verticale 1000×1500px située dans `project/static/image/pinterest/`.
- Copiez-collez le titre et la description ci-dessous.
- Renseignez le **Lien de destination tagué Matomo** (crucial pour le suivi des retours).

---

### Épingle 1 — Marque-pages d'emprunt & Fiche d'avis

- **Visuel** : `project/static/image/pinterest/marque-pages-a-imprimer.png` (1000×1500 px)
- **Tableau conseillé** : *Bibliothèque de classe & BCD école primaire* OU *Imprimables gratuits pour prof des écoles*
- **Titre de l'épingle** :
  ```text
  Marque-pages à imprimer gratuits | Suivi d'emprunt & Avis de lecture A4
  ```
- **Description de l'épingle** :
  ```text
  Un outil 2-en-1 indispensable pour votre bibliothèque de classe ou BCD ! 

  📚 4 marque-pages par page A4 prêts à imprimer :
  • Recto : fiche d'emprunt avec tableau de dates pour responsabiliser les élèves.
  • Verso : avis critique de lecture avec étoiles à colorier pour encourager les recommandations entre pairs.

  ✨ 100% personnalisable en ligne : modifiez le nom de votre classe et vos textes en direct avant d'imprimer ou d'enregistrer en PDF.

  #TeamPE #ProfDesEcoles #Cycle2 #Cycle3 #BibliothequeDeClasse #RallyeLecture #CoinLecture #ImprimableGratuit #EnseignantPrimaire
  ```
- **Lien de destination** :
  ```text
  https://livresenclasse.com/fr/ressources/marque-pages-a-imprimer?mtm_source=pinterest&mtm_medium=social&mtm_campaign=lead_magnets&mtm_content=marque_pages
  ```

---

### Épingle 2 — Diplôme de lecture personnalisé

- **Visuel** : `project/static/image/pinterest/diplome-de-lecture-a-imprimer.png` (1000×1500 px)
- **Tableau conseillé** : *Rallye lecture & Défis littéraires (CP-CM2)*
- **Titre de l'épingle** :
  ```text
  Diplôme de lecture à imprimer gratuit | Champion de lecture CP CE1 CE2 CM1 CM2
  ```
- **Description de l'épingle** :
  ```text
  Valorisez les progrès et les victoires de lecture de vos élèves ! 🏆

  🎓 Diplôme officiel au format A4 paysage :
  • Idéal pour clôturer un rallye lecture ou célébrer les paliers franchis (5, 10, 20 livres lus).
  • 6 thèmes visuels soignés (Or prestige, bleu écolier, vert aventure, coloriage N&B).
  • Remplissage libre ou génération automatique pour toute votre classe en 1 clic.

  À télécharger et imprimer gratuitement sur Livres en Classe.

  #TeamPE #Cycle2 #Cycle3 #RallyeLecture #DiplomeLecture #LecturePrimaire #ProfDesEcoles #GestionDeClasse #Pedagogie
  ```
- **Lien de destination** :
  ```text
  https://livresenclasse.com/fr/ressources/diplome-de-lecture-a-imprimer?mtm_source=pinterest&mtm_medium=social&mtm_campaign=lead_magnets&mtm_content=diplome_lecture
  ```

---

### Épingle 3 — Fiches « Coup de cœur » & Fanions de recommandation

- **Visuel** : `project/static/image/pinterest/fiche-de-lecture-a-imprimer.png` (1000×1500 px)
- **Tableau conseillé** : *Donner le goût de lire aux enfants* OU *Bibliothèque de classe & BCD école primaire*
- **Titre de l'épingle** :
  ```text
  Fiches Coup de Cœur de lecture à imprimer | Recommandations de livres en classe
  ```
- **Description de l'épingle** :
  ```text
  Donnez envie de lire à vos élèves grâce aux conseils de leurs propres camarades ! 💡

  ❤️ Fanions cartonnés 4 par feuille A4 :
  • L'élève note le titre, l'auteur, sa note (étoiles) et ce qui lui a plu dans l'histoire.
  • Glissé dans l'ouvrage, le fanion dépasse de la tranche du livre en rayon pour attirer l'œil.
  • Un support ludique pour travailler l'expression écrite sans la lourdeur d'une fiche de lecture traditionnelle.

  Personnalisable et téléchargeable gratuitement au format PDF.

  #TeamPE #Cycle2 #Cycle3 #CoinLecture #LitteratureJeunesse #RallyeLecture #DonnerLeGoutDeLire #ProfesseurDesEcoles
  ```
- **Lien de destination** :
  ```text
  https://livresenclasse.com/fr/ressources/fiche-de-lecture-a-imprimer?mtm_source=pinterest&mtm_medium=social&mtm_campaign=lead_magnets&mtm_content=fiche_lecture
  ```

---

## 4. Configuration des 3 Objectifs (Goals) dans Matomo

Pour mesurer l'efficacité de vos lead magnets et le trafic généré par Pinterest, configurez ces 3 objectifs dans votre tableau de bord Matomo (**Administration** > **Objectifs** > **Créer un nouvel objectif**) :

### Objectif 1 : Clic Partage Pinterest (Intention de sauvegarde)
- **Nom de l'objectif** : `Clic Partage Pinterest`
- **Déclenchement** : `Lorsqu'un visiteur envoie un événement`
- **Condition** :
  - `Catégorie d'événement` = `Ressources`
  - `Action d'événement` = `Clic_Pinterest`
- **Valeur par défaut** : Laisser vide ou 1.

### Objectif 2 : Utilisation / Impression Ressource (Consommation Lead Magnet)
- **Nom de l'objectif** : `Impression ou Téléchargement Ressource`
- **Déclenchement** : `Lorsqu'un visiteur envoie un événement`
- **Condition** :
  - `Catégorie d'événement` = `Ressources`
  - `Action d'événement` = `Impression`

### Objectif 3 : Passerelle vers le Logiciel (Conversion vers inscription)
- **Nom de l'objectif** : `Clic CTA Vers Logiciel`
- **Déclenchement** : `Lorsqu'un visiteur envoie un événement`
- **Condition** :
  - `Catégorie d'événement` = `Conversion`
  - `Action d'événement` = `CTA_Logiciel`

### Comment analyser l'entonnoir dans Matomo ?
1. Allez dans **Acquisition** > **Campagnes**.
2. Vous verrez la campagne `lead_magnets` avec la source `pinterest`.
3. Cliquez dessus pour voir les sous-contenus : `marque_pages`, `diplome_lecture`, `fiche_lecture`.
4. En bas de page, sélectionnez la métrique **Objectifs** pour voir exactement :
   - Combien de visites Pinterest ont téléchargé la ressource ?
   - Combien de visites Pinterest ont cliqué vers le logiciel pour créer leur classe ?

---

## 5. Calendrier & Rythme de Publication

Sur Pinterest, **la régularité prime sur la quantité brute**. Ne publiez pas toutes vos épingles en une seule journée : l'algorithme favorise les profils actifs chaque semaine.

### Planning recommandé (1 à 2 épingles par semaine)

| Semaine | Ressource mise en avant | Angle / Accroche éditoriale | Tableau Pinterest cible |
|---|---|---|---|
| **Semaine 1** | Marque-pages d'emprunt | Organisation de rentrée / circulation des livres | *Bibliothèque de classe & BCD* |
| **Semaine 2** | Fiches Coup de Cœur | Donner envie de lire & conseils entre élèves | *Donner le goût de lire aux enfants* |
| **Semaine 3** | Diplôme de lecture | Célébrer les premiers livres lus / rallye | *Rallye lecture & Défis littéraires* |
| **Semaine 4** | Marque-pages (Variante verso) | Étoiles et avis critique des élèves | *Imprimables gratuits pour profs* |
| **Semaine 5** | Fiches Coup de Cœur | Rituel de la minute critique du vendredi | *Bibliothèque de classe & BCD* |
| **Semaine 6** | Diplôme de lecture | Paliers 10 & 20 livres / fin de trimestre | *Rallye lecture & Défis littéraires* |

### Recyclage saisonnier (Moments clés)
- **Août - Septembre (Rentrée des classes)** : Marque-pages et organisation du coin lecture.
- **Novembre - Décembre (Fin de période 2)** : Diplômes de lecture du premier trimestre.
- **Février - Mars (Printemps des poètes & Rallyes)** : Fiches coup de cœur et diplômes de rallye.
- **Juin (Fin d'année scolaire)** : Bilan des lectures annuelles et remise solennelle des diplômes.
