from google.cloud import documentai
from google.cloud.documentai import Document
from loguru import logger
import os
import asyncio
import time
import gc
import tempfile
import psutil
from typing import Dict, Any, Optional
from datetime import datetime

from app.services.vision_service import VisionService
from app.services.pdf_splitter import PDFSplitter
from app.services.document_saver import DocumentSaver

class MemoryMonitor:
    def __init__(self, max_memory_percent: float = 0.7, check_interval: int = 2):
        self.max_memory_percent = max_memory_percent
        self.check_interval = check_interval
        logger.info(f"Memory monitor initialized: max {max_memory_percent*100}% threshold")

    async def check_memory(self) -> bool:
        """
        Vérifie l'utilisation mémoire et attend si nécessaire
        :return: True si la mémoire est disponible après attente
        """
        max_retries = 3
        for retry in range(max_retries):
            mem = psutil.virtual_memory()
            if mem.percent < (self.max_memory_percent * 100):
                return True
            
            logger.warning(f"High memory usage detected: {mem.percent}% (retry {retry + 1}/{max_retries})")
            await asyncio.sleep(self.check_interval * (retry + 1))
        
        return False

    async def log_memory_stats(self, context: str = ""):
        """Log detailed memory statistics"""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        sys_mem = psutil.virtual_memory()
        
        logger.info(f"""
            Memory Stats {context}:
            Process RSS: {mem_info.rss / 1024 / 1024:.2f} MB
            Process VMS: {mem_info.vms / 1024 / 1024:.2f} MB
            System Memory Used: {sys_mem.percent}%
            Available System Memory: {sys_mem.available / 1024 / 1024:.2f} MB
        """)

class OCRService:
    def __init__(
        self,
        max_chunk_pages: int = 10,
        max_retries: int = 3,
        processing_timeout: int = 300,
        max_memory_percent: float = 0.7
    ):
        """
        Initialise le service OCR avec une gestion optimisée de la mémoire
        
        :param max_chunk_pages: Nombre maximum de pages par chunk
        :param max_retries: Nombre maximum de tentatives pour chaque opération
        :param processing_timeout: Timeout en secondes pour le traitement d'un chunk
        :param max_memory_percent: Seuil maximum d'utilisation mémoire (0.0-1.0)
        """
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        
        self.max_chunk_pages = max_chunk_pages
        self.max_retries = max_retries
        self.processing_timeout = processing_timeout
        
        self.pdf_splitter = PDFSplitter(max_pages_per_chunk=max_chunk_pages)
        self.vision_service = VisionService()
        self.document_saver = DocumentSaver()
        self.memory_monitor = MemoryMonitor(max_memory_percent=max_memory_percent)
        
        self.temp_dir = tempfile.mkdtemp(prefix='ocr_processing_')
        logger.info(f"OCR Service initialized with configuration: max_chunk_pages={max_chunk_pages}, max_retries={max_retries}")

    def _validate_and_setup_env_variables(self) -> None:
        """Validation des variables d'environnement requises"""
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_CLOUD_LOCATION',
            'DOCUMENT_AI_PROCESSOR_ID'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    def _initialize_clients(self) -> None:
        """Initialisation des clients Google Cloud avec gestion des erreurs"""
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

    def _cleanup(self) -> None:
        """Nettoyage des ressources temporaires"""
        try:
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def __del__(self):
        """Destructeur avec nettoyage"""
        self._cleanup()

    async def _process_chunk_with_retry(
        self,
        chunk_path: str,
        chunk_index: int,
        temp_results_file: str
    ) -> bool:
        """
        Traite un chunk avec retry et sauvegarde streaming
        
        :param chunk_path: Chemin du fichier chunk
        :param chunk_index: Index du chunk
        :param temp_results_file: Fichier temporaire pour les résultats
        :return: True si le traitement a réussi
        """
        for attempt in range(self.max_retries):
            try:
                # Vérification mémoire avant traitement
                if not await self.memory_monitor.check_memory():
                    logger.error(f"Memory threshold exceeded for chunk {chunk_index}")
                    return False

                # Traitement avec timeout
                result = await asyncio.wait_for(
                    self._process_with_documentai(chunk_path),
                    timeout=self.processing_timeout
                )

                # Sauvegarde immédiate du résultat
                await self.document_saver.append_result(temp_results_file, result)
                
                logger.info(f"Successfully processed chunk {chunk_index} (Attempt {attempt + 1})")
                return True

            except asyncio.TimeoutError:
                logger.warning(f"Timeout processing chunk {chunk_index} (Attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_index} (Attempt {attempt + 1}): {str(e)}")

            # Pause entre les tentatives
            await asyncio.sleep(2 ** attempt)
            gc.collect()

        return False

    async def _process_with_documentai(self, file_path: str) -> Dict[str, Any]:
        """
        Traite un fichier avec Document AI
        
        :param file_path: Chemin du fichier à traiter
        :return: Résultat du traitement
        """
        try:
            with open(file_path, 'rb') as f:
                content = f.read()

            # Création de la requête Document AI
            raw_document = documentai.RawDocument(
                content=content,
                mime_type="application/pdf"
            )
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document
            )

            # Traitement avec Document AI
            result = await asyncio.to_thread(
                self.documentai_client.process_document,
                request=request
            )

            return self._process_docai_response(result.document)

        except Exception as e:
            logger.error(f"Document AI processing error: {str(e)}")
            raise

    def _process_docai_response(self, document: Document) -> Dict[str, Any]:
        """
        Traitement de la réponse de Document AI
        
        :param document: Document traité
        :return: Résultat structuré
        """
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
            } for page in document.pages],
            'timestamp': datetime.now().isoformat()
        }

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Processus principal de traitement avec gestion optimisée de la mémoire
        
        :param content: Contenu du document
        :param filename: Nom du fichier
        :return: Résultat du traitement
        """
        start_time = time.time()
        chunks_processed = 0
        chunks_failed = 0
        
        # Création du fichier temporaire pour les résultats
        temp_results_file = os.path.join(self.temp_dir, f"{filename}_results.jsonl")
        
        try:
            await self.memory_monitor.log_memory_stats("Start of processing")

            # Traitement des chunks en streaming
            async for chunk in self.pdf_splitter.split_pdf(content):
                chunks_processed += 1
                
                # Sauvegarde temporaire du chunk
                chunk_path = os.path.join(self.temp_dir, f"chunk_{chunks_processed}.pdf")
                with open(chunk_path, 'wb') as f:
                    f.write(chunk)

                # Traitement du chunk
                success = await self._process_chunk_with_retry(
                    chunk_path,
                    chunks_processed,
                    temp_results_file
                )

                if not success:
                    chunks_failed += 1
                
                # Nettoyage après chaque chunk
                try:
                    os.remove(chunk_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temporary chunk file: {str(e)}")

                # Libération mémoire
                del chunk
                gc.collect()
                
                # Log périodique des stats mémoire
                if chunks_processed % 5 == 0:
                    await self.memory_monitor.log_memory_stats(f"After chunk {chunks_processed}")

            # Traitement Vision AI avec contrôle mémoire
            if await self.memory_monitor.check_memory():
                vision_result = await self.vision_service.analyze_document(content, filename)
            else:
                logger.warning("Skipping Vision AI due to memory constraints")
                vision_result = {}

            # Finalisation et sauvegarde des résultats
            metadata = {
                'filename': filename,
                'processing_time': time.time() - start_time,
                'chunks_processed': chunks_processed,
                'chunks_failed': chunks_failed,
                'vision_ai_processed': bool(vision_result)
            }

            final_paths = await self.document_saver.save_final_results(
                temp_results_file,
                filename,
                metadata
            )

            await self.memory_monitor.log_memory_stats("End of processing")

            return {
                'status': 'success',
                'metadata': metadata,
                'file_paths': final_paths
            }

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise

        finally:
            self._cleanup()
            gc.collect()
