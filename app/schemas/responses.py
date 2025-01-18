from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List

class OCRResponse(BaseModel):
    """Response model for OCR processing"""
    success: bool = Field(..., description="Indicates if the processing was successful")
    data: Optional[Dict[str, Any]] = Field(None, description="Processed document data")
    
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
                        "docai": "Extracted text...",
                        "vision": "Extracted text..."
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
