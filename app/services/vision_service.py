from google.cloud import vision_v1
from loguru import logger
from typing import Dict, Any
import asyncio
from pdf2image import convert_from_bytes
from io import BytesIO
import traceback
import time

class VisionService:
    def __init__(self, credentials=None):
        try:
            # Configuration de l'endpoint régional
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
        try:
            # Convert PDF if necessary
            if filename.lower().endswith('.pdf'):
                logger.info(f"Starting PDF conversion for Vision AI: {filename}")
                try:
                    images = convert_from_bytes(content)
                    if not images:
                        raise ValueError("Failed to convert PDF to image")
                    logger.info(f"Successfully converted PDF to {len(images)} images")
                    
                    # Use first page for analysis
                    img_byte_arr = BytesIO()
                    images[0].save(img_byte_arr, format='PNG')
                    image_content = img_byte_arr.getvalue()
                    logger.info("First page converted to bytes successfully")
                except Exception as e:
                    logger.error(f"PDF conversion failed: {str(e)}\n{traceback.format_exc()}")
                    raise
            else:
                image_content = content

            # Configure features
            logger.info("Configuring Vision AI features")
            features = [
                vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.LABEL_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.TEXT_DETECTION)
            ]

            # Create request
            logger.info("Creating Vision AI request")
            image = vision_v1.Image(content=image_content)
            request = vision_v1.AnnotateImageRequest(
                image=image,
                features=features
            )

            # Process asynchronously
            logger.info("Sending request to Vision AI")
            response = await asyncio.to_thread(
                self.client.annotate_image,
                request=request
            )
            logger.info("Received Vision AI response")

            # Process response
            result = {
                'text': '',
                'labels': [],
                'metadata': {
                    'document_type': 'unknown',
                    'language': None,
                    'confidence': 0.0
                }
            }

            # Extract document text if available
            if response.full_text_annotation:
                logger.info("Processing text annotations")
                result['text'] = response.full_text_annotation.text
                text_length = len(result['text'])
                logger.info(f"Extracted {text_length} characters of text")
                
                if response.full_text_annotation.pages:
                    result['metadata']['confidence'] = response.full_text_annotation.pages[0].confidence
                    logger.info(f"Text detection confidence: {result['metadata']['confidence']:.2%}")
                
                # Try to detect document type from labels
                for label in response.label_annotations:
                    result['labels'].append({
                        'description': label.description,
                        'score': label.score,
                        'topicality': label.topicality
                    })
                    if label.score > 0.8:  # High confidence label
                        if any(keyword in label.description.lower() for keyword in 
                              ['schematic', 'diagram', 'technical', 'drawing']):
                            result['metadata']['document_type'] = 'technical_drawing'

            # Detect language if available
            if response.text_annotations and response.text_annotations[0].locale:
                result['metadata']['language'] = response.text_annotations[0].locale
                logger.info(f"Detected language: {result['metadata']['language']}")

            processing_time = time.time() - start_time
            logger.info(f"Vision AI processing completed in {processing_time:.2f} seconds")
            
            return result

        except Exception as e:
            error_msg = f"Error in Vision AI processing: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise