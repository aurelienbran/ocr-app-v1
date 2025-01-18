import json
import os
import aiofiles
from typing import Dict, Any
from loguru import logger
import tempfile
from datetime import datetime

class DocumentSaver:
    def __init__(self, base_path: str = "documents"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        self.temp_dir = tempfile.mkdtemp(prefix='doc_saver_')
        logger.info(f"Initialized DocumentSaver with base path: {base_path}")

    def _cleanup(self):
        """Nettoie les fichiers temporaires"""
        try:
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temporary files: {str(e)}")

    def __del__(self):
        self._cleanup()

    def _get_timestamp_path(self) -> str:
        """Crée un chemin basé sur le timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.base_path, timestamp)
        os.makedirs(path, exist_ok=True)
        return path

    async def append_result(self, temp_file: str, result: Dict[str, Any]) -> None:
        """
        Ajoute un résultat au fichier temporaire de manière asynchrone
        
        :param temp_file: Chemin du fichier temporaire
        :param result: Résultat à ajouter
        """
        try:
            async with aiofiles.open(temp_file, mode='a') as f:
                await f.write(json.dumps(result) + '\n')
        except Exception as e:
            logger.error(f"Error appending result: {str(e)}")
            raise

    async def save_final_results(self, temp_file: str, filename: str, metadata: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Sauvegarde les résultats finals à partir du fichier temporaire
        
        :param temp_file: Chemin du fichier temporaire
        :param filename: Nom du fichier original
        :param metadata: Métadonnées additionnelles
        :return: Chemins des fichiers sauvegardés
        """
        save_path = self._get_timestamp_path()
        base_name = os.path.splitext(os.path.basename(filename))[0]
        
        result_paths = {
            'json': os.path.join(save_path, f"{base_name}_results.json"),
            'text': os.path.join(save_path, f"{base_name}_text.txt"),
            'summary': os.path.join(save_path, f"{base_name}_summary.txt")
        }

        try:
            # Fusion des résultats en streaming
            merged_results = {
                'text': '',
                'pages': [],
                'metadata': metadata or {},
                'chunks_processed': 0
            }

            async with aiofiles.open(temp_file, mode='r') as f:
                async for line in f:
                    chunk_result = json.loads(line)
                    merged_results['text'] += chunk_result.get('text', '')
                    merged_results['pages'].extend(chunk_result.get('pages', []))
                    merged_results['chunks_processed'] += 1

            # Sauvegarder les résultats JSON
            async with aiofiles.open(result_paths['json'], mode='w') as f:
                await f.write(json.dumps(merged_results, indent=2))

            # Sauvegarder le texte extrait
            async with aiofiles.open(result_paths['text'], mode='w') as f:
                await f.write(merged_results['text'])

            # Créer et sauvegarder le résumé
            summary = (
                f"Document Analysis Summary\n"
                f"------------------------\n"
                f"Filename: {filename}\n"
                f"Total pages: {len(merged_results['pages'])}\n"
                f"Chunks processed: {merged_results['chunks_processed']}\n"
                f"Text length: {len(merged_results['text'])} characters\n"
            )

            async with aiofiles.open(result_paths['summary'], mode='w') as f:
                await f.write(summary)

            logger.info(f"Results saved successfully in {save_path}")
            return result_paths

        except Exception as e:
            logger.error(f"Error saving final results: {str(e)}")
            raise
