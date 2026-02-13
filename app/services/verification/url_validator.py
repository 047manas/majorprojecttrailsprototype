import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

class URLValidator:
    @staticmethod
    def check_url_with_text(url: str, candidate_names: List[str], ids: List[str]) -> Dict:
        """
        Generic link checker:
        - Checks reachability (timeout=5).
        - Scans page content for ANY candidate name OR ANY id.
        """
        
        # Pre-cleaning
        target_url = url.strip().rstrip('.,;)')
        if target_url.startswith('www.'):
            target_url = 'https://' + target_url
            
        res = {
            "url": target_url,
            "reachable": False,
            "status_code": None,
            "name_match": False,
            "id_match": False,
            "error": None
        }

        try:
            # User Agent to avoid bot blocking
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            resp = requests.get(target_url, timeout=5, allow_redirects=True, headers=headers)
            res["status_code"] = resp.status_code
            
            # Consider these status codes as reachable
            if resp.status_code in (200, 201, 202, 204, 301, 302, 303, 307, 308):
                res["reachable"] = True
                try:
                    page_text = resp.text.lower()
                except Exception:
                    # In case of binary content or encoding errors
                    page_text = ""
                
                # Check Name Match
                for full_name in candidate_names:
                    # Split name into parts to be more flexible
                    parts = [p.strip().lower() for p in full_name.split() if p.strip()]
                    if parts and all(p in page_text for p in parts):
                        res["name_match"] = True
                        break
                
                # Check ID Match
                for i in ids:
                    if len(i) >= 6 and i.lower() in page_text:
                        res["id_match"] = True
                        break
                        
        except requests.Timeout:
            res["error"] = "Timeout reached (5s)"
            logger.warning(f"Timeout checking URL: {target_url}")
        except Exception as e:
            res["error"] = str(e)
            logger.warning(f"Error checking URL {target_url}: {e}")
            
        return res
