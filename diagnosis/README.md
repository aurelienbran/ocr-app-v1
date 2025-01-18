# Diagnostic Mémoire OCR Application

## Prérequis

- Python 3.11+
- Bibliothèques requises :
  ```bash
  pip install psutil tracemalloc
  ```

## Utilisation

### Diagnostic Système Complet

```bash
python memory_diagnostic.py
```

### Diagnostic avec Fichier Spécifique

```bash
python memory_diagnostic.py /chemin/vers/votre/document.pdf
```

## Fonctionnalités

- Informations système détaillées
- Tracking de l'utilisation mémoire
- Log des allocations mémoire
- Analyse des fuites potentielles

## Outputs

Le script génère :
- Un fichier log `memory_diagnostic.log`
- Affichage en console des détails de diagnostic

## Conseils d'Interprétation

- Surveillez les "Memory Change"
- Analysez les top allocations mémoire
- Vérifiez les temps d'exécution

## Résolution des Problèmes

En cas de résultats inhabituels :
1. Vérifiez les versions de Python
2. Confirmez l'installation des dépendances
3. Assurez-vous de l'accès en lecture au fichier testé
