from pydantic import BaseModel
from typing import Optional, Dict, Any

class OCRResponse(BaseModel):
    """
    Response model for OCR processing
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "metadata": {
                        "docai_confidence": 0.95,
                        "processors": ["documentai", "vision"]
                    },
                    "text": {
                        "docai": "Extracted text example",
                        "vision": "Extracted text example"
                    },
                    "pages": [
                        {
                            "page_number": 1,
                            "dimensions": {
                                "width": 612,
                                "height": 792
                            },
                            "layout": {
                                "confidence": 0.95
                            }
                        }
                    ]
                }
            }
        }