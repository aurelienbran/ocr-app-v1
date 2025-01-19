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
import psutil
import gc

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

    def _log_memory_metrics(self, stage: str):
        """Log detailed memory metrics at different processing stages"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            logger.info(
                f"Memory metrics at {stage}:\n"
                f"  RSS: {memory_info.rss/1024/1024:.1f}MB\n"
                f"  VMS: {memory_info.vms/1024/1024:.1f}MB\n"
                f"  Percent: {process.memory_percent():.1f}%"
            )
        except Exception as e:
            logger.warning(f"Failed to log memory metrics: {str(e)}")

    async def analyze_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        temp_dir = None
        
        try:
            self._log_memory_metrics("start_analysis")
            
            # Convert PDF if necessary
            if filename.lower().endswith('.pdf'):
                logger.info(f"Starting PDF conversion for Vision AI: {filename}")
                logger.info(f"Input PDF size: {len(content)/1024/1024:.1f}MB")
                
                try:
                    # Create temporary directory for conversion
                    temp_dir = tempfile.mkdtemp(prefix="ocr_")
                    logger.info(f"Created temporary directory: {temp_dir}")
                    
                    self._log_memory_metrics("before_conversion")
                    
                    # Convert with optimized parameters
                    images = convert_from_bytes(
                        content,
                        output_folder=temp_dir,
                        fmt="png",
                        dpi=200,  # Lower DPI but sufficient for OCR
                        thread_count=1,  # Limit CPU usage
                        use_pdftocairo=True,  # More memory efficient
                        grayscale=True,  # Reduce memory usage
                        size=(1600, None),  # Limit max width
                        paths_only=True,  # Return paths instead of loading images
                        first_page=1,
                        last_page=1  # Only convert first page
                    )
                    
                    if not images:
                        raise ValueError("Failed to convert PDF to image")
                    
                    logger.info("PDF conversion successful")
                    
                    # Read the converted image
                    with open(images[0], 'rb') as img_file:
                        image_content = img_file.read()
                        
                    logger.info(f"Converted image size: {len(image_content)/1024/1024:.1f}MB")
                    self._log_memory_metrics("after_conversion")
                    
                except Exception as e:
                    logger.error(f"PDF conversion failed: {str(e)}\n{traceback.format_exc()}")
                    raise
                finally:
                    # Cleanup temporary directory
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

            # Configure features
            logger.info("Configuring Vision AI features")
            features = [
                vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.LABEL_DETECTION),
                vision_v1.Feature(type_=vision_v1.Feature.Type.TEXT_DETECTION)
            ]

            # Force garbage collection before Vision AI processing
            gc.collect()
            self._log_memory_metrics("before_vision_ai")

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

            # Final memory cleanup and metrics
            gc.collect()
            self._log_memory_metrics("end_analysis")
            
            processing_time = time.time() - start_time
            logger.info(f"Vision AI processing completed in {processing_time:.2f} seconds")
            
            return result

        except Exception as e:
            error_msg = f"Error in Vision AI processing: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise