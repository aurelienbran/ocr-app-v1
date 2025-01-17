from google.cloud import documentai, vision_v1
from google.cloud.documentai import Document
from loguru import logger
from app.services.vision_service import VisionService
from app.services.document_saver import DocumentSaver
from app.services.pdf_splitter import PDFSplitter
from typing import Dict, Any
import os
import asyncio

class OCRService:
    def __init__(self):
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        self.document_saver = DocumentSaver()
        self.vision_service = VisionService()
        self.pdf_splitter = PDFSplitter()

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

        # Configuration explicite de l'endpoint européen
        client_options = {"api_endpoint": "eu-documentai.googleapis.com"}
        self.documentai_client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        
        self.processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        try:
            # Split PDF if necessary and process with Document AI
            pdf_chunks = self.pdf_splitter.split_pdf(content)
            docai_tasks = [self._process_with_documentai(chunk) for chunk in pdf_chunks]
            docai_results = await asyncio.gather(*docai_tasks)
            docai_result = self._merge_docai_results(docai_results)

            # Process with Vision AI
            vision_result = await self.vision_service.analyze_document(content, filename)

            # Merge and save results
            final_result = self._merge_results(docai_result, vision_result)
            await self.document_saver.save_results(final_result, filename)

            return final_result

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
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
            merged['pages'].extend(result['pages'])

        return merged

    def _merge_results(self, docai_result: Dict[str, Any], vision_result: Dict[str, Any]) -> Dict[str, Any]:
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