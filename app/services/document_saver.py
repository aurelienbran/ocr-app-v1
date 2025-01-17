from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import json
import os

class DocumentSaver:
    def __init__(self, base_path: str = "documents"):
        self.base_path = Path(base_path)
        self._ensure_output_directory()

    def _ensure_output_directory(self):
        """Ensure the output directory exists"""
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True)

    async def save_results(self, results: Dict[str, Any], original_filename: str) -> Dict[str, str]:
        """Save OCR results in multiple formats"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{timestamp}_{Path(original_filename).stem}"

        # Save JSON results
        json_path = self.base_path / f"{base_filename}_results.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Save extracted text
        text_path = self.base_path / f"{base_filename}_text.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write("=== Document AI Text ===\n")
            f.write(results['text']['docai'])
            f.write("\n\n=== Vision AI Text ===\n")
            f.write(results['text']['vision'])

        # Save summary
        summary_path = self.base_path / f"{base_filename}_summary.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_summary(results))

        return {
            'json': str(json_path),
            'text': str(text_path),
            'summary': str(summary_path)
        }

    def _generate_summary(self, results: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the results"""
        summary = ["=== OCR Processing Summary ==="]

        # Add metadata
        summary.append("\nMetadata:")
        metadata = results.get('metadata', {})
        for key, value in metadata.items():
            summary.append(f"- {key}: {value}")

        # Add page information
        pages = results.get('pages', [])
        summary.append(f"\nPages Processed: {len(pages)}")
        for page in pages:
            confidence = page.get('layout', {}).get('confidence', 0)
            summary.append(f"- Page {page['page_number']}: Confidence {confidence:.2%}")

        # Add visual elements summary
        visual_elements = results.get('visual_elements', {})
        if visual_elements:
            summary.append("\nVisual Elements:")
            objects = visual_elements.get('objects', [])
            if objects:
                summary.append(f"- Detected Objects: {len(objects)}")

        return '\n'.join(summary)
