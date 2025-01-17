from google.cloud import vision_v1
from loguru import logger
from pdf2image import convert_from_bytes
from typing import Dict, Any
import io
import asyncio

class VisionService:
    def __init__(self, credentials=None):
        self.client = vision_v1.ImageAnnotatorClient(credentials=credentials)

    async def analyze_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        try:
            # Convert PDF if necessary
            if filename.lower().endswith('.pdf'):
                images = await asyncio.to_thread(convert_from_bytes, content)
                image_bytes = await asyncio.to_thread(self._pil_to_bytes, images[0])
            else:
                image_bytes = content

            # Configure features
            features = [
                vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.LABEL_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.OBJECT_LOCALIZATION)
            ]

            # Create and process request
            image = vision_v1.Image(content=image_bytes)
            request = vision_v1.AnnotateImageRequest(image=image, features=features)

            response = await self._execute_request(request)
            return self._process_response(response, filename)

        except Exception as e:
            logger.error(f"Error in Vision AI processing: {str(e)}")
            raise

    def _pil_to_bytes(self, image) -> bytes:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()

    async def _execute_request(self, request: vision_v1.AnnotateImageRequest) -> vision_v1.AnnotateImageResponse:
        response = await asyncio.to_thread(
            self.client.annotate_image,
            request
        )
        return response

    def _process_response(self, response: vision_v1.AnnotateImageResponse, filename: str) -> Dict[str, Any]:
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
            result['text'] = response.full_text_annotation.text
            if response.full_text_annotation.pages:
                result['metadata']['confidence'] = response.full_text_annotation.pages[0].confidence

        # Process labels
        if response.label_annotations:
            result['labels'] = [{
                'description': label.description,
                'score': round(label.score, 4),
                'topicality': round(label.topicality, 4)
            } for label in response.label_annotations]

        # Process detected objects
        if response.localized_object_annotations:
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

        return result