#!/usr/bin/env bash
# ==============================================================================
# Notification de connexion SSH vers Discord (#auth-ssh)
# Ne se déclenche que sur les sessions interactives (ignore SCP, rsync, git, batch)
# ==============================================================================

if [ -n "${SSH_TTY:-}" ] && [ -n "${SSH_CLIENT:-}" ]; then
    CLIENT_IP=$(echo "$SSH_CLIENT" | awk '{print $1}')
    USER_NAME=$(whoami)
    HOST_NAME=$(hostname)
    LOGIN_DATE=$(date '+%Y-%m-%d %H:%M:%S')

    HOMELAB_ENV="${HOMELAB_ENV:-/home/rob1/.env_homelab}"
    if [ -f "$HOMELAB_ENV" ]; then
        # shellcheck disable=SC1090
        source "$HOMELAB_ENV"
    fi

    DISCORD_SSH_WEBHOOK="${DISCORD_WEBHOOK_SSH:-${DISCORD_SSH_WEBHOOK:-}}"
    ROLE_INFO="${DISCORD_ROLE_INFO:-}"

    if [ -z "$DISCORD_SSH_WEBHOOK" ]; then
        exit 0
    fi

    mention=""
    if [ -n "$ROLE_INFO" ]; then
        mention="<@&${ROLE_INFO}>"
    fi

    payload=$(python3 -c "import json; print(json.dumps({
        'username': 'SSH Gatekeeper',
        'avatar_url': 'https://livresenclasse.com/static/img/logo.png',
        'content': '''$mention''',
        'embeds': [{
            'title': '🔑 Connexion SSH interactive : ' + '$USER_NAME',
            'description': 'Une nouvelle session terminal SSH a été ouverte.',
            'color': 3447003,
            'fields': [
                {'name': 'Utilisateur', 'value': '$USER_NAME', 'inline': True},
                {'name': 'Serveur hôte', 'value': '$HOST_NAME', 'inline': True},
                {'name': 'IP source', 'value': '$CLIENT_IP', 'inline': True},
                {'name': 'Date & Heure', 'value': '$LOGIN_DATE', 'inline': False}
            ]
        }]
    }))" 2>/dev/null || echo "")

    if [ -n "$payload" ]; then
        curl -s -m 3 -H "Content-Type: application/json" -X POST -d "$payload" "$DISCORD_SSH_WEBHOOK" >/dev/null 2>&1 &
    fi
fi
