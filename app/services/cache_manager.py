import hashlib
import json
import os
import aiofiles
from loguru import logger
import tempfile
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class CacheManager:
    def __init__(self, cache_dir: str = None, ttl_hours: int = 24):
        """
        Gestionnaire de cache pour les résultats OCR
        
        :param cache_dir: Répertoire de cache (utilise tmp si non spécifié)
        :param ttl_hours: Durée de vie du cache en heures
        """
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'ocr_cache')
        self.ttl_hours = ttl_hours
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"Cache initialized in {self.cache_dir}")

    def _get_hash(self, content: bytes) -> str:
        """Calcule un hash unique pour le contenu"""
        return hashlib.sha256(content).hexdigest()

    def _get_cache_path(self, key: str) -> str:
        """Génère le chemin du fichier cache"""
        return os.path.join(self.cache_dir, f"{key}.json")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Récupère un résultat du cache
        
        :param key: Clé de cache
        :return: Résultat ou None si non trouvé/expiré
        """
        cache_path = self._get_cache_path(key)
        try:
            if not os.path.exists(cache_path):
                return None

            async with aiofiles.open(cache_path, 'r') as f:
                cached = json.loads(await f.read())

            # Vérifier si le cache est expiré
            cached_time = datetime.fromisoformat(cached['timestamp'])
            if cached_time + timedelta(hours=self.ttl_hours) < datetime.now():
                await self.invalidate(key)
                return None

            logger.info(f"Cache hit for {key}")
            return cached['data']

        except Exception as e:
            logger.warning(f"Cache read error for {key}: {str(e)}")
            return None

    async def set(self, key: str, data: Dict[str, Any]) -> None:
        """
        Enregistre un résultat dans le cache
        
        :param key: Clé de cache
        :param data: Données à mettre en cache
        """
        cache_path = self._get_cache_path(key)
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            
            async with aiofiles.open(cache_path, 'w') as f:
                await f.write(json.dumps(cache_data))
            
            logger.info(f"Cached result for {key}")

        except Exception as e:
            logger.error(f"Cache write error for {key}: {str(e)}")

    async def invalidate(self, key: str) -> None:
        """
        Invalide une entrée du cache
        
        :param key: Clé à invalider
        """
        cache_path = self._get_cache_path(key)
        try:
            if os.path.exists(cache_path):
                os.remove(cache_path)
                logger.info(f"Invalidated cache for {key}")
        except Exception as e:
            logger.error(f"Cache invalidation error for {key}: {str(e)}")

    async def cleanup_old_entries(self) -> None:
        """Nettoie les entrées expirées du cache"""
        try:
            now = datetime.now()
            for filename in os.listdir(self.cache_dir):
                if not filename.endswith('.json'):
                    continue
                    
                file_path = os.path.join(self.cache_dir, filename)
                try:
                    async with aiofiles.open(file_path, 'r') as f:
                        cached = json.loads(await f.read())
                    
                    cached_time = datetime.fromisoformat(cached['timestamp'])
                    if cached_time + timedelta(hours=self.ttl_hours) < now:
                        os.remove(file_path)
                        logger.info(f"Removed expired cache: {filename}")
                except Exception as e:
                    logger.warning(f"Error checking cache file {filename}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Cache cleanup error: {str(e)}")
