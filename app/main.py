import os
from dotenv import load_dotenv
import gc
import psutil
import resource
from typing import Callable
import asyncio

# Configuration des limites de ressources système
def set_memory_limits():
    # Limite souple de 6GB
    soft = 6 * 1024 * 1024 * 1024  
    # Limite dure de 8GB
    hard = 8 * 1024 * 1024 * 1024
    
    try:
        resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
        logger.info(f"Memory limits set: soft={soft/1024/1024/1024:.1f}GB, hard={hard/1024/1024/1024:.1f}GB")
    except Exception as e:
        logger.warning(f"Could not set memory limits: {str(e)}")

# Charger les variables d'environnement
load_dotenv(override=True)

# Vérifier que les variables essentielles sont présentes
required_vars = ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "DOCUMENT_AI_PROCESSOR_ID"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

from fastapi import FastAPI, Request, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.routes import router
from loguru import logger
import uvicorn

# Configuration des logs avec rotation et rétention
logger.add(
    "logs/app.log",
    rotation="100 MB",
    retention="7 days",
    compression="zip",
    level="INFO",
    backtrace=True,
    diagnose=True
)

class MemoryMiddleware:
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.memory_threshold = 0.80  # 80% d'utilisation mémoire

    async def __call__(self, request: Request) -> Response:
        # Vérifier l'utilisation de la mémoire avant le traitement
        current_memory = psutil.Process(os.getpid()).memory_percent()
        logger.info(f"Current memory usage: {current_memory:.1f}%")

        if current_memory > self.memory_threshold:
            # Forcer le garbage collection si l'utilisation mémoire est élevée
            logger.warning("High memory usage detected, forcing garbage collection")
            gc.collect()

        # Monitorer l'utilisation mémoire pendant le traitement
        start_memory = psutil.Process(os.getpid()).memory_info().rss
        response = await self.get_response(request)
        end_memory = psutil.Process(os.getpid()).memory_info().rss

        memory_diff = end_memory - start_memory
        logger.info(f"Memory change during request: {memory_diff/1024/1024:.1f}MB")

        return response

app = FastAPI(
    title="OCR Application",
    description="Application for processing technical documents with OCR",
    version="1.0.0",
    servers=[
        {
            "url": "http://148.113.45.86:8000",
            "description": "Production server"
        }
    ]
)

@app.on_event("startup")
async def startup_event():
    """Configuration initiale de l'application"""
    # Définir les limites de mémoire
    set_memory_limits()
    
    # Configuration du GC
    gc.enable()
    gc.set_threshold(700, 10, 5)
    
    logger.info("Application startup complete")
    logger.info(f"Initial memory usage: {psutil.Process(os.getpid()).memory_percent():.1f}%")

@app.on_event("shutdown")
async def shutdown_event():
    """Nettoyage à l'arrêt de l'application"""
    gc.collect()
    logger.info("Application shutdown complete")

# Custom exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

# Active CORS avec options limitées
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://148.113.45.86:8000"],  # Restreindre aux origines nécessaires
    allow_credentials=True,
    allow_methods=["POST", "GET"],  # Limiter aux méthodes nécessaires
    allow_headers=["*"],
    max_age=3600  # Cache CORS pour 1 heure
)

@app.middleware("http")
async def memory_management(request: Request, call_next):
    """Middleware pour gérer la mémoire"""
    process = psutil.Process(os.getpid())
    
    try:
        # Log initial memory state
        initial_memory = process.memory_info()
        logger.info(f"Request start memory: RSS={initial_memory.rss/1024/1024:.1f}MB")
        
        # Traiter la requête avec timeout
        response = await asyncio.wait_for(
            call_next(request),
            timeout=300  # 5 minutes timeout
        )
        
        # Forcer le GC après le traitement
        gc.collect()
        
        # Log final memory state
        final_memory = process.memory_info()
        memory_diff = (final_memory.rss - initial_memory.rss) / 1024 / 1024
        logger.info(f"Memory change: {memory_diff:+.1f}MB")
        
        return response
        
    except asyncio.TimeoutError:
        logger.error("Request timeout")
        raise
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise
    finally:
        gc.collect()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware pour logger les requêtes"""
    try:
        logger.info(f"Request path: {request.url.path}")
        logger.info(f"Request headers: {request.headers}")
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise

# Inclure les routes
app.include_router(router)

# Configuration Uvicorn optimisée
config = {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "info",
    "workers": 1,                    # Un seul worker pour mieux gérer la mémoire
    "limit_concurrency": 5,          # Limite le nombre de connexions simultanées
    "limit_max_requests": 100,       # Redémarrage périodique pour éviter les fuites
    "timeout_keep_alive": 5,         # Réduit le temps de maintien des connexions
    "backlog": 2048,                 # File d'attente des connexions
    "h11_max_incomplete_size": 1024, # Limite la taille des requêtes incomplètes
    "access_log": False,             # Désactiver les logs d'accès intégrés (on utilise loguru)
}

if __name__ == "__main__":
    uvicorn.run("app.main:app", **config)
