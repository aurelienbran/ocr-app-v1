# Guide de Déploiement - OCR Application

## Mise à Jour du Service (19 Janvier 2025)

### Changements Majeurs
1. Optimisation de la conversion PDF
   - Utilisation de dossiers temporaires
   - Réduction de la consommation mémoire
   - Paramètres optimisés pour pdf2image
   - Gestion améliorée des ressources

2. Configuration Systemd
   - Limites mémoire ajustées
   - Gestion OOM optimisée
   - Support des fichiers temporaires
   - Permissions ajustées

3. Monitoring
   - Métriques mémoire détaillées
   - Logs améliorés
   - Suivi des performances

### Prérequis Système
- Python 3.11+
- poppler-utils
- Minimum 8GB RAM
- 4 CPU cores recommandés

### Instructions de Mise à Jour

1. Sauvegarde préalable
```bash
sudo cp /etc/systemd/system/ocr-app.service /etc/systemd/system/ocr-app.service.backup
sudo systemctl stop ocr-app
```

2. Exécution du script de mise à jour
```bash
cd /opt/ocr-app/ocr-app-v1
sudo ./deployment/update_service.sh
```

3. Vérification post-déploiement
```bash
# Vérifier le statut du service
sudo systemctl status ocr-app

# Consulter les logs
sudo journalctl -u ocr-app -f
```

### Restauration en Cas de Problème
```bash
# Restaurer l'ancienne version du service
sudo cp /etc/systemd/system/ocr-app.service.backup /etc/systemd/system/ocr-app.service
sudo systemctl daemon-reload
sudo systemctl restart ocr-app
```

### Monitoring et Maintenance

#### Surveillance des Ressources
```bash
# Utilisation mémoire
ps aux | grep ocr-app
free -h

# Logs en temps réel
sudo journalctl -u ocr-app -f
```

#### Points de Vérification
- [x] Statut du service actif
- [x] Logs sans erreurs
- [x] Utilisation mémoire stable
- [x] Traitement PDF fonctionnel
- [x] Permissions des dossiers correctes

### Configuration Systemd

La nouvelle configuration inclut :
- Limites mémoire : 8GB max
- Protection OOM optimisée
- Gestion des fichiers temporaires
- Quotas CPU ajustés

### Dépannage

1. Problèmes de Mémoire
```bash
# Vérifier l'utilisation mémoire
free -h
ps aux | grep ocr-app

# Nettoyer le cache système si nécessaire
sudo sync && sudo echo 3 > /proc/sys/vm/drop_caches
```

2. Erreurs de Permission
```bash
# Vérifier les permissions
ls -la /opt/ocr-app/ocr-app-v1/documents
ls -la /opt/ocr-app/ocr-app-v1/logs

# Corriger si nécessaire
sudo chown -R ubuntu:ubuntu /opt/ocr-app/ocr-app-v1/documents
sudo chown -R ubuntu:ubuntu /opt/ocr-app/ocr-app-v1/logs
```

3. Problèmes de Service
```bash
# Vérifier les journaux détaillés
sudo journalctl -u ocr-app -n 100 --no-pager

# Redémarrer le service
sudo systemctl restart ocr-app
```

### Contact et Support

Pour toute question ou problème :
1. Vérifier les logs système
2. Consulter la documentation
3. Contacter l'équipe de développement