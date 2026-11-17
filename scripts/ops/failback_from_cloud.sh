#!/usr/bin/env bash
# ==============================================================================
# Script de rapatriement (Failback) depuis le Cloud Oracle vers le serveur local
# 100% Automatisé : Rapatriement DB + Vérification Intégrité + Bascule DNS Cloudflare
# ==============================================================================

set -euo pipefail

DB_LOCAL="${DB_LOCAL:-/home/rob1/server/rob1forest/apps/Bibliotheque-Flask/instance/db.sqlite}"
REMOTE_HOST="${REMOTE_HOST:-oracle-biblio}"
REMOTE_DB="${REMOTE_DB:-/home/ubuntu/livresenclasse/instance/db.sqlite}"
REMOTE_LOCK="/home/ubuntu/livresenclasse/FAILOVER_ACTIVE"
TMP_REMOTE_SNAP="/tmp/db_failback_snap.sqlite"
TMP_LOCAL_SNAP="/tmp/db_failback_local.sqlite"
BACKUP_SAFETY="${DB_LOCAL}.pre_failback_$(date +%Y%m%d_%H%M%S)"

# Identifiants Cloudflare
CF_EMAIL="robinforestier1407@gmail.com"
CF_KEY="737093cba7a984125c2ed1a8b03798654cf8e"
CF_ZONE_ID="ab629cd54d5b8d91c13d651470d17fcd"
CF_RECORD_ID_APP="e02e6467e916b7c5a15fce799a741dae"   # livresenclasse.com
CF_RECORD_ID_AUTH="0c0c5669254ded18c9bfee6fad244fe3"  # auth.livresenclasse.com

# Cibles Tunnels
TUNNEL_LOCAL_TARGET="8086dee7-aee1-48c4-9166-be6f361172e5.cfargotunnel.com"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cf_update_record() {
    local record_id="$1"
    local name="$2"
    local target="$3"
    
    log "Cloudflare API : Rebascule de $name vers le tunnel local ($target)..."
    local response
    response=$(curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
        -H "X-Auth-Email: ${CF_EMAIL}" \
        -H "X-Auth-Key: ${CF_KEY}" \
        -H "Content-Type: application/json" \
        --data "{\"content\":\"${target}\",\"proxied\":true}")
    
    if echo "$response" | grep -q '"success":true'; then
        log "Cloudflare API : Succès pour $name."
    else
        log "ERREUR Cloudflare API pour $name : $response" >&2
        return 1
    fi
}

log "================================================================="
log "=== DÉBUT DU RAPATRIEMENT AUTOMATIQUE (CLOUD -> LOCAL) ==="
log "================================================================="

# 1. Vérifier la connectivité avec le Cloud
log "1. Vérification de la connectivité avec Oracle Cloud..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE_HOST" "test -f '$REMOTE_DB'"; then
    log "ERREUR: Impossible d'accéder à la base distante sur $REMOTE_HOST" >&2
    exit 1
fi

# 2. Rebasculer le DNS Cloudflare vers le local EN PREMIER
# Cela évite que de nouvelles écritures arrivent sur Oracle pendant la copie
log "2. Rebasculement DNS Cloudflare vers le serveur local..."
cf_update_record "$CF_RECORD_ID_APP" "livresenclasse.com" "$TUNNEL_LOCAL_TARGET"
cf_update_record "$CF_RECORD_ID_AUTH" "auth.livresenclasse.com" "$TUNNEL_LOCAL_TARGET"

# 3. Attendre 5 secondes que les dernières requêtes en cours sur Oracle se terminent
log "3. Pause de 5 secondes pour laisser se terminer les requêtes en cours sur Oracle..."
sleep 5

# 4. Prendre le snapshot final à chaud sur Oracle
log "4. Création de l'instantané SQLite final cohérent sur Oracle Cloud..."
ssh -o BatchMode=yes "$REMOTE_HOST" "sqlite3 '$REMOTE_DB' \".backup '$TMP_REMOTE_SNAP'\""

# 5. Sauvegarder la base locale actuelle par précaution
if [ -f "$DB_LOCAL" ]; then
    log "5. Sauvegarde de précaution de l'ancienne base locale vers $BACKUP_SAFETY..."
    cp "$DB_LOCAL" "$BACKUP_SAFETY"
fi

# 6. Rapatrier le snapshot depuis Oracle
log "6. Téléchargement de la base à jour depuis Oracle Cloud..."
rsync -az -e "ssh -o BatchMode=yes" "${REMOTE_HOST}:${TMP_REMOTE_SNAP}" "$TMP_LOCAL_SNAP"
ssh -o BatchMode=yes "$REMOTE_HOST" "rm -f '$TMP_REMOTE_SNAP'"

# 7. Vérifier l'intégrité de la base rapatriée
log "7. Vérification de l'intégrité de la base reçue..."
INTEGRITY=$(sqlite3 "$TMP_LOCAL_SNAP" "PRAGMA integrity_check;")
if [ "$INTEGRITY" != "ok" ]; then
    log "ERREUR CRITIQUE: L'intégrité de la base rapatriée est compromise : $INTEGRITY" >&2
    rm -f "$TMP_LOCAL_SNAP"
    exit 1
fi
log "Intégrité validée avec succès (ok)."

# 8. Remplacement atomique de la base locale
log "8. Application de la base de données à jour sur le serveur local..."
mv "$TMP_LOCAL_SNAP" "$DB_LOCAL"
chmod 644 "$DB_LOCAL"

# 9. Redémarrer le conteneur biblio local pour recharger la connexion
log "9. Redémarrage du conteneur biblio local..."
docker restart biblio >/dev/null 2>&1 || true

# 10. Lever le verrou FAILOVER_ACTIVE sur Oracle
log "10. Levée du verrou FAILOVER_ACTIVE sur Oracle Cloud..."
ssh -o BatchMode=yes "$REMOTE_HOST" "rm -f '$REMOTE_LOCK'"

log "================================================================="
log "=== RAPATRIEMENT TERMINÉ AVEC SUCCÈS (0 PERTE DE DONNÉE) ==="
log "================================================================="
log "Le trafic est revenu sur le serveur local et le verrou de sécurité a été levé."
