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

## 4. Réplication Continue Inter-Serveurs (En Production : Litestream Streaming - RPO < 1 s)

Le système utilise **Litestream** en production pour répliquer en temps réel au fil de l'eau chaque écriture de la base SQLite sans latence de batch :

* **Principe** : Litestream surveille en continu le journal WAL SQLite (`db.sqlite-wal`) sur le serveur local et diffuse chaque transaction commitée vers la VM Oracle via SFTP/SSH.
* **Service actif** : `systemctl --user status litestream` sur le serveur local (`192.168.1.144`).
* **Configuration** : `/home/rob1/scripts/litestream.yml` (clé SSH `~/.ssh/id_oracle_sync`, cible `152.67.70.90:/home/ubuntu/livresenclasse/litestream_replica`).
* **RPO (Perte max en cas de crash brutal)** : **< 1 seconde** (chaque écriture est expédiée en ~85 ms).
* **Consommation** : Binaire Go léger (~16 Mo RAM, < 0.1% CPU).
* **Sécurité Anti-Corruption lors d'un switch (Failover)** :
  1. Lors d'une bascule, `watchdog_failover.sh` applique les derniers segments WAL via `litestream restore -if-replica-exists`.
  2. Il vérifie immédiatement l'intégrité SQLite (`PRAGMA integrity_check;`) avant de recharger Gunicorn (`kill -HUP 1`).
  3. Si la base est corrompue ou incomplète, la restauration est rejetée et l'ancienne base valide est conservée.
* **Sécurité Anti-Corruption lors du retour (Failback)** :
  1. Lors du rapatriement, `failback_from_cloud.sh` stoppe Litestream temporairement.
  2. Il remplace la base locale par le snapshot cohérent d'Oracle, purge les anciens fichiers WAL locaux et réinitialise la réplique sur Oracle.
  3. Litestream est redémarré proprement pour initier une nouvelle génération sans conflit d'historique.

*(Note : L'ancien script rsync `sync_to_oracle.sh` reste disponible dans `scripts/ops/` à titre de secours manuel si besoin).*

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

---

---

## 9. Performances et Capacités de Charge (Benchmark k6)

Un test de charge complet a été réalisé sur la VM Oracle de secours (`VM.Standard.E2.1.Micro`).
Le rapport détaillé est consultable dans [`docs/benchmark-oracle.md`](benchmark-oracle.md) :
* **Débit maximal mesuré** : ~25 à 35 requêtes dynamiques / seconde.
* **Taux d'échec sous charge (jusqu'à 150 VUs)** : **0.00 %** (0 erreur HTTP sur 4'700+ requêtes).
* **Capacité estimée** : Supporte sereinement jusqu'à 1'000 utilisateurs réels simultanés (p99.9 ≤ 2.05 s).

---

## 10. Surveillance, Alertes Multi-Canaux & Contrôle d'État

### A. Contrôle d'État en 1 seconde (`ha_status.sh`)
Un script de diagnostic unifié est disponible sur le serveur local :
```bash
/home/rob1/scripts/ha_status.sh
```
Il vérifie et affiche en couleurs :
1. **La cible DNS Cloudflare** : indique si le trafic pointe vers le `Tunnel Local` ou le `Tunnel Oracle (Mode Secours)`.
2. **La sonde `/healthy`** : statut HTTP 200 et identification du serveur actif (`server: "local"` ou `"oracle-cloud"`).
3. **Le standby Oracle** : statut opérationnel de `backup.livresenclasse.com`.
4. **La sentinelle Oracle** : présence ou absence du verrou `FAILOVER_ACTIVE`.
5. **Litestream** : état du service de réplication WAL continue.

### B. Système d'Alertes Multi-Canaux lors d'un Failover
Lorsqu'une panne est confirmée sur le serveur local et que la sentinelle bascule vers Oracle Cloud, le script [`watchdog_failover.sh`](file:///c:/Users/Robin/Desktop/GitHub/Bibliotheque-Flask/scripts/ops/watchdog_failover.sh) émet automatiquement des alertes sur plusieurs canaux complémentaires :

1. **Bark (Push iOS)** :
   - Notification push critique envoyée vers l'iPhone (`https://bark.rob1forest.com/...`).
2. **Healthchecks.io (Fail Signal Cloud)** :
   - Ping immédiat de l'endpoint d'échec (`https://hc-ping.com/77e657b8-03fc-4576-bcbe-c0259dfa5657/fail`).
   - Même si le serveur local est totalement éteint, Healthchecks.io relaie instantanément l'alerte vers tous les canaux configurés (Discord, Telegram, Email, SMS).
3. **Discord Webhook** *(Optionnel)* :
   - Variable `DISCORD_WEBHOOK_URL` dans `/home/ubuntu/livresenclasse/.env` pour poster une alerte enrichie avec embed rouge dans un salon Discord privé.
4. **Telegram Bot** *(Optionnel)* :
   - Variables `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` pour envoi d'un message direct Telegram.

Lors du rapatriement ([`failback_from_cloud.sh`](file:///c:/Users/Robin/Desktop/GitHub/Bibliotheque-Flask/scripts/ops/failback_from_cloud.sh)), une notification de rétablissement `✅ RETOUR À LA NORMALE` est automatiquement envoyée sur tous ces canaux et le statut Healthchecks.io repasse au vert.
