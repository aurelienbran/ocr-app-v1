import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv(override=True)  # override=True force le rechargement des variables

# Vérifier que les variables essentielles sont présentes
required_vars = ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "DOCUMENT_AI_PROCESSOR_ID"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from loguru import logger
import uvicorn

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

# Active CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request path: {request.url.path}")
    logger.info(f"Request headers: {request.headers}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")