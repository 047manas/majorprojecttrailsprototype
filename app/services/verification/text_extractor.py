import os
import re
import logging
from typing import List, Dict
from PyPDF2 import PdfReader

# Optional imports for OCR
try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

logger = logging.getLogger(__name__)

class TextExtractor:
    @staticmethod
    def clean_text(s: str) -> str:
        return "".join(ch for ch in s if ch.isprintable()).strip()

    @staticmethod
    def clean_url(raw: str) -> str:
        cleaned = TextExtractor.clean_text(raw)
        return cleaned.replace(" ", "")

    @staticmethod
    def extract_from_file(file_path: str) -> str:
        """
        If file_path ends with .pdf -> use PyPDF2 to extract text.
        If image (jpg/png) -> use Pillow + pytesseract.
        Return full extracted text as a string (can be empty).
        """
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        try:
            if ext == '.pdf':
                reader = PdfReader(file_path)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            elif ext in ['.jpg', '.jpeg', '.png']:
                if Image and pytesseract:
                    try:
                        img = Image.open(file_path)
                        text = pytesseract.image_to_string(img)
                    except Exception as e:
                        logger.error(f"OCR Error: {e}")
                        text = "TODO: OCR not configured correctly or failed."
                else:
                     text = "TODO: Install Pillow and pytesseract for image OCR."
            else:
                 text = "" # Unsupported format
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return ""
            
        return TextExtractor.clean_text(text)

    @staticmethod
    def extract_urls_and_ids(cert_text: str) -> Dict[str, List[str]]:
        """
        From cert_text:
          - Find all URLs with a regex like r'(?:https?://|www\\.)\\S+'.
          - Find ID-like tokens.
        Return dict: { "urls": [...], "ids": [...] }
        """
        # Regex for URLs
        url_pattern = r'(?:https?://|www\.)\S+'
        urls = re.findall(url_pattern, cert_text)
        
        # Simple ID extraction: Look for "Id: XXXXX" or generic long tokens
        id_pattern = r'\b[A-Za-z0-9\-]{10,40}\b'
        ids = re.findall(id_pattern, cert_text)
        
        return {
            "urls": [TextExtractor.clean_url(u) for u in urls],
            "ids": [TextExtractor.clean_text(i) for i in ids]
        }

    @staticmethod
    def guess_candidate_names(cert_text: str) -> List[str]:
        """
        Heuristic:
          - Look for 2–4 capitalized words that look like names.
          - Return up to 3 best guesses.
        """
        lines = cert_text.split('\n')
        candidates = []
        
        blocklist = ['CERTIFICATE', 'UNIVERSITY', 'PROFESSOR', 'COMPLETION', 'OF', 'THE', 'BY', 'DEPARTMENT', 'EDUCATION']
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            words = line.split()
            if 2 <= len(words) <= 4:
                is_title = all(w[0].isupper() and w[1:].islower() for w in words if len(w) > 1)
                is_upper = line.isupper()
                
                if any(b in line.upper() for b in blocklist):
                    continue
                    
                if is_title or is_upper:
                    candidates.append(TextExtractor.clean_text(line))
                    
        return candidates[:3]
