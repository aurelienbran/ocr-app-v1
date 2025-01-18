from google.cloud import documentai, vision_v1
from google.cloud.documentai import Document
from loguru import logger
from app.services.vision_service import VisionService
from app.services.document_saver import DocumentSaver
from app.services.pdf_splitter import PDFSplitter
from typing import Dict, Any
import os
import asyncio
import time
from google.api_core import retry

class OCRService:
    def __init__(self):
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        self.document_saver = DocumentSaver()
        self.vision_service = VisionService()
        self.pdf_splitter = PDFSplitter()
        self.processing_timeout = 300  # 5 minutes timeout

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

        # Configuration de l'endpoint européen
        client_options = {
            "api_endpoint": f"{location}-documentai.googleapis.com"
        }
        
        self.documentai_client = documentai.DocumentProcessorServiceClient(
            client_options=client_options
        )
        
        self.processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    @retry.Retry(
        initial=1.0,
        maximum=60.0,
        multiplier=2.0,
        predicate=retry.if_exception_type(
            TimeoutError,
            ConnectionError
        )
    )
    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            logger.info(f"Starting processing for {filename}")

            # Split PDF if necessary and process with Document AI
            pdf_chunks = self.pdf_splitter.split_pdf(content)
            logger.info(f"Split PDF into {len(pdf_chunks)} chunks")

            # Process chunks with timeout
            docai_tasks = []
            for i, chunk in enumerate(pdf_chunks):
                task = asyncio.create_task(self._process_chunk_with_timeout(chunk, i))
                docai_tasks.append(task)

            # Wait for all chunks with timeout
            docai_results = await asyncio.gather(*docai_tasks, return_exceptions=True)
            
            # Filter out any failed chunks
            successful_results = []
            for result in docai_results:
                if isinstance(result, Exception):
                    logger.error(f"Chunk processing failed: {str(result)}")
                else:
                    successful_results.append(result)

            if not successful_results:
                raise Exception("All document processing chunks failed")

            # Merge results from successful chunks
            docai_result = self._merge_docai_results(successful_results)

            # Process with Vision AI in parallel
            vision_task = asyncio.create_task(self.vision_service.analyze_document(content, filename))
            vision_result = await vision_task

            # Merge and save results
            final_result = self._merge_results(docai_result, vision_result)

            processing_time = time.time() - start_time
            logger.info(f"Processing completed in {processing_time:.2f} seconds")

            # Save results asynchronously
            await self.document_saver.save_results(final_result, filename)

            return final_result

        except Exception as e:
            logger.error(f"Error processing document {filename}: {str(e)}")
            raise

    async def _process_chunk_with_timeout(self, chunk: bytes, chunk_index: int) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._process_with_documentai(chunk),
                timeout=self.processing_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Chunk {chunk_index} processing timed out")
            raise
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index}: {str(e)}")
            raise

    async def _process_with_documentai(self, content: bytes) -> Dict[str, Any]:
        try:
            raw_document = documentai.RawDocument(content=content, mime_type="application/pdf")
            request = documentai.ProcessRequest(name=self.processor_name, raw_document=raw_document)
            
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

    def _merge_docai_results(self, results: list) -> Dict[str, Any]:
        if not results:
            return {}

        merged = results[0].copy()
        merged['text'] = '\n'.join(r['text'] for r in results)
        merged['pages'] = []

        for result in results:
            merged['pages'].extend(result.get('pages', []))

        # Trier les pages par numéro
        merged['pages'].sort(key=lambda x: x['page_number'])

        return merged

    def _merge_results(self, docai_result: Dict[str, Any], vision_result: Dict[str, Any]) -> Dict[str, Any]:
        if not docai_result or not vision_result:
            logger.warning("One or both processing results are empty")

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