# Guide d'Optimisation Mémoire - Application OCR

## Contexte du Problème
L'application OCR rencontre des erreurs OOM (Out of Memory) lors du traitement de documents PDF volumineux, particulièrement durant le traitement par Document AI de Google Cloud.

## État Initial
- Erreur : `ocr-app.service: Failed with result 'oom-kill'`
- Se produit après le découpage du PDF en chunks
- Survient généralement pendant le traitement des derniers chunks
- Configuration initiale inadéquate pour la