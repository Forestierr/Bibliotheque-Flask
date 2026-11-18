# Haute Disponibilité (Failover Automatique) et Sauvegardes - Livres en Classe

Ce document détaille l'architecture de haute disponibilité, le failover automatique, le système anti-split-brain et la procédure de rapatriement (failback) en une commande de **Livres en Classe**.

---

## Sommaire

1. [Architecture Globale & Schéma](#1-architecture-globale--schéma)
2. [Inventaire des Fichiers et Scripts](#2-inventaire-des-fichiers-et-scripts)
3. [Sauvegardes Externes Chiffrées (Google Drive GFS)](#3-sauvegardes-externes-chiffrées-google-drive-gfs)
4. [Réplication Continue Inter-Serveurs (RPO ≤ 5 min)](#4-réplication-continue-inter-serveurs-rpo--5-min)
5. [Mécanisme de Failover Automatique (La Sentinelle)](#5-mécanisme-de-failover-automatique-la-sentinelle)
6. [Sécurité Anti-Écrasement (Protection Split-Brain)](#6-sécurité-anti-écrasement-protection-split-brain)
7. [Procédure de Rapatriement Automatisé (Failback)](#7-procédure-de-rapatriement-automatisé-failback)
8. [Guide de Dépannage et Commandes Utiles](#8-guide-de-dépannage-et-commandes-utiles)

---

## 1. Architecture Globale & Schéma

```
[ Régime Nominal (Normal) ]
  Écoles & Enseignants ───► Cloudflare Anycast (Edge)
                                      │
                                      ▼ CNAME livresenclasse.com
                            Tunnel Local "homelab"
                                      │
                                      ▼
                           Serveur Local (192.168.1.144)
                                ┌───────────────┐
                                │ biblio:5602   │
                                └───────┬───────┘
                                        │ Snapshot WAL (toutes les 5 min)
                                        ▼ (rsync SSH chiffré)
                             VM Oracle Cloud Zurich
                                ┌───────────────┐
                                │ Réplique DB   │
                                └───────────────┘

[ Scénario Panne Serveur Local (Failover Automatique) ]
  1. Panne locale détectée par la Sentinelle Oracle (3 échecs consécutifs > 1 min).
  2. La Sentinelle appelle l'API Cloudflare et bascule les CNAME vers le Tunnel Oracle.
  3. Pose du verrou FAILOVER_ACTIVE sur Oracle.
  4. Le trafic bascule en 2 secondes sur Oracle. Aucune interruption pour les écoles.

[ Scénario Rétablissement (Failback en 1 commande) ]
  1. Le serveur local se rallume.
  2. sync_to_oracle.sh voit FAILOVER_ACTIVE et REFUSE de synchroniser (sécurité anti-écrasement).
  3. L'administrateur lance : /home/rob1/scripts/failback_from_cloud.sh
  4. Le script rebascule le DNS vers Local, rapatrie la base d'Oracle, vérifie l'intégrité et lève le verrou.
```

---

## 2. Inventaire des Fichiers et Scripts

### A. Scripts Opérationnels (`scripts/ops/`)
* **`backup_gdrive.sh`** : Sauvegarde quotidienne chiffrée AES-256 avec rétention GFS (Google Drive).
* **`sync_to_oracle.sh`** : Synchronisation continue toutes les 5 min (Local ➔ Cloud) avec rechargement gracieux `SIGHUP` de Gunicorn et vérification du verrou de secours.
* **`watchdog_failover.sh`** : Sentinelle de surveillance tournant chaque minute sur Oracle. Déclenche la bascule automatique via l'API Cloudflare si le local tombe.
* **`failback_from_cloud.sh`** : Rapatriement automatique complet des modifications du Cloud vers le local et retour DNS Cloudflare vers le serveur local.

### B. Emplacements Système en Production
* **Serveur Local** :
  * Scripts : `/home/rob1/scripts/`
  * Logs : `/home/rob1/logs/sync_oracle.log`
  * Base : `/home/rob1/server/rob1forest/apps/Bibliotheque-Flask/instance/db.sqlite`
* **Serveur Oracle Cloud** :
  * Sentinelle : `/home/ubuntu/livresenclasse/watchdog_failover.sh`
  * Verrou : `/home/ubuntu/livresenclasse/FAILOVER_ACTIVE`
  * Log : `/home/ubuntu/livresenclasse/watchdog.log`
  * Base : `/home/ubuntu/livresenclasse/instance/db.sqlite`
  * Heartbeat Healthchecks.io : `*/5 * * * *` vers `https://hc-ping.com/1bfb023a-735d-4c5f-bcc1-1f36aa649ff7`

---

## 3. Sauvegardes Externes Chiffrées (Google Drive GFS)

* **Script** : `/home/rob1/scripts/backup_livresenclasse.sh`
* **Planification Cron** : Tous les jours à 03h00 UTC (`0 3 * * *`).
* **Sécurité** : Chiffrement AES-256 via GPG.
* **Rétention GFS** :
  * `daily/` : 3 derniers jours (purge > 3 jours).
  * `weekly/` : 1 hebdomadaire le dimanche (purge > 8 jours).
  * `monthly/` : 1 mensuelle le 1er du mois (purge > 32 jours).

---

## 4. Réplication Continue Inter-Serveurs

### Option A-1 : Synchronisation Périodique (Rsync SSH - RPO ≤ 5 min)
* **Script** : `/home/rob1/scripts/sync_to_oracle.sh`
* **Planification Cron** : Toutes les 5 minutes (`*/5 * * * *`).
* **Mécanique** :
  1. Vérification de l'absence du verrou `FAILOVER_ACTIVE`.
  2. Snapshot à chaud SQLite `sqlite3 .backup`.
  3. Transfert différentiel rsync chiffré vers Oracle.
  4. Remplacement atomique système (`mv`) et signal `docker exec biblio kill -HUP 1` pour que Gunicorn recharge son descripteur de fichier sans coupure.

### Option A-2 : Réplication Continue Streaming (Litestream SFTP Direct - RPO < 1 s)
Pour une synchronisation en temps réel au fil de l'eau (sans attendre 5 minutes) et sans service cloud tiers additionnel :
* **Principe** : Litestream surveille en continu le journal WAL SQLite (`db.sqlite-wal`) sur le serveur local et diffuse chaque transaction commitée vers la VM Oracle via SFTP/SSH.
* **Fichiers de configuration & Scripts prêts à l'emploi** :
  * `scripts/ops/litestream.yml` : Configuration de la réplication de `instance/db.sqlite` vers `152.67.70.90` (répertoire distant `/home/ubuntu/livresenclasse/litestream_replica`).
  * `scripts/ops/litestream.service` : Unité systemd pour faire tourner Litestream en arrière-plan avec redémarrage automatique.
  * `scripts/ops/install_litestream.sh` : Script d'installation automatique du binaire Litestream (amd64 / arm64).
  * `scripts/ops/restore_litestream_on_oracle.sh` : Script de restauration instantanée sur Oracle (`litestream restore -if-replica-exists`).
* **Installation rapide** :
  ```bash
  # Sur le serveur local (192.168.1.144) :
  ./scripts/ops/install_litestream.sh
  sudo cp scripts/ops/litestream.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now litestream
  ```

---

## 5. Mécanisme de Failover Automatique (La Sentinelle)

* **Script** : `/home/ubuntu/livresenclasse/watchdog_failover.sh`
* **Planification Cron sur Oracle** : Toutes les minutes (`* * * * *`).
* **Sonde technique dédiée (`/healthy` et `/healthz`)** :
  * L'application Flask expose un endpoint de santé dédié non préfixé par la langue (`https://livresenclasse.com/healthy`).
  * Il exécute une requête `SELECT 1` sur SQLite pour valider la disponibilité de la base sans surcoût de template Jinja2.
  * Réponse type (`HTTP 200 OK`) :
    ```json
    {
      "status": "ok",
      "database": "healthy",
      "timestamp": "2026-11-18T19:25:00.000000+00:00"
    }
    ```
  * En cas d'erreur ou de base verrouillée, il renvoie immédiatement `HTTP 503 Service Unavailable`.
  * *(Note : Dès le déploiement du code en production, la sonde du watchdog cible `/healthy` au lieu de la page lourde `/fr/`).*
* **Détection Anti-Faux-Positifs** :
  1. Vérifie d'abord qu'Oracle a accès à Internet (`curl https://1.1.1.1`).
  2. Sonde le endpoint de santé (`https://livresenclasse.com/healthy` ou fallback `/fr/`).
  3. Si la sonde échoue, attend 15 secondes et réessaye (2ème test).
  4. Si échec, attend 15 secondes et réessaye (3ème test).
  5. Si les 3 tests consécutifs échouent (panne confirmée > 1 min) :
     * Si Litestream est actif : restaure la base à la seconde près (`restore_litestream_on_oracle.sh`).
     * Bascule les CNAME `livresenclasse.com` et `auth.livresenclasse.com` vers le tunnel d'Oracle via l'API Cloudflare.
     * Crée le fichier `/home/ubuntu/livresenclasse/FAILOVER_ACTIVE`.

---

## 6. Sécurité Anti-Écrasement (Protection Split-Brain)

Quand le serveur local redémarre après une coupure :
1. Le script `sync_to_oracle.sh` teste la présence de `FAILOVER_ACTIVE` sur Oracle.
2. Si le verrou est présent, le script **abandonne immédiatement** :
   ```
   [ALERTE SÉCURITÉ] Le mode FAILOVER est actif sur Oracle Cloud !
   La synchronisation Local -> Cloud est STRICTEMENT BLOQUÉE pour protéger les données du Cloud.
   ```
3. Cela empêche formellement la machine locale de détruire le travail saisi sur le Cloud pendant la panne.

---

## 7. Procédure de Rapatriement Automatisé (Failback)

Une fois l'incident résolu sur le serveur local :

Exécutez simplement la commande suivante sur le serveur local :
```bash
/home/rob1/scripts/failback_from_cloud.sh
```

Le script effectue automatiquement et séquentiellement :
1. **Bascule DNS Cloudflare** : Rebascule les CNAME `livresenclasse.com` et `auth.livresenclasse.com` vers le tunnel local.
2. **Pause de 5 secondes** : Laisse se terminer les dernières requêtes in-flight sur Oracle.
3. **Instantané cohérent** : Exécute `sqlite3 .backup` sur Oracle.
4. **Rapatriement et vérification** : Télécharge la base, exécute `PRAGMA integrity_check;`.
5. **Application locale** : Remplace `db.sqlite` et redémarre le conteneur `biblio` local.
6. **Levée du verrou** : Supprime `/home/ubuntu/livresenclasse/FAILOVER_ACTIVE` sur Oracle.
7. **Reprise nominale** : La synchronisation Local ➔ Cloud reprend automatiquement.

---

## 8. Guide de Dépannage et Commandes Utiles

### Vérifier le statut du Failover sur Oracle
```bash
ssh oracle-biblio "test -f /home/ubuntu/livresenclasse/FAILOVER_ACTIVE && echo 'FAILOVER EN COURS' || echo 'Régime Normal'"
```

### Consulter les logs de la Sentinelle sur Oracle
```bash
ssh oracle-biblio "tail -n 25 /home/ubuntu/livresenclasse/watchdog.log"
```

### Consulter les logs de synchronisation sur le serveur local
```bash
tail -n 25 /home/rob1/logs/sync_oracle.log
```

### Vérifier la cible DNS actuelle Cloudflare
```bash
dig +short CNAME livresenclasse.com
```
* Si pointe vers `8086dee7...` : Trafic sur le serveur local.
* Si pointe vers `d6f9880e...` : Trafic sur le serveur Oracle Cloud.
