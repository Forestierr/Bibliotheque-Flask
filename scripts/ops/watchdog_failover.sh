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

log "BASCULE AUTOMATIQUE RÉUSSIE. Oracle Cloud est désormais le serveur de production."
log "Verrou $LOCK_FILE posé. La synchronisation locale est bloquée jusqu'au rapatriement."
