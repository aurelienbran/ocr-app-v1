from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

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

app.include_router(router)