#!/usr/bin/env bash
# ==============================================================================
# Script de sauvegarde chiffrée de la base de données livresenclasse.com
# Destination : Google Drive (via Rclone)
# Rétention : 3 quotidiens (daily), 1 hebdo (weekly), 1 mensuel (monthly)
# ==============================================================================

set -euo pipefail

# Chemins par défaut (adaptables selon l'environnement)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_PATH="${DB_PATH:-${APP_DIR}/instance/db.sqlite}"
BACKUP_DIR="/tmp/livresenclasse_backup_$$"
LOG_FILE="${LOG_FILE:-${APP_DIR}/backup.log}"
RCLONE_BIN="${RCLONE_BIN:-$(command -v rclone || echo "${HOME}/.local/bin/rclone")}"

# Charger les variables d'environnement si un .env existe
if [ -f "${APP_DIR}/.env" ]; then
    # shellcheck disable=SC1091
    source "${APP_DIR}/.env"
fi

# Clé de chiffrement AES-256 (doit être définie dans l'environnement ou dans .env)
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-${SECRET_KEY:-}}"
if [ -z "$ENCRYPTION_KEY" ]; then
    echo "ERREUR: BACKUP_ENCRYPTION_KEY n'est pas définie." >&2
    exit 1
fi

# Dossiers Google Drive
GDRIVE_BASE="gdrive:Backups/livresenclasse"
GDRIVE_DAILY="${GDRIVE_BASE}/daily"
GDRIVE_WEEKLY="${GDRIVE_BASE}/weekly"
GDRIVE_MONTHLY="${GDRIVE_BASE}/monthly"

# Horodatage
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
DAY_OF_WEEK=$(date +"%u")   # 1 (lundi) à 7 (dimanche)
DAY_OF_MONTH=$(date +"%d")  # 01 à 31

FILENAME="livresenclasse_${TIMESTAMP}.sqlite.gz.gpg"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

log "=== Début de la sauvegarde de livresenclasse.com ==="

# 1. Vérifications
if [ ! -f "$DB_PATH" ]; then
    log "ERREUR: Base de données introuvable à $DB_PATH"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# 2. Sauvegarde SQLite atomique à chaud (compatible WAL)
TMP_SQLITE="${BACKUP_DIR}/db_snapshot.sqlite"
log "Création du snapshot SQLite cohérent (.backup)..."
sqlite3 "$DB_PATH" ".backup '${TMP_SQLITE}'"

# 3. Compression gzip et Chiffrement fort GPG (AES-256)
ENCRYPTED_FILE="${BACKUP_DIR}/${FILENAME}"
log "Compression et chiffrement AES-256 avec GPG..."
gzip -c "$TMP_SQLITE" | gpg --symmetric --cipher-algo AES256 --batch --yes --passphrase "$ENCRYPTION_KEY" -o "$ENCRYPTED_FILE"

FILE_SIZE=$(du -h "$ENCRYPTED_FILE" | cut -f1)
log "Fichier chiffré généré : ${FILENAME} (${FILE_SIZE})"

# 4. Envoi sur Google Drive - Dossier DAILY
log "Upload vers Google Drive (${GDRIVE_DAILY})..."
"$RCLONE_BIN" copyto "$ENCRYPTED_FILE" "${GDRIVE_DAILY}/${FILENAME}"

# 5. Envoi WEEKLY (chaque dimanche)
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    log "Dimanche détecté -> Copie vers le dossier WEEKLY..."
    "$RCLONE_BIN" copyto "$ENCRYPTED_FILE" "${GDRIVE_WEEKLY}/${FILENAME}"
fi

# 6. Envoi MONTHLY (le 1er du mois)
if [ "$DAY_OF_MONTH" = "01" ]; then
    log "1er du mois détecté -> Copie vers le dossier MONTHLY..."
    "$RCLONE_BIN" copyto "$ENCRYPTED_FILE" "${GDRIVE_MONTHLY}/${FILENAME}"
fi

# 7. Rotation et Rétention automatique
# A. Daily : conserve uniquement les 3 derniers jours
log "Nettoyage des sauvegardes daily de plus de 3 jours..."
"$RCLONE_BIN" delete --min-age 3d --retries 1 "$GDRIVE_DAILY" 2>/dev/null || true

# B. Weekly : conserve la dernière sauvegarde hebdo (supprime > 8 jours)
log "Nettoyage des sauvegardes weekly de plus de 8 jours..."
"$RCLONE_BIN" delete --min-age 8d --retries 1 "$GDRIVE_WEEKLY" 2>/dev/null || true

# C. Monthly : conserve la dernière sauvegarde mensuelle (supprime > 32 jours)
log "Nettoyage des sauvegardes monthly de plus de 32 jours..."
"$RCLONE_BIN" delete --min-age 32d --retries 1 "$GDRIVE_MONTHLY" 2>/dev/null || true

log "=== Sauvegarde et rotation terminées avec succès ! ==="
