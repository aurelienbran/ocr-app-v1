from pydantic import BaseModel
from typing import Optional, Any

class OCRResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
