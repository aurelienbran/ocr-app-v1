from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="OCR Application",
    description="Application for processing technical documents with OCR",
    version="1.0.0",
    servers=[
        {
            "url": "http://localhost:8000",  # URL de développement local
            "description": "Local development server"
        }
    ]
)

app.include_router(router)