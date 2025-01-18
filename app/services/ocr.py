from google.cloud import documentai, vision_v1
from google.cloud.documentai import Document
from loguru import logger
from app.services.vision_service import VisionService
from app.services.document_saver import DocumentSaver
from app.services.pdf_splitter import PDFSplitter
from typing import Dict, Any, List
import os
import asyncio
import time
from google.api_core import retry
import tempfile

class OCRService:
    def __init__(self):
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        self.document_saver = DocumentSaver()
        self.vision_service = VisionService()
        self.pdf_splitter = PDFSplitter()
        self.processing_timeout = 300  # 5 minutes timeout
        self.temp_dir = tempfile.mkdtemp(prefix='ocr_processing_')

    def _validate_and_setup_env_variables(self):
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_CLOUD_LOCATION',
            'DOCUMENT_AI_PROCESSOR_ID'
        ]
        for var in required_vars:
            if not os.getenv(var):
                raise ValueError(f"Missing required environment variable: {var}")

    def _initialize_clients(self):
        location = os.getenv('GOOGLE_CLOUD_LOCATION')
        processor_id = os.getenv('DOCUMENT_AI_PROCESSOR_ID')
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

        client_options = {
            "api_endpoint": f"{location}-documentai.googleapis.com"
        }
        
        self.documentai_client = documentai.DocumentProcessorServiceClient(
            client_options=client_options
        )
        
        self.processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    def _cleanup(self):
        """Nettoie les fichiers temporaires"""
        try:
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temporary files: {str(e)}")

    def __del__(self):
        """Assure le nettoyage à la destruction"""
        self._cleanup()

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            logger.info(f"Starting processing for {filename}")

            # Split PDF if necessary
            pdf_chunks = self.pdf_splitter.split_pdf(content)
            num_chunks = len(pdf_chunks)
            logger.info(f"Split PDF into {num_chunks} chunks")

            # Process chunks sequentially to manage memory
            docai_results = []
            for i, chunk in enumerate(pdf_chunks, 1):
                logger.info(f"Processing chunk {i}/{num_chunks}")
                try:
                    # Save chunk to temp file to reduce memory usage
                    chunk_path = os.path.join(self.temp_dir, f'chunk_{i}.pdf')
                    with open(chunk_path, 'wb') as f:
                        f.write(chunk)

                    # Process chunk
                    result = await self._process_chunk_with_timeout(chunk_path, i)
                    if result:
                        docai_results.append(result)

                    # Clean up chunk file
                    os.remove(chunk_path)

                except Exception as e:
                    logger.error(f"Error processing chunk {i}: {str(e)}")
                    # Continue with next chunk even if this one fails

                # Force garbage collection after each chunk
                del chunk
                import gc
                gc.collect()

            if not docai_results:
                raise Exception("All document processing chunks failed")

            # Merge results from successful chunks
            docai_result = self._merge_docai_results(docai_results)

            # Process with Vision AI
            vision_result = await self.vision_service.analyze_document(content, filename)

            # Merge and save results
            final_result = self._merge_results(docai_result, vision_result)

            processing_time = time.time() - start_time
            logger.info(f"Processing completed in {processing_time:.2f} seconds")

            # Save results
            await self.document_saver.save_results(final_result, filename)

            return final_result

        except Exception as e:
            logger.error(f"Error processing document {filename}: {str(e)}")
            raise

        finally:
            # Clean up any remaining temporary files
            self._cleanup()

    async def _process_chunk_with_timeout(self, chunk_path: str, chunk_index: int) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._process_with_documentai(chunk_path),
                timeout=self.processing_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Chunk {chunk_index} processing timed out")
            return None
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index}: {str(e)}")
            return None

    async def _process_with_documentai(self, chunk_path: str) -> Dict[str, Any]:
        try:
            with open(chunk_path, 'rb') as f:
                content = f.read()

            raw_document = documentai.RawDocument(
                content=content,
                mime_type="application/pdf"
            )
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document
            )

            # Utiliser to_thread pour le traitement asynchrone
            result = await asyncio.to_thread(
                self.documentai_client.process_document,
                request=request
            )

            return self._process_docai_response(result.document)

        except Exception as e:
            logger.error(f"Error in Document AI processing: {str(e)}")
            raise

    def _process_docai_response(self, document: Document) -> Dict[str, Any]:
        return {
            'text': document.text,
            'pages': [{
                'page_number': page.page_number,
                'dimensions': {
                    'width': page.dimension.width,
                    'height': page.dimension.height
                },
                'layout': {
                    'confidence': round(page.layout.confidence, 4)
                }
            } for page in document.pages]
        }

    def _merge_docai_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not results:
            return {}

        # Start with a deep copy of the first result to avoid modifications
        from copy import deepcopy
        merged = deepcopy(results[0])

        # Combine texts with proper spacing
        merged['text'] = '\n\n'.join(r.get('text', '') for r in results if r.get('text'))

        # Merge pages and ensure proper page numbering
        merged['pages'] = []
        current_page = 1

        for result in results:
            pages = result.get('pages', [])
            for page in pages:
                page_copy = deepcopy(page)
                page_copy['page_number'] = current_page
                merged['pages'].append(page_copy)
                current_page += 1

        return merged

    def _merge_results(self, docai_result: Dict[str, Any], vision_result: Dict[str, Any]) -> Dict[str, Any]:
        """Fusionne les résultats de Document AI et Vision AI"""
        try:
            if not docai_result and not vision_result:
                raise ValueError("Both Document AI and Vision AI results are empty")

            return {
                'metadata': {
                    **vision_result.get('metadata', {}),
                    'docai_confidence': docai_result.get('pages', [{}])[0].get('layout', {}).get('confidence', 0.0),
                    'processors': ['documentai', 'vision']
                },
                'text': {
                    'docai': docai_result.get('text', ''),
                    'vision': vision_result.get('text', '')
                },
                'pages': docai_result.get('pages', []),
                'visual_elements': vision_result.get('visual_elements', {}),
                'classifications': vision_result.get('classifications', {})
            }
        except Exception as e:
            logger.error(f"Error merging results: {str(e)}")
            raise