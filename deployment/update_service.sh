#!/bin/bash

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Fonction de logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

# Vérifier si l'utilisateur est root
if [ "$EUID" -ne 0 ]; then
    error "Ce script doit être exécuté en tant que root"
    exit 1
fi

# Chemin de l'application
APP_PATH="/opt/ocr-app/ocr-app-v1"
SERVICE_NAME="ocr-app"

# Backup du service existant
log "Sauvegarde de la configuration du service existant"
if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    cp "/etc/systemd/system/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service.backup"
    log "Backup créé: ${SERVICE_NAME}.service.backup"
fi

# Vérification des dépendances
log "Vérification des dépendances système"
if ! command -v poppler-utils > /dev/null; then
    log "Installation de poppler-utils"
    apt-get update && apt-get install -y poppler-utils
fi

# Mise à jour du code
log "Mise à jour du code source"
cd $APP_PATH || exit 1
git fetch
git checkout fix/pdf-conversion-memory
git pull

# Activation de l'environnement virtuel et mise à jour des dépendances
log "Mise à jour des dépendances Python"
source venv/bin/activate
pip install -r requirements.txt

# Copie du nouveau fichier de service
log "Mise à jour de la configuration systemd"
cp deployment/ocr-app.service /etc/systemd/system/

# Création/Vérification des répertoires nécessaires
log "Vérification des répertoires"
mkdir -p "${APP_PATH}/documents"
mkdir -p "${APP_PATH}/logs"
chown -R ubuntu:ubuntu "${APP_PATH}/documents"
chown -R ubuntu:ubuntu "${APP_PATH}/logs"

# Reload systemd et redémarrage du service
log "Rechargement de la configuration systemd"
systemctl daemon-reload

log "Redémarrage du service"
systemctl restart $SERVICE_NAME

# Vérification du statut
sleep 5
if systemctl is-active --quiet $SERVICE_NAME; then
    log "Service démarré avec succès"
    systemctl status $SERVICE_NAME --no-pager
else
    error "Erreur lors du démarrage du service"
    systemctl status $SERVICE_NAME --no-pager
    
    # Restauration du backup si le service ne démarre pas
    warn "Restauration de la configuration précédente"
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service.backup" ]; then
        mv "/etc/systemd/system/${SERVICE_NAME}.service.backup" "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
        systemctl restart $SERVICE_NAME
        if systemctl is-active --quiet $SERVICE_NAME; then
            log "Service restauré et redémarré avec succès"
        else
            error "Échec de la restauration du service"
        fi
    fi
    exit 1
fi

# Nettoyage
rm -f "/etc/systemd/system/${SERVICE_NAME}.service.backup"
log "Mise à jour terminée avec succès"

# Affichage des derniers logs
log "Derniers logs du service:"
journalctl -u $SERVICE_NAME -n 50 --no-pager