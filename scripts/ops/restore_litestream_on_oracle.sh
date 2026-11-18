#!/usr/bin/env bash
# ==============================================================================
# Restauration de la base SQLite depuis la réplique Litestream locale sur Oracle
# ==============================================================================
set -euo pipefail

REPLICA_DIR="/home/ubuntu/livresenclasse/litestream_replica"
DB_TARGET="/home/ubuntu/livresenclasse/instance/db.sqlite"

if [ ! -d "$REPLICA_DIR" ]; then
    echo "Répertoire de réplique introuvable à $REPLICA_DIR. Abandon."
    exit 1
fi

echo "Restauration de la base SQLite depuis $REPLICA_DIR vers $DB_TARGET..."
/usr/local/bin/litestream restore -if-replica-exists -o "$DB_TARGET" "$REPLICA_DIR"

if [ -f "$DB_TARGET" ]; then
    echo "Vérification d'intégrité SQLite..."
    INTEGRITY=$(sqlite3 "$DB_TARGET" "PRAGMA integrity_check;")
    if [ "$INTEGRITY" = "ok" ]; then
        echo "Intégrité OK. Rechargement gracieux de Gunicorn..."
        docker exec biblio kill -HUP 1 2>/dev/null || true
        echo "Base prête et active sur Oracle !"
    else
        echo "ERREUR d'intégrité SQLite: $INTEGRITY"
        exit 1
    fi
fi
