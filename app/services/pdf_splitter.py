from PyPDF2 import PdfReader, PdfWriter
from typing import List, Generator
import io
import gc
import os
from loguru import logger
import tempfile

class PDFSplitter:
    def __init__(self, max_pages_per_chunk: int = 15, max_chunk_size: int = 10 * 1024 * 1024):
        self.max_pages_per_chunk = max_pages_per_chunk
        self.max_chunk_size = max_chunk_size
        self.temp_dir = tempfile.mkdtemp(prefix='pdf_processing_')

    def _cleanup(self) -> None:
        """Nettoie les fichiers temporaires"""
        import shutil
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {str(e)}")

    def __del__(self):
        """S'assure que le nettoyage est effectué à la destruction de l'objet"""
        self._cleanup()

    def split_pdf(self, pdf_content: bytes) -> List[bytes]:
        """Split a PDF into chunks of maximum size using temporary files"""
        chunks = []
        temp_input = os.path.join(self.temp_dir, 'input.pdf')
        
        try:
            # Écrire le PDF d'entrée dans un fichier temporaire
            with open(temp_input, 'wb') as f:
                f.write(pdf_content)

            # Lire le PDF à partir du fichier temporaire
            reader = PdfReader(temp_input)
            total_pages = len(reader.pages)
            logger.info(f"Starting PDF split: {total_pages} pages total")

            for start_page in range(0, total_pages, self.max_pages_per_chunk):
                # Créer un nouveau writer pour chaque chunk
                writer = PdfWriter()
                end_page = min(start_page + self.max_pages_per_chunk, total_pages)
                
                logger.info(f"Processing pages {start_page + 1} to {end_page}")
                
                # Ajouter les pages au chunk actuel
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # Écrire le chunk dans un fichier temporaire
                temp_output = os.path.join(self.temp_dir, f'chunk_{len(chunks)}.pdf')
                with open(temp_output, 'wb') as output_file:
                    writer.write(output_file)
                
                # Lire le contenu du chunk et l'ajouter à la liste
                with open(temp_output, 'rb') as chunk_file:
                    chunk_content = chunk_file.read()
                
                chunk_size_mb = len(chunk_content) / (1024 * 1024)
                logger.info(f"Chunk {len(chunks)} processed. Size: {chunk_size_mb:.2f}MB")
                
                chunks.append(chunk_content)
                
                # Nettoyage explicite après chaque chunk
                del writer
                os.remove(temp_output)
                gc.collect()

            logger.info(f"PDF split complete: {len(chunks)} chunks created")
            return chunks

        except Exception as e:
            logger.error(f"Error splitting PDF: {str(e)}")
            raise
        
        finally:
            # Nettoyage
            try:
                os.remove(temp_input)
            except:
                pass
            gc.collect()

    def get_memory_usage(self) -> dict:
        """Get current memory usage"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return {
                "rss": f"{memory_info.rss / (1024 * 1024):.2f} MB",
                "vms": f"{memory_info.vms / (1024 * 1024):.2f} MB",
                "percent": f"{process.memory_percent():.1f}%"
            }
        except Exception as e:
            logger.error(f"Error getting memory usage: {str(e)}")
            return {"error": "Unable to get memory info"}
