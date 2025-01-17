from PyPDF2 import PdfReader, PdfWriter
from typing import List
import io

class PDFSplitter:
    def __init__(self, max_pages_per_chunk: int = 15):
        self.max_pages_per_chunk = max_pages_per_chunk

    def split_pdf(self, pdf_content: bytes) -> List[bytes]:
        """Split a PDF into chunks of maximum size"""
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        total_pages = len(reader.pages)
        
        chunks = []
        for start_page in range(0, total_pages, self.max_pages_per_chunk):
            writer = PdfWriter()
            end_page = min(start_page + self.max_pages_per_chunk, total_pages)
            
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            
            output = io.BytesIO()
            writer.write(output)
            chunks.append(output.getvalue())
            
        return chunks