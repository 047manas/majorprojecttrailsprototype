import logging
import os
import re
from typing import List
from app.verification.qr_reader import extract_qr_data as _extract_qr_data

logger = logging.getLogger(__name__)

class QRExtractor:
    @staticmethod
    def extract(file_path: str) -> List[str]:
        """
        Wrapper around existing QR reader.
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        # For now, only processing images for QR.
        if ext not in ['.jpg', '.jpeg', '.png']:
            return []
            
        try:
             # Using the existing module
             # We could migrate the logic here entirely, but wrapping is safer for now.
             # However, the user asked to "Split logic into... QRExtractor".
             # app.verification.qr_reader deals with OpenCV.
             values = _extract_qr_data(file_path)
             return values
        except Exception as e:
            logger.error(f"QR Extraction Error: {e}")
            return []
            
    @staticmethod
    def clean_url(raw: str) -> str:
        # Same cleaning logic as TextExtractor to ensure consistency
        s = "".join(ch for ch in raw if ch.isprintable()).strip()
        return s.replace(" ", "")

    @staticmethod
    def filter_urls(qr_values: List[str]) -> List[str]:
        """
        Filter QR values to return only those that look like URLs.
        """
        cleaned = [QRExtractor.clean_url(v) for v in qr_values]
        # Regex to valid URL start
        return [v for v in cleaned if re.match(r'(?:https?://|www\.)', v)]
