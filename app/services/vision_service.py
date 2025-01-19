from google.cloud import vision_v1
from loguru import logger
from typing import Dict, Any
import asyncio
from pdf2image import convert_from_bytes
from io import BytesIO
import traceback
import time
import tempfile
import os
import gc

class VisionService:
    def __init__(self, credentials=None):
        try:
            client_options = {"api_endpoint": "eu-vision.googleapis.com"}
            self.client = vision_v1.ImageAnnotatorClient(
                client_options=client_options,
                credentials=credentials
            )
            logger.info("Vision AI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Vision AI client: {str(e)}\n{traceback.format_exc()}")
            raise

    async def analyze_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        temp_dir = None
        
        try:
            if filename.lower().endswith('.pdf'):
                logger.info(f"Starting PDF conversion for Vision AI: {filename}")
                logger.info(f"Input PDF size: {len(content)/1024/1024:.1f}MB")
                
                try:
                    # Utiliser un dossier temporaire pour la conversion
                    temp_dir = tempfile.mkdtemp(prefix="ocr_")
                    logger.info(f"Created temporary directory: {temp_dir}")
                    
                    # Convertir avec des paramètres optimisés
                    images = convert_from_bytes(
                        content,
                        output_folder=temp_dir,
                        fmt="png",
                        dpi=200,  # Résolution réduite mais suffisante pour OCR
                        thread_count=1,  # Limite l'utilisation CPU
                        use_pdftocairo=True,  # Plus efficace que pdftoppm
                        grayscale=True,  # Réduit l'utilisation mémoire
                        size=(1600, None),  # Limite la largeur max
                        paths_only=True,  # Retourne les chemins au lieu de charger les images
                        first_page=1,
                        last_page=1  # Ne convertir que la première page
                    )
                    
                    if not images:
                        raise ValueError("Failed to convert PDF to image")
                    
                    logger.info("PDF conversion successful")
                    
                    # Lire l'image convertie
                    with open(images[0], 'rb') as img_file:
                        image_content = img_file.read()
                    
                    logger.info(f"Converted image size: {len(image_content)/1024/1024:.1f}MB")
                
                except Exception as e:
                    logger.error(f"PDF conversion failed: {str(e)}\n{traceback.format_exc()}")
                    raise
                finally:
                    # Nettoyer le dossier temporaire
                    if temp_dir and os.path.exists(temp_dir):
                        try:
                            for file in os.listdir(temp_dir):
                                os.remove(os.path.join(temp_dir, file))
                            os.rmdir(temp_dir)
                            logger.info("Cleaned up temporary directory")
                        except Exception as e:
                            logger.warning(f"Failed to clean temporary directory: {str(e)}")
            else:
                image_content = content

            # Configuration des features
            logger.info("Configuring Vision AI features")
            features = [
                vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.LABEL_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.TEXT_DETECTION)
            ]

            # Forcer le garbage collection avant le traitement Vision AI
            gc.collect()

            # Créer la requête
            logger.info("Creating Vision AI request")
            image = vision_v1.Image(content=image_content)
            request = vision_v1.AnnotateImageRequest(
                image=image,
                features=features
            )

            # Traitement asynchrone
            logger.info("Sending request to Vision AI")
            response = await asyncio.to_thread(
                self.client.annotate_image,
                request=request
            )
            logger.info("Received Vision AI response")

            # Traiter la réponse
            result = {
                'text': '',
                'labels': [],
                'metadata': {
                    'document_type': 'unknown',
                    'language': None,
                    'confidence': 0.0
                }
            }

            # Extraire le texte si disponible
            if response.full_text_annotation:
                logger.info("Processing text annotations")
                result['text'] = response.full_text_annotation.text
                text_length = len(result['text'])
                logger.info(f"Extracted {text_length} characters of text")
                
                if response.full_text_annotation.pages:
                    result['metadata']['confidence'] = response.full_text_annotation.pages[0].confidence
                    logger.info(f"Text detection confidence: {result['metadata']['confidence']:.2%}")
                
                # Détecter le type de document depuis les labels
                for label in response.label_annotations:
                    result['labels'].append({
                        'description': label.description,
                        'score': label.score,
                        'topicality': label.topicality
                    })
                    if label.score > 0.8:  # Label avec haute confiance
                        if any(keyword in label.description.lower() for keyword in 
                              ['schematic', 'diagram', 'technical', 'drawing']):
                            result['metadata']['document_type'] = 'technical_drawing'

            # Détecter la langue si disponible
            if response.text_annotations and response.text_annotations[0].locale:
                result['metadata']['language'] = response.text_annotations[0].locale
                logger.info(f"Detected language: {result['metadata']['language']}")

            # Nettoyage final et métriques
            gc.collect()
            
            processing_time = time.time() - start_time
            logger.info(f"Vision AI processing completed in {processing_time:.2f} seconds")
            
            return result

        except Exception as e:
            error_msg = f"Error in Vision AI processing: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise