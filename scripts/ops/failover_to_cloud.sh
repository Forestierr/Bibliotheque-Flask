#!/usr/bin/env bash
# ==============================================================================
# Script de bascule manuelle (Failover) depuis le serveur local vers Oracle Cloud
# 100% Automatisé : Synchronisation / Restauration + Bascule DNS Cloudflare + Verrou
# ==============================================================================

set -euo pipefail

DB_LOCAL="${DB_LOCAL:-/home/rob1/server/rob1forest/apps/Bibliotheque-Flask/instance/db.sqlite}"
REMOTE_HOST="${REMOTE_HOST:-oracle-biblio}"
REMOTE_LOCK="/home/ubuntu/livresenclasse/FAILOVER_ACTIVE"

# Identifiants Cloudflare
CF_EMAIL="robinforestier1407@gmail.com"
CF_KEY="737093cba7a984125c2ed1a8b03798654cf8e"
CF_ZONE_ID="ab629cd54d5b8d91c13d651470d17fcd"
CF_RECORD_ID_APP="e02e6467e916b7c5a15fce799a741dae"   # livresenclasse.com
CF_RECORD_ID_AUTH="0c0c5669254ded18c9bfee6fad244fe3"  # auth.livresenclasse.com

# Cible Tunnel Secours Oracle
TUNNEL_ORACLE_TARGET="d6f9880e-8118-4509-8a85-9162face663d.cfargotunnel.com"

# Configuration des Alertes & Notifications
BARK_KEY="${BARK_KEY:-79dXLJGwoScfZckHKNMuKY}"
BARK_HOST="${BARK_HOST:-https://bark.rob1forest.com}"
HEALTHCHECKS_UUID="${HEALTHCHECKS_UUID:-}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
DISCORD_ROLE_CRITICAL="${DISCORD_ROLE_CRITICAL:-}"
DISCORD_ROLE_INFO="${DISCORD_ROLE_INFO:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

ENV_FILE="${ENV_FILE:-/home/rob1/server/rob1forest/apps/Bibliotheque-Flask/.env}"
if [ -f "$ENV_FILE" ]; then
    eval "$(grep -E '^(DISCORD_WEBHOOK_URL|DISCORD_ROLE_CRITICAL|DISCORD_ROLE_INFO|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|BARK_KEY|BARK_HOST|HEALTHCHECKS_UUID)=' "$ENV_FILE" | sed -e 's/^/export /')" 2>/dev/null || true
fi

send_alert() {
    local title="$1"
    local message="$2"
    local status="${3:-error}"

    log "Envoi des alertes : $title..."

    if [ -n "$HEALTHCHECKS_UUID" ]; then
        curl -fsS -m 5 --retry 2 --data-raw "$title : $message" "https://hc-ping.com/${HEALTHCHECKS_UUID}/fail" >/dev/null 2>&1 || true
    fi

    if [ -n "$BARK_KEY" ]; then
        local enc_title enc_msg
        enc_title=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$title'''))" 2>/dev/null || echo "Info")
        enc_msg=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$message'''))" 2>/dev/null || echo "Failover")
        curl -s -m 5 "${BARK_HOST}/${BARK_KEY}/${enc_title}/${enc_msg}?group=BiblioHA&level=critical&icon=https://livresenclasse.com/static/img/logo.png" >/dev/null 2>&1 || true
    fi

    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        local color="15158332"
        local mention=""
        if [ -n "$DISCORD_ROLE_CRITICAL" ]; then
            mention="<@&${DISCORD_ROLE_CRITICAL}>"
        fi
        local payload
        payload=$(python3 -c "import json; print(json.dumps({'username': 'Sentinelle Livres en Classe', 'avatar_url': 'https://livresenclasse.com/static/img/logo.png', 'content': '''$mention''', 'embeds': [{'title': '''$title''', 'description': '''$message''', 'color': $color, 'footer': {'text': 'Serveur Oracle Secours Active'}}]}))" 2>/dev/null || echo "")
        if [ -n "$payload" ]; then
            curl -s -m 5 -H "Content-Type: application/json" -X POST -d "$payload" "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1 || true
        fi
    fi
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cf_update_record() {
    local record_id="$1"
    local name="$2"
    local target="$3"
    
    log "Cloudflare API : Bascule de $name vers le tunnel Oracle ($target)..."
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
log "=== DÉBUT DE LA BASCULE VERS LE CLOUD ORACLE (FAILOVER) ==="
log "================================================================="

# 1. Vérifier la connectivité avec le Cloud
log "1. Vérification de la connectivité avec Oracle Cloud..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE_HOST" "echo ok" >/dev/null 2>&1; then
    log "ERREUR: Impossible de joindre Oracle Cloud ($REMOTE_HOST) via SSH" >&2
    exit 1
fi

# 2. Restauration de la dernière réplique Litestream sur Oracle
log "2. Application de la dernière transaction SQLite sur Oracle Cloud..."
ssh -o BatchMode=yes "$REMOTE_HOST" "
REPLICA_DIR='/home/ubuntu/livresenclasse/litestream_replica'
DB_TARGET='/home/ubuntu/livresenclasse/instance/db.sqlite'
if [ -d \"\$REPLICA_DIR/generations\" ]; then
    rm -f /tmp/restore_temp.sqlite
    if /usr/local/bin/litestream restore -if-replica-exists -o /tmp/restore_temp.sqlite \"file://\$REPLICA_DIR\" && mv /tmp/restore_temp.sqlite \"\$DB_TARGET\"; then
        docker exec biblio kill -HUP 1 2>/dev/null || docker restart biblio 2>/dev/null || true
    fi
fi
"

# 3. Basculement DNS Cloudflare vers le tunnel Oracle
log "3. Basculement DNS Cloudflare vers le tunnel Oracle..."
cf_update_record "$CF_RECORD_ID_APP" "livresenclasse.com" "$TUNNEL_ORACLE_TARGET"
cf_update_record "$CF_RECORD_ID_AUTH" "auth.livresenclasse.com" "$TUNNEL_ORACLE_TARGET"

# 4. Poser le verrou de failover actif sur Oracle
log "4. Pose du verrou FAILOVER_ACTIVE sur Oracle Cloud..."
ssh -o BatchMode=yes "$REMOTE_HOST" "
touch '$REMOTE_LOCK'
echo 'FAILOVER_ACTIVATED_AT=$(date \"+%Y-%m-%d %H:%M:%S\") (Bascule Manuelle)' > '$REMOTE_LOCK'
"

# 5. Envoi des alertes
send_alert "🚨 BASCULE VERS LE CLOUD ORACLE EFFECTUÉE" "Le trafic de livresenclasse.com a été basculé manuellement vers le serveur de secours Oracle Cloud Zurich." "error"

log "================================================================="
log "=== BASCULE VERS ORACLE TERMINÉE AVEC SUCCÈS ==="
log "================================================================="
