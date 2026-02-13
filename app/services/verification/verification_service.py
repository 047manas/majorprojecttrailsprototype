import logging
import json
from typing import Dict, List, Any

# Import modular components
from .text_extractor import TextExtractor
from .qr_extractor import QRExtractor
from .hash_validator import HashValidator
from .url_validator import URLValidator
from .decision_engine import DecisionEngine

logger = logging.getLogger(__name__)

class VerificationService:
    def verify(self, file_path: str) -> Dict[str, Any]:
        """
        Orchestrates the verification process.
        Matches the output format of the old auto_verifier.py.
        """
        logger.info(f"Starting verification for: {file_path}")
        
        # 1. Extract Text
        logger.debug("Extracting text...")
        cert_text_raw = TextExtractor.extract_from_file(file_path)
        cert_text = TextExtractor.clean_text(cert_text_raw)
        
        # 2. Extract QR
        logger.debug("Extracting QR...")
        qr_values_raw = QRExtractor.extract(file_path)
        # Note: qr_values_raw are already strings from the reader
        
        # 3. Parse Data
        logger.debug("Parsing data...")
        parsed = TextExtractor.extract_urls_and_ids(cert_text)
        candidate_names = TextExtractor.guess_candidate_names(cert_text)
        
        # Clean and Prepare URLs
        urls_from_text = parsed['urls']
        ids = parsed['ids']
        clean_qr_values = [QRExtractor.clean_url(v) for v in qr_values_raw]
        
        # Merge URLs for checking
        urls_for_check = []
        urls_for_check.extend(urls_from_text)
        
        # Filter QR values that are URLs
        qr_urls = QRExtractor.filter_urls(clean_qr_values)
        urls_for_check.extend(qr_urls)
        
        # Deduplicate
        urls_for_check = list(dict.fromkeys(urls_for_check))
        
        logger.info(f"URLs to check: {urls_for_check}")
        
        # 4. Check Links
        logger.debug("Validating links...")
        link_checks = [URLValidator.check_url_with_text(u, candidate_names, ids) for u in urls_for_check]
        
        # 5. Make Decision
        logger.debug(" evaluating decision...")
        status, verification_mode, reason, strong_match_url, strong_auto, auto_details = DecisionEngine.evaluate(
            link_checks, clean_qr_values
        )
        
        logger.info(f"Decision: {status}, Mode: {verification_mode}")

        # 6. Format Output (Exactly matching old format)
        return {
            "cert_text": cert_text,
            "urls": urls_for_check,
            "ids": ids,
            "candidate_names": candidate_names,
            "link_checks": link_checks,
            "strong_auto": strong_auto,
            "auto_decision": reason, # Old key was 'auto_decision' holding the reason string
            "verification_mode": verification_mode,
            "auto_details": auto_details
        }
