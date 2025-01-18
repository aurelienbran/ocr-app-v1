import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv(override=True)

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
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="OCR Application",
    description="Application for processing technical documents with OCR",
    version="1.0.0",
    openapi_version="3.0.0",  # Ajout de la version OpenAPI
    docs_url=None,  # Désactive l'endpoint /docs par défaut
    redoc_url=None  # Désactive l'endpoint /redoc par défaut
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

# Custom OpenAPI et Swagger UI endpoints
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " - Swagger UI",
        swagger_js_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui-bundle.min.js",
        swagger_css_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui.min.css",
    )

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_endpoint():
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Ajouter explicitement la version OpenAPI
    openapi_schema["openapi"] = "3.0.0"
    return openapi_schema

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")