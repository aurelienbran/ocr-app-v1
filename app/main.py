import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv(override=True)

# Vérifier que les variables essentielles sont présentes
required_vars = ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "DOCUMENT_AI_PROCESSOR_ID"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.routes import router
from loguru import logger
import uvicorn

app = FastAPI(
    title="OCR Application",
    description="Application for processing technical documents with OCR",
    version="1.0.0",
    openapi_version="3.0.0",
    root_path=""
)

# Custom exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
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

# Configuration additionnelle OpenAPI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = app.openapi()
    schema["openapi"] = "3.0.0"
    
    # Ajout des composants nécessaires
    if "components" not in schema:
        schema["components"] = {}
    
    if "schemas" not in schema["components"]:
        schema["components"]["schemas"] = {}

    # Définition du schéma de réponse pour les fichiers
    schema["components"]["schemas"]["HTTPValidationError"] = {
        "title": "HTTPValidationError",
        "type": "object",
        "properties": {
            "detail": {
                "title": "Detail",
                "type": "array",
                "items": {"$ref": "#/components/schemas/ValidationError"}
            }
        }
    }

    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="debug",
        limit_concurrency=10,
        limit_max_requests=100,
        timeout_keep_alive=5,
        workers=4
    )
    server = uvicorn.Server(config)
    server.run()