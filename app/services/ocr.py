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

from app.services.vision_service import VisionService
from app.services.pdf_splitter import PDFSplitter
from app.services.document_saver import DocumentSaver
from app.services.cache_manager import CacheManager

class ChunkProcessor:
    def __init__(self, max_concurrent: int = 3):
        """
        Gestionnaire de traitement parallèle des chunks
        
        :param max_concurrent: Nombre maximum de chunks traités en parallèle
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cache = CacheManager()
        logger.info(f"ChunkProcessor initialized with {max_concurrent} concurrent tasks")

    async def process_chunks(
        self,
        chunks: List[bytes],
        processor_name: str,
        documentai_client: documentai.DocumentProcessorServiceClient
    ) -> List[Dict[str, Any]]:
        """
        Traite une liste de chunks en parallèle avec cache
        
        :param chunks: Liste des chunks à traiter
        :param processor_name: Nom du processeur DocumentAI
        :param documentai_client: Client DocumentAI
        :return: Liste des résultats
        """
        async def process_single_chunk(chunk: bytes, index: int) -> Dict[str, Any]:
            async with self.semaphore:
                # Vérifier le cache
                cache_key = f"{self.cache._get_hash(chunk)}"
                if cached_result := await self.cache.get(cache_key):
                    logger.info(f"Using cached result for chunk {index}")
                    return cached_result

                # Traiter le chunk
                try:
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

                    # Mettre en cache
                    await self.cache.set(cache_key, processed_result)
                    
                    logger.info(f"Successfully processed chunk {index}")
                    return processed_result

                except Exception as e:
                    logger.error(f"Error processing chunk {index}: {str(e)}")
                    return None

        # Créer les tâches de traitement
        tasks = [
            process_single_chunk(chunk, i)
            for i, chunk in enumerate(chunks)
        ]

        # Exécuter les tâches en parallèle
        results = await asyncio.gather(*tasks)
        
        # Filtrer les résultats None (erreurs)
        return [r for r in results if r is not None]

class OCRService:
    def __init__(
        self,
        max_chunk_pages: int = 10,
        max_concurrent_chunks: int = 3,
        processing_timeout: int = 1800
    ):
        """
        Service OCR avec traitement parallèle et cache
        
        :param max_chunk_pages: Nombre maximum de pages par chunk
        :param max_concurrent_chunks: Nombre maximum de chunks traités en parallèle
        :param processing_timeout: Timeout global en secondes
        """
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

    def _validate_and_setup_env_variables(self) -> None:
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_CLOUD_LOCATION',
            'DOCUMENT_AI_PROCESSOR_ID'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    def _initialize_clients(self) -> None:
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
            logger.error(f"Failed to initialize Google Cloud clients: {str(e)}")
            raise

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Traite un document avec parallélisation et cache
        
        :param content: Contenu du document
        :param filename: Nom du fichier
        :return: Résultat du traitement
        """
        start_time = time.time()
        chunks = []
        
        try:
            logger.info(f"Starting processing of {filename}")
            
            # Collecter tous les chunks
            async for chunk in self.pdf_splitter.split_pdf(content):
                chunks.append(chunk)
            
            logger.info(f"Split document into {len(chunks)} chunks")
            
            # Traitement parallèle des chunks
            results = await self.chunk_processor.process_chunks(
                chunks,
                self.processor_name,
                self.documentai_client
            )
            
            logger.info(f"Successfully processed {len(results)} chunks")
            
            # Traitement Vision AI (en parallèle avec les chunks)
            vision_task = asyncio.create_task(
                self.vision_service.analyze_document(content, filename)
            )
            
            # Fusionner les résultats
            merged_result = {
                'text': '',
                'pages': [],
                'metadata': {
                    'filename': filename,
                    'processing_time': time.time() - start_time,
                    'chunks_processed': len(results),
                    'total_chunks': len(chunks)
                }
            }
            
            # Fusionner les textes et pages
            for result in results:
                merged_result['text'] += result['text']
                merged_result['pages'].extend(result['pages'])
            
            # Ajouter les résultats Vision AI
            vision_result = await vision_task
            merged_result.update({
                'visual_elements': vision_result.get('visual_elements', {}),
                'classifications': vision_result.get('classifications', {})
            })
            
            # Sauvegarder les résultats
            save_paths = await self.document_saver.save_final_results(
                merged_result,
                filename
            )
            
            logger.info(
                f"Document processing completed in {time.time() - start_time:.1f} seconds. "
                f"Processed {len(results)}/{len(chunks)} chunks"
            )
            
            return {
                'status': 'success',
                'metadata': merged_result['metadata'],
                'file_paths': save_paths
            }

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise

        finally:
            # Nettoyage
            for chunk in chunks:
                del chunk
            gc.collect()
