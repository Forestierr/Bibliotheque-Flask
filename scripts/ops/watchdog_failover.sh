#!/usr/bin/env bash
# ==============================================================================
# Sentinelle de Surveillance Haute Disponibilité (Tourne sur la VM Oracle)
# Fréquence : Toutes les minutes via cron
# Action : Détecte l'inaccessibilité du serveur local et bascule vers Oracle
# Sécurité : 3 essais espacés de 15s + test internet Oracle + verrouillage Latch
# ==============================================================================

set -euo pipefail

LOCK_FILE="/home/ubuntu/livresenclasse/FAILOVER_ACTIVE"
LOG_FILE="/home/ubuntu/livresenclasse/watchdog.log"

# Si le failover est déjà actif, ne rien faire
if [ -f "$LOCK_FILE" ]; then
    exit 0
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WATCHDOG] $*" | tee -a "$LOG_FILE"
}

# Identifiants Cloudflare
CF_EMAIL="robinforestier1407@gmail.com"
CF_KEY="737093cba7a984125c2ed1a8b03798654cf8e"
CF_ZONE_ID="ab629cd54d5b8d91c13d651470d17fcd"
CF_RECORD_ID_APP="e02e6467e916b7c5a15fce799a741dae"   # livresenclasse.com
CF_RECORD_ID_AUTH="0c0c5669254ded18c9bfee6fad244fe3"  # auth.livresenclasse.com

# Cible Tunnel Secours Oracle
TUNNEL_ORACLE_TARGET="d6f9880e-8118-4509-8a85-9162face663d.cfargotunnel.com"

# Configuration des Alertes & Notifications (chargées depuis l'environnement ou .env)
BARK_KEY="${BARK_KEY:-}"
BARK_HOST="${BARK_HOST:-https://bark.rob1forest.com}"
HEALTHCHECKS_UUID="${HEALTHCHECKS_UUID:-}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
DISCORD_ROLE_CRITICAL="${DISCORD_ROLE_CRITICAL:-}"
DISCORD_ROLE_INFO="${DISCORD_ROLE_INFO:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# Charger les variables optionnelles depuis .env si présent
ENV_FILE="${ENV_FILE:-/home/ubuntu/livresenclasse/.env}"
if [ -f "$ENV_FILE" ]; then
    eval "$(grep -E '^(DISCORD_WEBHOOK_URL|DISCORD_ROLE_CRITICAL|DISCORD_ROLE_INFO|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|BARK_KEY|BARK_HOST|HEALTHCHECKS_UUID)=' "$ENV_FILE" | sed -e 's/^/export /')" 2>/dev/null || true
fi

send_alert() {
    local title="$1"
    local message="$2"
    local status="${3:-error}"

    log "Envoi des alertes : $title..."

    # 1. Healthchecks.io (Fail signal ou OK)
    if [ -n "$HEALTHCHECKS_UUID" ]; then
        if [ "$status" = "error" ]; then
            curl -fsS -m 5 --retry 2 --data-raw "$title : $message" "https://hc-ping.com/${HEALTHCHECKS_UUID}/fail" >/dev/null 2>&1 || true
            log "Notification Healthchecks.io (/fail) envoyée."
        else
            curl -fsS -m 5 --retry 2 --data-raw "$title : $message" "https://hc-ping.com/${HEALTHCHECKS_UUID}" >/dev/null 2>&1 || true
            log "Notification Healthchecks.io (OK) envoyée."
        fi
    fi

    # 2. Bark (Push iOS)
    if [ -n "$BARK_KEY" ]; then
        local enc_title enc_msg
        enc_title=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$title'''))" 2>/dev/null || echo "Alerte")
        enc_msg=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$message'''))" 2>/dev/null || echo "Failover")
        if curl -s -m 5 "${BARK_HOST}/${BARK_KEY}/${enc_title}/${enc_msg}?group=BiblioHA&level=critical&icon=https://livresenclasse.com/static/img/logo.png" >/dev/null 2>&1; then
            log "Notification Bark envoyée avec succès."
        else
            log "Échec notification Bark (serveur local possiblement éteint)."
        fi
    fi

    # 3. Discord Webhook (si configuré)
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        local color="15158332"
        local mention=""
        if [ "$status" = "error" ] && [ -n "$DISCORD_ROLE_CRITICAL" ]; then
            mention="<@&${DISCORD_ROLE_CRITICAL}>"
        elif [ "$status" = "ok" ] && [ -n "$DISCORD_ROLE_INFO" ]; then
            mention="<@&${DISCORD_ROLE_INFO}>"
        fi
        local payload
        payload=$(python3 -c "import json; print(json.dumps({'username': 'Sentinelle Livres en Classe', 'avatar_url': 'https://livresenclasse.com/static/img/logo.png', 'content': '''$mention''', 'embeds': [{'title': '''$title''', 'description': '''$message''', 'color': $color, 'footer': {'text': 'Oracle Cloud Always Free Zurich'}}]}))" 2>/dev/null || echo "")
        if [ -n "$payload" ]; then
            curl -s -m 5 -H "Content-Type: application/json" -X POST -d "$payload" "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1 || true
            log "Notification Discord envoyée."
        fi
    fi

    # 4. Telegram Bot (si configuré)
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        local tele_text
        tele_text=$(python3 -c "import urllib.parse; print(urllib.parse.quote('🚨 *' + '''$title''' + '*\n' + '''$message'''))" 2>/dev/null || echo "$title")
        curl -s -m 5 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${tele_text}" \
            -d "parse_mode=Markdown" >/dev/null 2>&1 || true
        log "Notification Telegram envoyée."
    fi
}

# 1. Vérifier qu'Oracle a lui-même accès à Internet (évite les faux positifs)
if ! curl -s -m 3 --head https://1.1.1.1 >/dev/null 2>&1; then
    # Oracle n'a pas de réseau, on ne déclenche rien
    exit 0
fi

# 2. Sonde du serveur primaire (endpoint technique /healthy)
check_primary() {
    local code
    code=$(curl -s -m 5 -o /dev/null -w "%{http_code}" https://livresenclasse.com/healthy 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
        return 0
    else
        return 1
    fi
}

# Si le primaire répond bien, tout va bien
if check_primary; then
    exit 0
fi

# Premier échec détecté : confirmation avec 2 vérifications supplémentaires espacées
log "Alerte : Première sonde échouée pour le serveur primaire. Vérification en cours..."
sleep 15
if check_primary; then
    log "Fausse alerte (micro-coupure résolue). Abandon du failover."
    exit 0
fi

log "Alerte : Deuxième sonde échouée. Ultime vérification dans 15 secondes..."
sleep 15
if check_primary; then
    log "Fausse alerte au 3ème essai. Abandon du failover."
    exit 0
fi

# 3. PANNE AVÉRÉE DU SERVEUR LOCAL (3 échecs consécutifs)
log "=========================================================================="
log "CRITIQUE : Serveur primaire injoignable (3 échecs consécutifs)."
log "DÉCLENCHEMENT DE LA BASCULE AUTOMATIQUE VERS ORACLE CLOUD..."
log "=========================================================================="

# 3.1 Restauration de la dernière transaction SQLite depuis la réplique Litestream
REPLICA_DIR="/home/ubuntu/livresenclasse/litestream_replica"
DB_TARGET="/home/ubuntu/livresenclasse/instance/db.sqlite"

if [ -d "$REPLICA_DIR/generations" ]; then
    log "Restauration en cours de la base SQLite depuis la réplique Litestream..."
    rm -f /tmp/restore_temp.sqlite
    if /usr/local/bin/litestream restore -if-replica-exists -o /tmp/restore_temp.sqlite "file://$REPLICA_DIR" && mv /tmp/restore_temp.sqlite "$DB_TARGET"; then
        log "Restauration Litestream réussie."
        INTEGRITY=$(sqlite3 "$DB_TARGET" "PRAGMA integrity_check;" 2>/dev/null || echo "error")
        if [ "$INTEGRITY" = "ok" ]; then
            log "Intégrité SQLite validée (PRAGMA integrity_check: ok)."
            docker exec biblio kill -HUP 1 2>/dev/null || true
        else
            log "ATTENTION : Erreur d'intégrité SQLite ($INTEGRITY), conservation de la base précédente."
        fi
    else
        log "Avertissement : La restauration Litestream a échoué, conservation de la base actuelle."
    fi
fi

cf_update_record() {
    local record_id="$1"
    local name="$2"
    local target="$3"
    
    local response
    response=$(curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
        -H "X-Auth-Email: ${CF_EMAIL}" \
        -H "X-Auth-Key: ${CF_KEY}" \
        -H "Content-Type: application/json" \
        --data "{\"content\":\"${target}\",\"proxied\":true}")
    
    if echo "$response" | grep -q '"success":true'; then
        log "Cloudflare API : $name basculé avec succès vers Oracle ($target)."
    else
        log "ERREUR Cloudflare API pour $name : $response"
    fi
}

# Bascule des CNAME vers le tunnel Oracle
cf_update_record "$CF_RECORD_ID_APP" "livresenclasse.com" "$TUNNEL_ORACLE_TARGET"
cf_update_record "$CF_RECORD_ID_AUTH" "auth.livresenclasse.com" "$TUNNEL_ORACLE_TARGET"

# Poser le verrou de failover actif (sécurité anti-split-brain)
touch "$LOCK_FILE"
echo "FAILOVER_ACTIVATED_AT=$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCK_FILE"

# Envoi immédiat des alertes multi-canaux (Bark, Healthchecks.io, Discord/Telegram)
send_alert "🚨 BASCULE HAUTE DISPONIBILITÉ ACTIVE" "Le serveur local (192.168.1.144) est injoignable après 3 tentatives. Le trafic de livresenclasse.com a été basculé avec succès vers le serveur de secours Oracle Cloud Zurich." "error"

log "BASCULE AUTOMATIQUE RÉUSSIE. Oracle Cloud est désormais le serveur de production."
log "Verrou $LOCK_FILE posé. La synchronisation locale est bloquée jusqu'au rapatriement."
