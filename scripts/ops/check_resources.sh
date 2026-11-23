#!/usr/bin/env bash
# ==============================================================================
# Surveillance des ressources serveur (Disque, RAM, Swap)
# Envoie une alerte dans Discord (#ressources) si un seuil critique est dépassé
# ==============================================================================

set -euo pipefail

HOMELAB_ENV="${HOMELAB_ENV:-/home/rob1/.env_homelab}"
if [ -f "$HOMELAB_ENV" ]; then
    # shellcheck disable=SC1090
    source "$HOMELAB_ENV"
fi

DISCORD_WEBHOOK="${DISCORD_WEBHOOK_RESOURCES:-${DISCORD_WEBHOOK:-}}"
DISCORD_ROLE_CRITICAL="${DISCORD_ROLE_CRITICAL:-}"

if [ -z "$DISCORD_WEBHOOK" ]; then
    # Pas de webhook configuré, sortir silencieusement
    exit 0
fi

DISK_THRESHOLD=85
RAM_THRESHOLD=90

# 1. Mesure de l'espace disque sur /
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')

# 2. Mesure de la RAM
RAM_TOTAL=$(free -m | awk '/Mem:/ {print $2}')
RAM_USED=$(free -m | awk '/Mem:/ {print $3}')
RAM_USAGE=$(( RAM_USED * 100 / RAM_TOTAL ))

# 3. Mesure du Swap
SWAP_TOTAL=$(free -m | awk '/Swap:/ {print $2}')
SWAP_USED=$(free -m | awk '/Swap:/ {print $3}')
SWAP_USAGE=0
if [ "$SWAP_TOTAL" -gt 0 ]; then
    SWAP_USAGE=$(( SWAP_USED * 100 / SWAP_TOTAL ))
fi

IS_ALERT=0
ALERT_MSG=""

if [ "$DISK_USAGE" -ge "$DISK_THRESHOLD" ]; then
    IS_ALERT=1
    ALERT_MSG="${ALERT_MSG}⚠️ **Disque racine critique** : ${DISK_USAGE}% utilisé (Reste seulement ${DISK_AVAIL})\n"
fi

if [ "$RAM_USAGE" -ge "$RAM_THRESHOLD" ]; then
    IS_ALERT=1
    ALERT_MSG="${ALERT_MSG}⚠️ **RAM critique** : ${RAM_USAGE}% utilisé (${RAM_USED} Mo / ${RAM_TOTAL} Mo)\n"
fi

if [ "$IS_ALERT" -eq 1 ]; then
    HOST=$(hostname)
    mention=""
    if [ -n "$DISCORD_ROLE_CRITICAL" ]; then
        mention="<@&${DISCORD_ROLE_CRITICAL}>"
    fi
    payload=$(python3 -c "import json; print(json.dumps({
        'username': 'Surveillance Ressources',
        'content': '''$mention''',
        'embeds': [{
            'title': '🚨 Alerte Ressources : ' + '$HOST',
            'description': '''$ALERT_MSG''',
            'color': 15158332,
            'fields': [
                {'name': 'Disque /', 'value': '$DISK_USAGE% (Reste $DISK_AVAIL)', 'inline': True},
                {'name': 'RAM', 'value': '$RAM_USAGE% ($RAM_USED/$RAM_TOTAL Mo)', 'inline': True},
                {'name': 'Swap', 'value': '$SWAP_USAGE% ($SWAP_USED/$SWAP_TOTAL Mo)', 'inline': True}
            ],
            'footer': {'text': 'Seuils : Disque > $DISK_THRESHOLD%, RAM > $RAM_THRESHOLD%'}
        }]
    }))")

    curl -s -m 5 -H "Content-Type: application/json" -X POST -d "$payload" "$DISCORD_WEBHOOK" >/dev/null 2>&1 || true
fi
