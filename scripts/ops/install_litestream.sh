#!/usr/bin/env bash
# ==============================================================================
# Script d'installation automatique de Litestream (Linux amd64 / arm64)
# ==============================================================================
set -euo pipefail

LITESTREAM_VERSION="v0.3.13"
ARCH=$(uname -m)

case "$ARCH" in
    x86_64)
        LITESTREAM_ARCH="amd64"
        ;;
    aarch64|arm64)
        LITESTREAM_ARCH="arm64"
        ;;
    *)
        echo "Architecture non supportée: $ARCH"
        exit 1
        ;;
esac

TAR_FILE="litestream-${LITESTREAM_VERSION}-linux-${LITESTREAM_ARCH}.tar.gz"
URL="https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/${TAR_FILE}"

echo "Téléchargement de Litestream ${LITESTREAM_VERSION} pour ${LITESTREAM_ARCH}..."
curl -sL "$URL" -o "/tmp/${TAR_FILE}"

echo "Extraction vers /usr/local/bin/litestream..."
sudo tar -C /usr/local/bin -xzf "/tmp/${TAR_FILE}" litestream
sudo chmod +x /usr/local/bin/litestream
rm -f "/tmp/${TAR_FILE}"

echo "Vérification de l'installation :"
/usr/local/bin/litestream version
echo "Litestream installé avec succès dans /usr/local/bin/litestream !"
