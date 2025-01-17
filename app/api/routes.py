from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pathlib import Path
from typing import List
from app.services.ocr import OCRService
from app.schemas.responses import OCRResponse

router = APIRouter()
ocr_service = None
DOCUMENTS_DIR = Path("documents")  # Chemin vers le répertoire des documents

@router.post("/process", response_model=OCRResponse)
async def process_document(file: UploadFile = File(...)):
    """Process a PDF document using OCR"""
    global ocr_service
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        if ocr_service is None:
            ocr_service = OCRService()
        
        content = await file.read()
        result = await ocr_service.process_document(content, file.filename)
        
        return OCRResponse(
            success=True,
            data=result
        )
    
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files", response_model=List[str])
async def list_processed_files():
    """List all available processed files"""
    try:
        if not DOCUMENTS_DIR.exists():
            return []
        return [f.name for f in DOCUMENTS_DIR.iterdir() if f.is_file()]
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{filename}")
async def get_file(filename: str):
    """Download a specific file"""
    try:
        file_path = DOCUMENTS_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File {filename} not found")
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Check service health"""
    return {"status": "healthy"}