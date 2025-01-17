from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="OCR Application",
    description="Application for processing technical documents with OCR",
    version="1.0.0"
)

app.include_router(router)
