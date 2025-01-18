from pydantic import BaseModel
from typing import Dict, Any, Optional

class OCRResponse(BaseModel):
    """Modèle de réponse pour le traitement OCR"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None