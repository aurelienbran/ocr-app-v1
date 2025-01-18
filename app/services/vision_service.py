from google.cloud import vision_v1
from loguru import logger
from pdf2image import convert_from_bytes
from typing import Dict, Any
import io
import asyncio
import traceback
import time

class VisionService:
    def __init__(self, credentials=None):
        try:
            self.client = vision_v1.ImageAnnotatorClient(credentials=credentials)
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
                    images = await asyncio.to_thread(convert_from_bytes, content)
                    logger.info(f"Successfully converted PDF to {len(images)} images")
                    image_bytes = await asyncio.to_thread(self._pil_to_bytes, images[0])
                    logger.info("First page converted to bytes successfully")
                except Exception as e:
                    logger.error(f"PDF conversion failed: {str(e)}\n{traceback.format_exc()}")
                    raise
            else:
                image_bytes = content

            # Configure features
            logger.info("Configuring Vision AI features")
            features = [
                vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.LABEL_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.OBJECT_LOCALIZATION)
            ]

            # Create and process request
            logger.info("Creating Vision AI request")
            image = vision_v1.Image(content=image_bytes)
            request = vision_v1.AnnotateImageRequest(image=image, features=features)

            logger.info("Sending request to Vision AI")
            response = await self._execute_request(request)
            logger.info("Received Vision AI response")

            result = self._process_response(response, filename)
            
            processing_time = time.time() - start_time
            logger.info(f"Vision AI processing completed in {processing_time:.2f} seconds")
            
            return result

        except Exception as e:
            logger.error(f"Error in Vision AI processing: {str(e)}\n{traceback.format_exc()}")
            raise

    def _pil_to_bytes(self, image) -> bytes:
        """Convert PIL image to bytes"""
        logger.info("Converting PIL image to bytes")
        try:
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            logger.info("Image conversion successful")
            return img_byte_arr.getvalue()
        except Exception as e:
            logger.error(f"Error converting image to bytes: {str(e)}\n{traceback.format_exc()}")
            raise

    async def _execute_request(self, request: vision_v1.AnnotateImageRequest) -> vision_v1.AnnotateImageResponse:
        """Execute Vision AI request"""
        try:
            logger.info("Starting Vision AI API call")
            start_time = time.time()
            
            response = await asyncio.to_thread(
                self.client.annotate_image,
                request
            )
            
            processing_time = time.time() - start_time
            logger.info(f"Vision AI API call completed in {processing_time:.2f} seconds")
            return response
            
        except Exception as e:
            logger.error(f"Vision AI API call failed: {str(e)}\n{traceback.format_exc()}")
            raise

    def _process_response(self, response: vision_v1.AnnotateImageResponse, filename: str) -> Dict[str, Any]:
        """Process Vision AI response"""
        logger.info("Processing Vision AI response")
        try:
            result = {
                'text': '',
                'labels': [],
                'metadata': {
                    'document_type': 'unknown',
                    'language': None,
                    'confidence': 0.0
                },
                'visual_elements': {
                    'objects': [],
                    'tables': []
                }
            }

            # Process text annotations
            if response.full_text_annotation:
                logger.info("Processing text annotations")
                result['text'] = response.full_text_annotation.text
                text_length = len(result['text'])
                logger.info(f"Extracted {text_length} characters of text")
                
                if response.full_text_annotation.pages:
                    result['metadata']['confidence'] = response.full_text_annotation.pages[0].confidence
                    logger.info(f"Text detection confidence: {result['metadata']['confidence']:.2%}")

            # Process labels
            if response.label_annotations:
                logger.info("Processing label annotations")
                result['labels'] = [{
                    'description': label.description,
                    'score': round(label.score, 4),
                    'topicality': round(label.topicality, 4)
                } for label in response.label_annotations]
                logger.info(f"Found {len(result['labels'])} labels")

            # Process detected objects
            if response.localized_object_annotations:
                logger.info("Processing object detections")
                result['visual_elements']['objects'] = [{
                    'name': obj.name,
                    'confidence': round(obj.score, 4),
                    'bounding_box': {
                        'left': obj.bounding_poly.normalized_vertices[0].x,
                        'top': obj.bounding_poly.normalized_vertices[0].y,
                        'right': obj.bounding_poly.normalized_vertices[2].x,
                        'bottom': obj.bounding_poly.normalized_vertices[2].y
                    }
                } for obj in response.localized_object_annotations]
                logger.info(f"Found {len(result['visual_elements']['objects'])} objects")

            logger.info("Vision AI response processing completed")
            return result

        except Exception as e:
            logger.error(f"Error processing Vision AI response: {str(e)}\n{traceback.format_exc()}")
            raise