from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pathlib import Path
from typing import List
from app.services.ocr import OCRService
from app.schemas.responses import OCRResponse
import tempfile
import os
import asyncio
import psutil

router = APIRouter()
ocr_service = None
DOCUMENTS_DIR = Path("documents")  # Chemin vers le répertoire des documents
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading

@router.post("/process", response_model=OCRResponse)
async def process_document(request: Request, file: UploadFile = File(...)):
    """Process a PDF document using OCR"""
    global ocr_service
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        if ocr_service is None:
            ocr_service = OCRService()
        
        # Créer un fichier temporaire pour stocker le PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            # Lire et écrire le fichier par morceaux
            while chunk := await file.read(CHUNK_SIZE):
                tmp_file.write(chunk)
            tmp_file.flush()
            
            # Traiter le document
            with open(tmp_file.name, 'rb') as f:
                content = f.read()
                result = await ocr_service.process_document(content, file.filename)
            
            # Nettoyer le fichier temporaire
            os.unlink(tmp_file.name)
        
        return OCRResponse(
            success=True,
            data=result
        )
    
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        # S'assurer que le fichier temporaire est supprimé en cas d'erreur
        if 'tmp_file' in locals():
            try:
                os.unlink(tmp_file.name)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files", response_model=List[str])
async def list_processed_files():
    """List all available processed files"""
    try:
        if not DOCUMENTS_DIR.exists():
            return []
        files = [f.name for f in DOCUMENTS_DIR.iterdir() if f.is_file()]
        return sorted(files, key=lambda x: os.path.getmtime(str(DOCUMENTS_DIR / x)), reverse=True)
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
    return {"status": "healthy", "memory_info": get_memory_info()}

def get_memory_info():
    """Get current memory usage information"""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return {
            "rss": f"{memory_info.rss / 1024 / 1024:.2f} MB",
            "vms": f"{memory_info.vms / 1024 / 1024:.2f} MB"
        }
    except:
        return {"status": "memory info not available"}