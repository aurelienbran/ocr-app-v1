from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pathlib import Path
from typing import List
from app.services.ocr import OCRService
from app.schemas.responses import OCRResponse

router = APIRouter(tags=["OCR"])

ocr_service = None
DOCUMENTS_DIR = Path("documents")  # Chemin vers le répertoire des documents

@router.post(
    "/process",
    response_model=OCRResponse,
    description="Process a PDF document using OCR"
)
async def process_document(file: UploadFile = File(...)):
    """
    Process a PDF document using OCR
    """
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

@router.get(
    "/files",
    response_model=List[str],
    description="List all processed files"
)
async def list_processed_files():
    """
    List all available processed files
    """
    try:
        if not DOCUMENTS_DIR.exists():
            return []
        files = [f.name for f in DOCUMENTS_DIR.iterdir() if f.is_file()]
        return sorted(files, key=lambda x: Path(DOCUMENTS_DIR / x).stat().st_mtime, reverse=True)
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/files/{filename}",
    description="Download a specific file"
)
async def get_file(filename: str):
    """
    Download a specific file
    """
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

@router.get("/health", description="Health check endpoint")
async def health_check():
    """Check service health"""
    return {"status": "healthy"}