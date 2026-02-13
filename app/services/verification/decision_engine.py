from typing import List, Dict, Tuple
import json

class DecisionEngine:
    @staticmethod
    def evaluate(link_checks: List[Dict], clean_qr_values: List[str]) -> Tuple[str, str, str, str, bool, str]:
        """
        Pure logic to determine:
        - status
        - verification_mode
        - reason
        - strong_match_url
        - strong_auto (bool)
        - auto_details (json string)
        
        Args:
            link_checks: Output from URLValidator.
            clean_qr_values: Output from QRExtractor.
            
        Returns:
            (status, verification_mode, reason, strong_match_url, strong_auto, auto_details)
        """
        verification_mode = "text_only"
        if clean_qr_values:
            verification_mode = "qr_only" # Initial state

        reason = "No strong signal found."
        strong_auto = False
        status = "pending"
        strong_match_url = None
        
        # Find strong match
        # Reachable AND (Name OR ID match)
        strong = next((lc for lc in link_checks if lc["reachable"] and (lc["name_match"] or lc["id_match"])), None)
        
        if strong:
            strong_auto = True
            status = "auto_verified"
            strong_match_url = strong["url"]
            
            # Determine specific mode
            # Check if the strong URL matches any of the QR codes
            # We need to be careful with trailing slashes or minor diffs, but original logic was exact match check (clean_url)
            # URLValidator returns cleaned url. QRExtractor returns cleaned url.
            
            is_qr_url = any(strong["url"] == v for v in clean_qr_values)
            
            if is_qr_url:
                verification_mode = "qr+link"
                reason = "QR code URL reached issuer site and matched name/ID."
            elif clean_qr_values:
                verification_mode = "qr_plus_text_link"
                reason = "Text/URL + QR evidence: issuer site reachable with matching name/ID."
            else:
                verification_mode = "link_only"
                reason = "Issuer link from certificate text matched name/ID."

        # Construct Details
        # We need to reconstruct 'checked_urls' from input for the details JSON, 
        # or we assume caller gave us all checks.
        checked_urls = [lc['url'] for lc in link_checks]

        auto_details = json.dumps({
            "reason": reason,
            "qr_found": len(clean_qr_values) > 0,
            "checked_urls": checked_urls,
            "strong_match_url": strong_match_url,
            "link_checks": link_checks,
            "qr_values": clean_qr_values
        })
        
        return status, verification_mode, reason, strong_match_url, strong_auto, auto_details
