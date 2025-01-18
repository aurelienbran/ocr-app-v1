import os
import sys
import gc
import platform
import tracemalloc
import logging
from typing import Optional, Dict, Any
import psutil
import asyncio
import time
import traceback

class MemoryDiagnostic:
    def __init__(self, log_file: Optional[str] = 'memory_diagnostic.log'):
        """
        Initialise un diagnostic complet de mémoire
        
        :param log_file: Chemin du fichier de log, None pour désactiver
        """
        # Configuration du logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file) if log_file else logging.StreamHandler(),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Démarrage du tracking mémoire
        tracemalloc.start()

    def log_system_info(self):
        """Log informations système détaillées"""
        self.logger.info("--- Diagnostic Système ---")
        self.logger.info(f"Python Version: {sys.version}")
        self.logger.info(f"Platform: {platform.platform()}")
        self.logger.info(f"Architecture: {platform.architecture()}")
        
        # Informations mémoire
        mem = psutil.virtual_memory()
        self.logger.info(f"Total Memory: {mem.total / (1024*1024):.2f} MB")
        self.logger.info(f"Available Memory: {mem.available / (1024*1024):.2f} MB")
        self.logger.info(f"Memory Usage: {mem.percent}%")
        
        # Processus Python
        process = psutil.Process()
        self.logger.info(f"Python Process Memory: {process.memory_info().rss / (1024*1024):.2f} MB")

    def track_memory_usage(self, func):
        """
        Décorateur pour tracker l'utilisation mémoire d'une fonction
        
        :param func: Fonction à tracker
        :return: Fonction wrappée
        """
        def wrapper(*args, **kwargs):
            # Snapshot initial
            snapshot1 = tracemalloc.take_snapshot()
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss

            try:
                result = func(*args, **kwargs)
                
                # Snapshot final
                snapshot2 = tracemalloc.take_snapshot()
                
                # Calcul des différences
                top_stats = snapshot2.compare_to(snapshot1, 'lineno')
                
                self.logger.info("--- Memory Tracking Results ---")
                self.logger.info(f"Function: {func.__name__}")
                self.logger.info(f"Execution Time: {time.time() - start_time:.2f} seconds")
                
                # Top 10 memory allocations
                for stat in top_stats[:10]:
                    self.logger.info(str(stat))
                
                # Mémoire utilisée
                end_memory = psutil.Process().memory_info().rss
                memory_diff = end_memory - start_memory
                self.logger.info(f"Memory Change: {memory_diff / (1024*1024):.2f} MB")
                
                # Force garbage collection
                gc.collect()
                
                return result
            
            except Exception as e:
                self.logger.error(f"Error in {func.__name__}: {e}")
                self.logger.error(traceback.format_exc())
                raise
        return wrapper

    async def async_memory_test(self, document_path: str):
        """
        Test de traitement de document avec tracking mémoire
        
        :param document_path: Chemin du document à tester
        """
        self.logger.info(f"--- Début du test de traitement: {document_path} ---")
        
        # Vérification du fichier
        if not os.path.exists(document_path):
            self.logger.error(f"Fichier non trouvé: {document_path}")
            return
        
        file_size = os.path.getsize(document_path) / (1024 * 1024)
        self.logger.info(f"Taille du fichier: {file_size:.2f} MB")
        
        # Test de lecture et traitement
        @self.track_memory_usage
        def process_document(path):
            with open(path, 'rb') as f:
                content = f.read()
            
            # Simulation du traitement
            # Remplacez cette partie par votre logique de traitement réelle
            processed_chunks = []
            chunk_size = 1024 * 1024  # 1 MB chunks
            
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i+chunk_size]
                processed_chunks.append(len(chunk))
                
                # Simulation de traitement
                time.sleep(0.1)
            
            return processed_chunks

        try:
            result = process_document(document_path)
            self.logger.info(f"Nombre de chunks traités: {len(result)}")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement: {e}")

    def run_full_diagnostic(self, document_path: Optional[str] = None):
        """
        Lance un diagnostic complet
        
        :param document_path: Chemin optionnel d'un document à tester
        """
        self.log_system_info()
        
        if document_path:
            asyncio.run(self.async_memory_test(document_path))

async def main():
    diagnostic = MemoryDiagnostic()
    
    # Chemin du document à tester (à remplacer)
    test_document = sys.argv[1] if len(sys.argv) > 1 else None
    
    diagnostic.run_full_diagnostic(test_document)

if __name__ == "__main__":
    asyncio.run(main())
