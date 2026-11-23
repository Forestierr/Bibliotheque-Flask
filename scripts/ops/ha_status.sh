#!/usr/bin/env bash
# ==============================================================================
# Contrôle d'état Haute Disponibilité en temps réel (1 seconde)
# Vérifie : DNS Cloudflare, Sondes /healthy, Sentinelle Oracle, Litestream
# ==============================================================================

set -euo pipefail

CF_EMAIL="robinforestier1407@gmail.com"
CF_KEY="737093cba7a984125c2ed1a8b03798654cf8e"
CF_ZONE_ID="ab629cd54d5b8d91c13d651470d17fcd"
CF_RECORD_ID_APP="e02e6467e916b7c5a15fce799a741dae"

TUNNEL_LOCAL="8086dee7-aee1-48c4-9166-be6f361172e5.cfargotunnel.com"
TUNNEL_ORACLE="d6f9880e-8118-4509-8a85-9162face663d.cfargotunnel.com"

# Couleurs ANSI
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}====================================================================${NC}"
echo -e "${BOLD}=== CONTRÔLE HAUTE DISPONIBILITÉ - LIVRESENCLASSE.COM ===${NC}"
echo -e "${BOLD}====================================================================${NC}"

# 1. Vérification DNS Cloudflare
echo -n "1. Cible active Cloudflare  : "
CF_RESPONSE=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${CF_RECORD_ID_APP}" \
    -H "X-Auth-Email: ${CF_EMAIL}" \
    -H "X-Auth-Key: ${CF_KEY}")

CURRENT_TARGET=$(echo "$CF_RESPONSE" | grep -o '"content":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ "$CURRENT_TARGET" = "$TUNNEL_LOCAL" ]; then
    echo -e "${GREEN}${BOLD}SERVEUR LOCAL (Principal)${NC}"
    echo -e "   Tunnel actif : Local (${CURRENT_TARGET:0:8}...)"
elif [ "$CURRENT_TARGET" = "$TUNNEL_ORACLE" ]; then
    echo -e "${RED}${BOLD}SERVEUR ORACLE CLOUD (Mode Secours Actif !)${NC}"
    echo -e "   Tunnel actif : Oracle Cloud (${CURRENT_TARGET:0:8}...)"
else
    echo -e "${YELLOW}Cible inconnue : $CURRENT_TARGET${NC}"
fi

# 2. Sonde technique publique (/healthy)
echo -n "2. Sonde publique (/healthy) : "
HEALTH_JSON=$(curl -s -m 5 https://livresenclasse.com/healthy || echo '{"status":"down"}')
HEALTH_STATUS=$(echo "$HEALTH_JSON" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "down")
HEALTH_SERVER=$(echo "$HEALTH_JSON" | grep -o '"server":"[^"]*"' | cut -d'"' -f4 || echo "inconnu")

if [ "$HEALTH_STATUS" = "ok" ]; then
    echo -e "${GREEN}200 OK${NC} (Noeud déclaré : ${CYAN}${HEALTH_SERVER}${NC})"
else
    echo -e "${RED}ERREUR / INDISPONIBLE${NC}"
fi

# 3. Sonde Oracle Backup direct
echo -n "3. Standby Oracle (backup)  : "
BACKUP_CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" https://backup.livresenclasse.com/healthy || echo "000")
if [ "$BACKUP_CODE" = "200" ]; then
    echo -e "${GREEN}200 OK (Standby opérationnel)${NC}"
else
    echo -e "${YELLOW}Code HTTP : $BACKUP_CODE${NC}"
fi

# 4. État du verrou de failover sur Oracle
echo -n "4. Sentinelle Oracle Cloud  : "
if ssh -o BatchMode=yes -o ConnectTimeout=3 oracle-biblio "test -f /home/ubuntu/livresenclasse/FAILOVER_ACTIVE" 2>/dev/null; then
    echo -e "${RED}${BOLD}VERROU ACTIF (Failover en cours !)${NC}"
    echo -e "   👉 Pour réintégrer vos données et revenir en local : ${BOLD}./scripts/ops/failback_from_cloud.sh${NC}"
else
    echo -e "${GREEN}Normal (Mode veille passive, prêt à basculer)${NC}"
fi

# 5. État Litestream Local
echo -n "5. Réplication Litestream   : "
if systemctl --user is-active litestream >/dev/null 2>&1; then
    echo -e "${GREEN}Actif (Flux WAL continu < 1s vers Oracle)${NC}"
else
    echo -e "${YELLOW}Inactif sur cette machine ou vérification distante requise${NC}"
fi

echo -e "${BOLD}====================================================================${NC}"
