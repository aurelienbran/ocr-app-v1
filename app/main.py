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

# Configurations globales
GLOBAL_TIMEOUT = 1800  # 30 minutes
MEMORY_THRESHOLD = 0.80  # 80% d'utilisation mémoire
MEMORY_CHECK_INTERVAL = 30  # Vérifier la mémoire toutes les 30 secondes

class MemoryMiddleware:
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.memory_threshold = MEMORY_THRESHOLD
        self.check_interval = MEMORY_CHECK_INTERVAL

    async def check_memory_periodically(self):
        """Surveille périodiquement l'utilisation de la mémoire"""
        while True:
            current_memory = psutil.Process(os.getpid()).memory_percent()
            if current_memory > self.memory_threshold:
                logger.warning(f"High memory usage: {current_memory:.1f}%")
                gc.collect()
            await asyncio.sleep(self.check_interval)

    async def __call__(self, request: Request) -> Response:
        # Démarrer la surveillance mémoire en background
        monitor_task = asyncio.create_task(self.check_memory_periodically())
        
        try:
            # Vérifier l'utilisation de la mémoire avant le traitement
            current_memory = psutil.Process(os.getpid()).memory_percent()
            logger.info(f"Current memory usage: {current_memory:.1f}%")

            # Monitorer l'utilisation mémoire pendant le traitement
            start_memory = psutil.Process(os.getpid()).memory_info().rss
            response = await self.get_response(request)
            end_memory = psutil.Process(os.getpid()).memory_info().rss

            memory_diff = end_memory - start_memory
            logger.info(f"Memory change during request: {memory_diff/1024/1024:.1f}MB")

            return response
        finally:
            # Arrêter la surveillance mémoire
            monitor_task.cancel()
            gc.collect()

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
    allow_origins=["http://148.113.45.86:8000"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
    max_age=3600
)

@app.middleware("http")
async def memory_management(request: Request, call_next):
    """Middleware pour gérer la mémoire avec timeout augmenté"""
    process = psutil.Process(os.getpid())
    response = None
    
    try:
        # Log initial memory state
        initial_memory = process.memory_info()
        logger.info(f"Request start memory: RSS={initial_memory.rss/1024/1024:.1f}MB")
        
        # Traiter la requête avec un timeout plus long
        response = await asyncio.wait_for(
            call_next(request),
            timeout=GLOBAL_TIMEOUT
        )
        
        # Forcer le GC après le traitement
        gc.collect()
        
        # Log final memory state
        final_memory = process.memory_info()
        memory_diff = (final_memory.rss - initial_memory.rss) / 1024 / 1024
        logger.info(f"Memory change: {memory_diff:+.1f}MB")
        
        return response
        
    except asyncio.TimeoutError:
        logger.error(f"Request timeout after {GLOBAL_TIMEOUT} seconds")
        if response:
            return response
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
    "workers": 1,
    "limit_concurrency": 5,
    "limit_max_requests": 100,
    "timeout_keep_alive": 5,
    "backlog": 2048,
    "h11_max_incomplete_size": 1024,
    "access_log": False,
    "timeout": GLOBAL_TIMEOUT  # Synchroniser avec le timeout global
}

if __name__ == "__main__":
    uvicorn.run("app.main:app", **config)
