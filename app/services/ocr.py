from google.cloud import documentai
from google.cloud.documentai import Document
from loguru import logger
import os
import asyncio
import time
import gc
import tempfile
import psutil
from typing import Dict, Any, Optional, List
from datetime import datetime
import traceback

from app.services.vision_service import VisionService
from app.services.pdf_splitter import PDFSplitter
from app.services.document_saver import DocumentSaver
from app.services.cache_manager import CacheManager

class ChunkProcessor:
    def __init__(self, max_concurrent: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cache = CacheManager()
        logger.info(f"ChunkProcessor initialized with {max_concurrent} concurrent tasks")

    async def process_chunks(
        self,
        chunks: List[bytes],
        processor_name: str,
        documentai_client: documentai.DocumentProcessorServiceClient
    ) -> List[Dict[str, Any]]:
        async def process_single_chunk(chunk: bytes, index: int) -> Dict[str, Any]:
            logger.info(f"Starting to process chunk {index}")
            async with self.semaphore:
                cache_key = f"{self.cache._get_hash(chunk)}"
                if cached_result := await self.cache.get(cache_key):
                    logger.info(f"Using cached result for chunk {index}")
                    return cached_result

                try:
                    logger.info(f"Sending chunk {index} to Document AI")
                    raw_document = documentai.RawDocument(
                        content=chunk,
                        mime_type="application/pdf"
                    )
                    request = documentai.ProcessRequest(
                        name=processor_name,
                        raw_document=raw_document
                    )

                    result = await asyncio.to_thread(
                        documentai_client.process_document,
                        request=request
                    )
                    logger.info(f"Received Document AI response for chunk {index}")

                    processed_result = {
                        'text': result.document.text,
                        'pages': [{
                            'page_number': page.page_number,
                            'dimensions': {
                                'width': page.dimension.width,
                                'height': page.dimension.height
                            },
                            'layout': {
                                'confidence': round(page.layout.confidence, 4)
                            }
                        } for page in result.document.pages],
                        'timestamp': datetime.now().isoformat()
                    }

                    await self.cache.set(cache_key, processed_result)
                    logger.info(f"Successfully processed chunk {index}")
                    return processed_result

                except Exception as e:
                    logger.error(f"Error processing chunk {index}: {str(e)}\n{traceback.format_exc()}")
                    return None

        # Traiter les chunks avec gestion d'erreur améliorée
        processed_results = []
        for index, chunk in enumerate(chunks):
            try:
                logger.info(f"Processing chunk {index}/{len(chunks)}")
                result = await process_single_chunk(chunk, index)
                if result:
                    processed_results.append(result)
                    logger.info(f"Added result for chunk {index}")
            except Exception as e:
                logger.error(f"Failed to process chunk {index}: {str(e)}\n{traceback.format_exc()}")

        logger.info(f"Completed chunk processing. Successful: {len(processed_results)}/{len(chunks)}")
        return processed_results

class OCRService:
    def __init__(
        self,
        max_chunk_pages: int = 10,
        max_concurrent_chunks: int = 3,
        processing_timeout: int = 1800
    ):
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        
        self.max_chunk_pages = max_chunk_pages
        self.processing_timeout = processing_timeout
        
        self.pdf_splitter = PDFSplitter(max_pages_per_chunk=max_chunk_pages)
        self.vision_service = VisionService()
        self.document_saver = DocumentSaver()
        self.chunk_processor = ChunkProcessor(max_concurrent=max_concurrent_chunks)
        
        self.temp_dir = tempfile.mkdtemp(prefix='ocr_processing_')
        logger.info(f"OCR Service initialized with {max_concurrent_chunks} concurrent chunks")

    def _validate_and_setup_env_variables(self):
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_CLOUD_LOCATION',
            'DOCUMENT_AI_PROCESSOR_ID'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    def _initialize_clients(self):
        try:
            location = os.getenv('GOOGLE_CLOUD_LOCATION')
            processor_id = os.getenv('DOCUMENT_AI_PROCESSOR_ID')
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

            client_options = {"api_endpoint": f"{location}-documentai.googleapis.com"}
            
            self.documentai_client = documentai.DocumentProcessorServiceClient(
                client_options=client_options
            )
            
            self.processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
            logger.info("Document AI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud clients: {str(e)}\n{traceback.format_exc()}")
            raise

    def _cleanup(self):
        try:
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}\n{traceback.format_exc()}")

    def __del__(self):
        self._cleanup()

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        chunks = []
        temp_results_file = os.path.join(self.temp_dir, f"{filename}_results.jsonl")
        
        try:
            logger.info(f"Starting OCR processing of {filename}")
            
            # 1. Split document into chunks
            logger.info("Starting document splitting")
            async for chunk in self.pdf_splitter.split_pdf(content):
                chunks.append(chunk)
            logger.info(f"Split document into {len(chunks)} chunks")
            
            # 2. Process chunks with Document AI
            logger.info("Starting Document AI processing")
            results = await self.chunk_processor.process_chunks(
                chunks,
                self.processor_name,
                self.documentai_client
            )
            logger.info(f"Successfully processed {len(results)} chunks with Document AI")
            
            # 3. Save chunk results
            logger.info("Starting to save chunk results")
            for chunk_result in results:
                await self.document_saver.append_result(temp_results_file, chunk_result)
            logger.info("Finished saving chunk results")
            
            # 4. Vision AI analysis
            logger.info("Starting Vision AI analysis")
            vision_result = {}
            try:
                vision_result = await asyncio.wait_for(
                    self.vision_service.analyze_document(content, filename),
                    timeout=300  # 5 minutes timeout for Vision AI
                )
                logger.info("Vision AI analysis completed successfully")
            except asyncio.TimeoutError:
                logger.error("Vision AI analysis timed out")
            except Exception as e:
                logger.error(f"Vision AI analysis failed: {str(e)}\n{traceback.format_exc()}")
            
            # 5. Prepare final results
            metadata = {
                'filename': filename,
                'processing_time': time.time() - start_time,
                'chunks_processed': len(results),
                'total_chunks': len(chunks),
                'vision_ai_processed': bool(vision_result),
                'visual_elements': vision_result.get('visual_elements', {}),
                'classifications': vision_result.get('classifications', {})
            }
            
            # 6. Save final results
            logger.info("Starting final save")
            save_paths = await self.document_saver.save_final_results(
                temp_results_file,
                filename,
                metadata
            )
            logger.info(f"Final results saved to: {save_paths}")
            
            processing_time = time.time() - start_time
            logger.info(
                f"Processing completed in {processing_time:.1f}s. "
                f"Processed {len(results)}/{len(chunks)} chunks"
            )
            
            return {
                'status': 'success',
                'metadata': metadata,
                'file_paths': save_paths
            }

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}\n{traceback.format_exc()}")
            raise

        finally:
            # Cleanup
            logger.info("Starting cleanup")
            for chunk in chunks:
                del chunk
            if os.path.exists(temp_results_file):
                try:
                    os.remove(temp_results_file)
                    logger.info("Cleaned up temporary results file")
                except Exception as e:
                    logger.error(f"Error cleaning up temp file: {str(e)}")
            gc.collect()
            logger.info("Cleanup completed")