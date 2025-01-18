from PyPDF2 import PdfReader, PdfWriter
from typing import AsyncGenerator
import io
import gc
import os
import asyncio
from loguru import logger
import tempfile
import psutil

class PDFSplitter:
    def __init__(self, max_pages_per_chunk: int = 10):  # Réduit de 15 à 10 pages
        self.max_pages_per_chunk = max_pages_per_chunk
        self.temp_dir = tempfile.mkdtemp(prefix='pdf_processing_')
        logger.info(f"Initialized PDFSplitter with temp directory: {self.temp_dir}")

    def _cleanup(self) -> None:
        """Nettoie les fichiers temporaires"""
        import shutil
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {str(e)}")

    def __del__(self):
        """S'assure que le nettoyage est effectué à la destruction de l'objet"""
        self._cleanup()

    async def log_memory_stats(self, context: str = ""):
        """Log detailed memory statistics"""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        sys_mem = psutil.virtual_memory()
        
        logger.info(f"""
            Memory Stats {context}:
            RSS: {mem_info.rss / 1024 / 1024:.2f} MB
            VMS: {mem_info.vms / 1024 / 1024:.2f} MB
            Shared: {mem_info.shared / 1024 / 1024:.2f} MB
            System Memory Used: {sys_mem.percent}%
            Available Memory: {sys_mem.available / 1024 / 1024:.2f} MB
        """)

    async def split_pdf(self, pdf_content: bytes) -> AsyncGenerator[bytes, None]:
        """
        Split a PDF into chunks using async generator for memory efficiency
        
        :param pdf_content: PDF file content in bytes
        :yields: PDF chunks as bytes
        """
        temp_input = os.path.join(self.temp_dir, 'input.pdf')
        await self.log_memory_stats("Before PDF processing")
        
        try:
            # Écrire le PDF d'entrée dans un fichier temporaire
            logger.info("Writing input PDF to temporary file")
            with open(temp_input, 'wb') as f:
                f.write(pdf_content)

            # Libérer la mémoire du contenu original
            del pdf_content
            gc.collect()
            await asyncio.sleep(0.1)  # Permettre la libération mémoire

            # Lire le PDF à partir du fichier temporaire
            reader = PdfReader(temp_input)
            total_pages = len(reader.pages)
            logger.info(f"Starting PDF split: {total_pages} pages total")

            for start_page in range(0, total_pages, self.max_pages_per_chunk):
                end_page = min(start_page + self.max_pages_per_chunk, total_pages)
                logger.info(f"Processing pages {start_page + 1} to {end_page}")
                
                try:
                    # Créer un writer temporaire pour ce chunk
                    writer = PdfWriter()
                    
                    # Ajouter les pages au chunk actuel
                    for page_num in range(start_page, end_page):
                        writer.add_page(reader.pages[page_num])
                    
                    # Utiliser un fichier temporaire pour le chunk
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=self.temp_dir) as temp_chunk:
                        writer.write(temp_chunk)
                        temp_chunk_path = temp_chunk.name
                    
                    # Lire le chunk et le yield
                    with open(temp_chunk_path, 'rb') as chunk_file:
                        chunk_content = chunk_file.read()
                        chunk_size_mb = len(chunk_content) / (1024 * 1024)
                        logger.info(f"Chunk {start_page // self.max_pages_per_chunk} processed. Size: {chunk_size_mb:.2f}MB")
                        
                        yield chunk_content
                    
                    # Nettoyage immédiat après avoir yield le chunk
                    os.unlink(temp_chunk_path)
                    del writer, chunk_content
                    gc.collect()
                    
                    # Log des stats mémoire tous les 3 chunks
                    if (start_page // self.max_pages_per_chunk) % 3 == 0:
                        await self.log_memory_stats(f"After processing chunk {start_page // self.max_pages_per_chunk}")
                    
                    # Pause courte pour permettre la libération mémoire
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error(f"Error processing chunk starting at page {start_page}: {str(e)}")
                    raise

            logger.info(f"PDF split complete: {(total_pages + self.max_pages_per_chunk - 1) // self.max_pages_per_chunk} chunks created")
            await self.log_memory_stats("After PDF processing completed")

        except Exception as e:
            logger.error(f"Error splitting PDF: {str(e)}")
            raise
        
        finally:
            # Nettoyage final
            try:
                if os.path.exists(temp_input):
                    os.remove(temp_input)
                    logger.info("Cleaned up input temporary file")
            except Exception as e:
                logger.error(f"Error cleaning up input file: {str(e)}")
            
            gc.collect()
