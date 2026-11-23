# Rapport de Benchmark & Limites de Charge - VM Oracle Secours

*Date du test : 18 novembre 2026*  
*Cible : `https://backup.livresenclasse.com` (Oracle Cloud Infrastructure - Région Zurich `eu-zurich-1`)*  
*Outil : Grafana k6 v2.4.0 (exécuté sur le réseau local via conteneur officiel)*

---

## 1. Caractéristiques de l'Infrastructure

* **Forme (Shape)** : `VM.Standard.E2.1.Micro` (Always Free)
* **Processeur** : 1 OCPU AMD EPYC
* **Mémoire vive** : 1 Go RAM physique + 2 Go Swap
* **Bande passante réseau** : 0.48 Gbps
* **Stockage** : Block Storage standard
* **Stack logicielle** : Docker Compose (`traefik:v3`, `authelia`, `cloudflare/cloudflared:latest`, `biblio` Gunicorn 2 workers, SQLite WAL).

---

## 2. Synthèse Comparative des Tests de Charge

Deux scénarios ont été exécutés avec une montée progressive en charge (ramping VUs) :
* **Test 1 (Charge modérée à forte)** : 1 à 50 utilisateurs simultanés (VUs).
* **Test 2 (Stress extrême / Saturation)** : 1 à 150 utilisateurs simultanés (VUs).

| Métrique | Test 1 (50 VUs max) | Test 2 (150 VUs max) |
| :--- | :---: | :---: |
| **Requêtes totales traitées** | 2'474 requêtes | 2'226 requêtes |
| **Volume de données échangé** | 94 Mo | 116 Mo |
| **Débit soutenu moyen (RPS)** | **30.87 req/s** | **24.45 req/s** |
| **Taux d'échec / Erreurs HTTP** | **0.00 %** (0 erreur) | **0.00 %** (0 erreur) |
| **Latence min** | 16.01 ms | 15.72 ms |
| **Latence médiane (p50)** | **602 ms** | **2.25 s** |
| **Latence moyenne** | 654 ms | 2.81 s |
| **Percentile p90** | 1.29 s | 5.96 s |
| **Percentile p95** | **1.48 s** | **6.22 s** |
| **Percentile p99** | **1.71 s** | **6.64 s** |
| **Percentile p99.9** | **2.05 s** | **6.82 s** |
| **Latence max isolée** | 7.52 s | 21.17 s |

---

## 3. Comportement des Ressources & Limites Physiques

* **Plafond CPU / Débit** : L'unique OCPU plafonne naturellement entre **25 et 35 requêtes dynamiques / seconde** (rendu complet HTML Jinja2 + requêtes SQLite).
* **Résilience sous saturation** : 
  * Même poussé à **150 VUs** (l'équivalent de 1'500 à 3'000 enseignants naviguant simultanément), **aucune requête n'a échoué ni été coupée par Cloudflare ou Traefik**.
  * Le mécanisme de file d'attente (backlog queue) temporise les requêtes sans crash.
* **Consommation Mémoire** :
  * RAM utilisée totale : **~577 Mo / 952 Mo** (encore 374 Mo de mémoire vive libre).
  * Swap sollicité : **~296 Mo / 2048 Mo**.
  * Aucun risque d'OOM Killer (Out-Of-Memory).

---

## 4. Conclusion Opérationnelle

Pour une instance 100% gratuite :
1. **Jusqu'à 15 VUs (~300 utilisateurs actifs)** : Réponse ultra-rapide (**médiane ~50 ms, p95 < 150 ms**).
2. **Jusqu'à 50 VUs (~1'000 utilisateurs actifs)** : Navigation fluide (**p99.9 ≤ 2.05 s**).
3. **Au-delà de 100 VUs** : Allongement de la file d'attente (latence ~2 à 6 s), mais **aucune perte de données ni coupure de service (taux d'erreur 0%)**.
