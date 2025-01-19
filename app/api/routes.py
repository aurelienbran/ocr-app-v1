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
    response_model=List[dict],
    description="List all processed files with their details"
)
async def list_processed_files():
    """
    List all available processed files with details about modification time and size
    """
    try:
        if not DOCUMENTS_DIR.exists():
            return []

        files = []
        # Parcourir tous les sous-répertoires dans documents/
        for subdir in DOCUMENTS_DIR.iterdir():
            if subdir.is_dir():
                for file_path in subdir.glob("*.*"):
                    if file_path.is_file():
                        files.append({
                            "name": file_path.name,
                            "path": str(file_path.relative_to(DOCUMENTS_DIR)),
                            "size": file_path.stat().st_size,
                            "modified": file_path.stat().st_mtime
                        })
        
        # Trier par date de modification (le plus récent en premier)
        files.sort(key=lambda x: x["modified"], reverse=True)
        return files
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/download/{file_path:path}",
    description="Download a specific file"
)
async def download_file(file_path: str):
    """
    Download a specific file with proper headers for download
    """
    try:
        # Sécuriser le chemin du fichier
        full_path = DOCUMENTS_DIR / file_path
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File {file_path} not found")
        
        # Vérifier que le fichier est bien dans le répertoire documents/
        if not str(full_path.absolute()).startswith(str(DOCUMENTS_DIR.absolute())):
            raise HTTPException(status_code=403, detail="Access denied")

        filename = full_path.name

        # Déterminer le type MIME en fonction de l'extension
        content_type = "text/plain"
        if filename.endswith('.json'):
            content_type = "application/json"
        elif filename.endswith('.pdf'):
            content_type = "application/pdf"

        return FileResponse(
            path=full_path,
            filename=filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health", description="Health check endpoint")
async def health_check():
    """Check service health"""
    return {"status": "healthy"}