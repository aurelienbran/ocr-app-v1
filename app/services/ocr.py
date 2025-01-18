from google.cloud import documentai, vision_v1
from google.cloud.documentai import Document
from loguru import logger
import os
import asyncio
import time
import gc
import io
import tempfile
import psutil
from typing import Dict, Any, List, Optional
from PyPDF2 import PdfReader, PdfWriter

from app.services.vision_service import VisionService
from app.services.document_saver import DocumentSaver

class MemoryMonitor:
    def __init__(self, max_memory_percent: float = 0.8):
        """
        Surveille l'utilisation mémoire du système
        
        :param max_memory_percent: Pourcentage maximal de mémoire avant déclenchement
        """
        self.max_memory_percent = max_memory_percent

    def is_memory_safe(self) -> bool:
        """
        Vérifie si la mémoire système est dans les limites acceptables
        
        :return: Booléen indiquant si la mémoire est dans les limites
        """
        mem = psutil.virtual_memory()
        current_usage = mem.percent
        is_safe = current_usage < (self.max_memory_percent * 100)
        
        if not is_safe:
            logger.warning(f"Memory pressure detected: {current_usage}% used")
        
        return is_safe

class OCRService:
    def __init__(
        self, 
        max_chunk_size_mb: int = 10, 
        max_text_size: int = 500_000, 
        max_memory_percent: float = 0.8,
        chunk_pages: int = 15,
        processing_timeout: int = 600,
        max_retries: int = 3
    ):
        """
        Service de traitement OCR avec gestion mémoire avancée
        
        :param max_chunk_size_mb: Taille maximale des chunks PDF
        :param max_text_size: Taille maximale du texte fusionné
        :param max_memory_percent: Seuil maximal d'utilisation mémoire
        :param chunk_pages: Nombre de pages par chunk
        :param processing_timeout: Timeout pour le traitement d'un chunk
        :param max_retries: Nombre maximal de tentatives par chunk
        """
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        
        self.document_saver = DocumentSaver()
        self.vision_service = VisionService()
        
        self.max_chunk_size = max_chunk_size_mb * 1024 * 1024
        self.max_text_size = max_text_size
        self.chunk_pages = chunk_pages
        self.processing_timeout = processing_timeout
        self.max_retries = max_retries
        
        self.memory_monitor = MemoryMonitor(max_memory_percent)
        
        self.temp_dir = tempfile.mkdtemp(prefix='ocr_processing_')

    def _validate_and_setup_env_variables(self):
        """Validation des variables d'environnement requises"""
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_CLOUD_LOCATION',
            'DOCUMENT_AI_PROCESSOR_ID'
        ]
        for var in required_vars:
            if not os.getenv(var):
                raise ValueError(f"Missing required environment variable: {var}")

    def _initialize_clients(self):
        """Initialisation des clients Google Cloud"""
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
        """Nettoyage des fichiers temporaires"""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def __del__(self):
        """Assure le nettoyage à la destruction"""
        self._cleanup()

    def _memory_efficient_chunk_generator(self, pdf_content: bytes):
        """
        Générateur de chunks PDF avec gestion dynamique
        
        :param pdf_content: Contenu du PDF à traiter
        :yield: Chunks du PDF
        """
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)
        
        for start in range(0, total_pages, self.chunk_pages):
            writer = PdfWriter()
            end = min(start + self.chunk_pages, total_pages)
            
            for page_num in range(start, end):
                writer.add_page(reader.pages[page_num])
            
            chunk_buffer = io.BytesIO()
            writer.write(chunk_buffer)
            chunk_buffer.seek(0)
            
            yield chunk_buffer.read()

    async def _process_chunk_with_timeout(self, chunk_path: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """
        Traitement d'un chunk avec timeout et retry
        
        :param chunk_path: Chemin du fichier chunk
        :param chunk_index: Index du chunk
        :return: Résultat du traitement ou None
        """
        for attempt in range(self.max_retries):
            try:
                result = await asyncio.wait_for(
                    self._process_with_documentai(chunk_path),
                    timeout=self.processing_timeout
                )
                return result
            
            except asyncio.TimeoutError:
                logger.warning(
                    f"Chunk {chunk_index} processing timed out "
                    f"(Attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    return None
            
            except Exception as e:
                logger.error(f"Chunk {chunk_index} processing error: {e}")
                if attempt == self.max_retries - 1:
                    return None
                
                # Délai entre les tentatives
                await asyncio.sleep(2 ** attempt)

    async def _process_with_documentai(self, chunk_path: str) -> Dict[str, Any]:
        """
        Traitement d'un chunk avec Document AI
        
        :param chunk_path: Chemin du chunk PDF
        :return: Résultat du traitement
        """
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

            result = await asyncio.to_thread(
                self.documentai_client.process_document,
                request=request
            )

            return self._process_docai_response(result.document)

        except Exception as e:
            logger.error(f"Document AI processing error: {e}")
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
            } for page in document.pages]
        }

    def _safe_merge_results(self, results: List[Dict]) -> Dict:
        """
        Fusion sécurisée des résultats avec contrôles stricts
        
        :param results: Liste des résultats de chunks
        :return: Résultat fusionné
        """
        merged = {
            'text': '',
            'pages': [],
            'metadata': {
                'total_chunks': len(results),
                'processors': set()
            }
        }

        for result in results:
            text_chunk = result.get('text', '')[:self.max_text_size - len(merged['text'])]
            merged['text'] += text_chunk
            merged['pages'].extend(result.get('pages', []))
            merged['metadata']['processors'].update(
                result.get('metadata', {}).get('processors', [])
            )

            if len(merged['text']) >= self.max_text_size:
                break

        return merged

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Processus principal de traitement du document
        
        :param content: Contenu du document
        :param filename: Nom du fichier
        :return: Résultat du traitement
        """
        start_time = time.time()
        try:
            logger.info(
                f"Starting processing for {filename}, "
                f"Initial memory usage: {psutil.virtual_memory().percent}%"
            )

            # Liste pour résultats avec limitation
            processed_results = []
            chunks_processed = 0
            
            async for chunk in self._memory_efficient_chunk_generator(content):
                # Vérification de la mémoire avant chaque traitement
                if not self.memory_monitor.is_memory_safe():
                    logger.warning("Memory threshold reached. Pausing processing.")
                    await asyncio.sleep(5)  # Pause pour libération
                
                # Sauvegarde temporaire du chunk
                chunk_path = os.path.join(self.temp_dir, f'chunk_{chunks_processed}.pdf')
                with open(chunk_path, 'wb') as f:
                    f.write(chunk)

                try:
                    # Traitement du chunk
                    chunk_result = await self._process_chunk_with_timeout(chunk_path, chunks_processed + 1)
                    if chunk_result:
                        processed_results.append(chunk_result)
                    
                    chunks_processed += 1
                
                    # Nettoyage du chunk
                    os.remove(chunk_path)

                except Exception as e:
                    logger.error(f"Chunk processing error: {e}")
                
                # Libération explicite
                del chunk
                gc.collect()

            # Traitement Vision AI
            vision_result = await self.vision_service.analyze_document(content, filename)

            # Fusion des résultats
            final_result = self._safe_merge_results(processed_results)
            
            # Compléter avec les résultats Vision AI
            final_result.update({
                'visual_elements': vision_result.get('visual_elements', {}),
                'classifications': vision_result.get('classifications', {})
            })

            processing_time = time.time() - start_time
            logger.info(
                f"Processing completed in {processing_time:.2f} seconds, "
                f"Total chunks processed: {chunks_processed}, "
                f"Final memory usage: {psutil.virtual_memory().percent}%"
            )

            # Sauvegarde des résultats
            await self.document_saver.save_results(final_result, filename)

            return final_result

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise

        finally:
            self._cleanup()
            gc.collect()
