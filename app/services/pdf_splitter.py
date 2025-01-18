from PyPDF2 import PdfReader, PdfWriter
from typing import List
import io
import gc
import os
from loguru import logger

class PDFSplitter:
    def __init__(self, max_pages_per_chunk: int = 15, max_chunk_size: int = 10 * 1024 * 1024):  # 10MB par défaut
        self.max_pages_per_chunk = max_pages_per_chunk
        self.max_chunk_size = max_chunk_size

    def split_pdf(self, pdf_content: bytes) -> List[bytes]:
        """Split a PDF into chunks of maximum size"""
        try:
            # Créer un fichier temporaire pour le PDF source
            temp_file = io.BytesIO(pdf_content)
            reader = PdfReader(temp_file)
            total_pages = len(reader.pages)
            
            logger.info(f"Starting PDF split: {total_pages} pages total")
            
            chunks = []
            for start_page in range(0, total_pages, self.max_pages_per_chunk):
                # Créer un nouveau writer pour chaque chunk
                writer = PdfWriter()
                end_page = min(start_page + self.max_pages_per_chunk, total_pages)
                
                logger.info(f"Processing pages {start_page + 1} to {end_page}")
                
                # Ajouter les pages au chunk actuel
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # Écrire le chunk dans un buffer
                output = io.BytesIO()
                writer.write(output)
                chunk_content = output.getvalue()
                
                # Vérifier la taille du chunk
                chunk_size_mb = len(chunk_content) / (1024 * 1024)
                if len(chunk_content) > self.max_chunk_size:
                    logger.warning(f"Chunk size ({chunk_size_mb:.2f}MB) exceeds maximum ({self.max_chunk_size / (1024 * 1024)}MB)")
                
                chunks.append(chunk_content)
                
                # Nettoyage manuel après chaque chunk
                output.close()
                del writer
                gc.collect()
                
                logger.info(f"Chunk {len(chunks)} processed. Size: {chunk_size_mb:.2f}MB")
            
            # Nettoyage final
            temp_file.close()
            del reader
            gc.collect()
            
            logger.info(f"PDF split complete: {len(chunks)} chunks created")
            return chunks
            
        except Exception as e:
            logger.error(f"Error splitting PDF: {str(e)}")
            raise
        finally:
            # S'assurer que tous les fichiers temporaires sont fermés
            try:
                if 'temp_file' in locals():
                    temp_file.close()
                if 'output' in locals():
                    output.close()
            except:
                pass

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
