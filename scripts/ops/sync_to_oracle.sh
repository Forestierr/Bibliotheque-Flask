#!/usr/bin/env bash
# ==============================================================================
# Synchronisation continue de la base SQLite vers la VM Oracle de secours
# Exécution : toutes les 5 minutes via cron
# Protection 1 : flock anti-chevauchement
# Protection 2 : vérification du verrou FAILOVER_ACTIVE sur Oracle (Anti-Split-Brain)
# ==============================================================================

set -euo pipefail

LOCKFILE="/tmp/sync_to_oracle.lock"
exec 200>"$LOCKFILE"
flock -n 200 || exit 0

DB_SRC="${DB_SRC:-/home/rob1/server/rob1forest/apps/Bibliotheque-Flask/instance/db.sqlite}"
TMP_SNAP="/tmp/db_sync_oracle.sqlite"
REMOTE_HOST="${REMOTE_HOST:-oracle-biblio}"
REMOTE_DEST="${REMOTE_DEST:-/home/ubuntu/livresenclasse/instance/db.sqlite}"
REMOTE_LOCK="/home/ubuntu/livresenclasse/FAILOVER_ACTIVE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 1. Vérification présence de la source
if [ ! -f "$DB_SRC" ]; then
    log "ERREUR: Base locale introuvable à $DB_SRC" >&2
    exit 1
fi

# 2. SÉCURITÉ ANTI-SPLIT-BRAIN : Vérifier si Oracle est en mode Failover actif
if ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE_HOST" "test -f '$REMOTE_LOCK'" 2>/dev/null; then
    log "[ALERTE SÉCURITÉ] Le mode FAILOVER est actif sur Oracle Cloud !"
    log "La synchronisation Local -> Cloud est STRICTEMENT BLOQUÉE pour protéger les données du Cloud."
    log "Pour réintégrer les données et lever le verrou, exécutez : /home/rob1/scripts/failback_from_cloud.sh"
    exit 0
fi

# 3. Snapshot cohérent à chaud (.backup)
sqlite3 "$DB_SRC" ".backup '$TMP_SNAP'"

# 4. Transfert compressé par SSH vers un fichier temporaire sur la destination
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=10" "$TMP_SNAP" "${REMOTE_HOST}:${REMOTE_DEST}.new"

# 5. Remplacement atomique sur la destination et rechargement gracieux de Gunicorn
ssh -o BatchMode=yes -o ConnectTimeout=10 "$REMOTE_HOST" "mv '${REMOTE_DEST}.new' '${REMOTE_DEST}' && docker exec biblio kill -HUP 1"

# 6. Nettoyage du snapshot local
rm -f "$TMP_SNAP"

log "Synchronisation vers Oracle terminée avec succès (Gunicorn rechargé)."
