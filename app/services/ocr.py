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
from typing import Dict, Any, List, Optional, AsyncGenerator
from PyPDF2 import PdfReader, PdfWriter

from app.services.vision_service import VisionService
from app.services.document_saver import DocumentSaver

class MemoryMonitor:
    def __init__(self, max_memory_percent: float = 0.7):
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
        max_chunk_pages: int = 10,  # Réduction du nombre de pages par chunk
        max_text_size: int = 250_000,  # Réduction de la taille de texte
        max_memory_percent: float = 0.7,  # Seuil mémoire plus bas
        processing_timeout: int = 300,  # Réduction du timeout
        memory_check_interval: int = 2  # Vérification mémoire plus fréquente
    ):
        """
        Service de traitement OCR avec gestion mémoire avancée
        
        :param max_chunk_pages: Nombre maximal de pages par chunk
        :param max_text_size: Taille maximale du texte fusionné
        :param max_memory_percent: Seuil maximal d'utilisation mémoire
        :param processing_timeout: Timeout pour le traitement d'un chunk
        :param memory_check_interval: Intervalle de vérification mémoire
        """
        self._validate_and_setup_env_variables()
        self._initialize_clients()
        
        self.document_saver = DocumentSaver()
        self.vision_service = VisionService()
        
        self.max_chunk_pages = max_chunk_pages
        self.max_text_size = max_text_size
        self.processing_timeout = processing_timeout
        self.memory_check_interval = memory_check_interval
        
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

    async def _memory_efficient_chunk_generator(self, pdf_content: bytes) -> AsyncGenerator[bytes, None]:
        """
        Générateur de chunks avec contrôle mémoire strict
        """
        def create_chunk(reader, start, end):
            writer = PdfWriter()
            for page_num in range(start, end):
                writer.add_page(reader.pages[page_num])
            
            chunk_buffer = io.BytesIO()
            writer.write(chunk_buffer)
            chunk_buffer.seek(0)
            return chunk_buffer.read()

        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)
        
        for start in range(0, total_pages, self.max_chunk_pages):
            # Vérification mémoire avant chaque chunk
            if not self.memory_monitor.is_memory_safe():
                logger.warning("High memory usage. Pausing chunk generation.")
                await asyncio.sleep(self.memory_check_interval)
            
            end = min(start + self.max_chunk_pages, total_pages)
            chunk = await asyncio.to_thread(create_chunk, reader, start, end)
            
            # Libération explicite
            gc.collect()
            
            yield chunk

    async def _process_chunk_with_timeout(self, chunk_path: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """
        Traitement d'un chunk avec timeout et retry
        
        :param chunk_path: Chemin du fichier chunk
        :param chunk_index: Index du chunk
        :return: Résultat du traitement ou None
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    self._process_with_documentai(chunk_path),
                    timeout=self.processing_timeout
                )
                return result
            
            except asyncio.TimeoutError:
                logger.warning(
                    f"Chunk {chunk_index} processing timed out "
                    f"(Attempt {attempt + 1}/{max_retries})"
                )
                if attempt == max_retries - 1:
                    return None
            
            except Exception as e:
                logger.error(f"Chunk {chunk_index} processing error: {e}")
                if attempt == max_retries - 1:
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
        Processus de traitement avec contrôle mémoire renforcé
        
        :param content: Contenu du document
        :param filename: Nom du fichier
        :return: Résultat du traitement
        """
        start_time = time.time()
        processed_results = []
        chunks_processed = 0

        try:
            logger.info(
                f"Starting processing for {filename}, "
                f"Initial memory usage: {psutil.virtual_memory().percent}%"
            )

            async for chunk in self._memory_efficient_chunk_generator(content):
                # Contrôle mémoire strict
                if not self.memory_monitor.is_memory_safe():
                    logger.warning("Memory threshold exceeded. Stopping processing.")
                    break

                # Traitement du chunk avec gestion temporaire
                with tempfile.NamedTemporaryFile(delete=True, suffix='.pdf') as temp_chunk:
                    temp_chunk.write(chunk)
                    temp_chunk.flush()

                    try:
                        chunk_result = await self._process_chunk_with_timeout(
                            temp_chunk.name, 
                            chunks_processed + 1
                        )
                        
                        if chunk_result:
                            processed_results.append(chunk_result)
                        
                        chunks_processed += 1
                    
                    except Exception as e:
                        logger.error(f"Chunk processing error: {e}")
                
                # Libération explicite
                del chunk
                gc.collect()

                # Pause si mémoire haute
                if not self.memory_monitor.is_memory_safe():
                    await asyncio.sleep(self.memory_check_interval)

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
