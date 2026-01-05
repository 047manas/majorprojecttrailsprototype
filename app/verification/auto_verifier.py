import re
import json
import hashlib
import requests
import os
from typing import List, Dict, Tuple
from PyPDF2 import PdfReader

# Optional imports for OCR
try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

def extract_text_from_file(file_path: str) -> str:
    """
    If file_path ends with .pdf -> use PyPDF2 to extract text.
    If image (jpg/png) -> use Pillow + pytesseract (or return simulated text with a TODO).
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
                    print(f"OCR Error: {e}")
                    text = "TODO: OCR not configured correctly or failed."
            else:
                 text = "TODO: Install Pillow and pytesseract for image OCR."
        else:
             text = "" # Unsupported format
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return ""
        
    return text

# Helpers
def clean_text(s: str) -> str:
    return "".join(ch for ch in s if ch.isprintable()).strip()

def clean_url(raw: str) -> str:
    cleaned = clean_text(raw)
    return cleaned.replace(" ", "")

def extract_urls_and_ids(cert_text: str) -> Dict[str, List[str]]:
    """
    From cert_text:
      - Find all URLs with a regex like r'(?:https?://|www\\.)\\S+'.
      - Find ID-like tokens.
    Return dict:
      {
        "urls": [...],
        "ids": [...]
      }
    """
    # Regex for URLs
    url_pattern = r'(?:https?://|www\.)\S+'
    urls = re.findall(url_pattern, cert_text)
    
    # Simple ID extraction: Look for "Id: XXXXX" or generic long tokens
    id_pattern = r'\b[A-Za-z0-9\-]{10,40}\b'
    ids = re.findall(id_pattern, cert_text)
    
    return {
        "urls": [clean_url(u) for u in urls],
        "ids": [clean_text(i) for i in ids]
    }

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
                candidates.append(clean_text(line))
                
    return candidates[:3]

def check_url_with_text(url: str, candidate_names: List[str], ids: List[str]) -> Dict:
    """
    Generic link checker:
    - Checks reachability.
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
        resp = requests.get(target_url, timeout=8, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        res["status_code"] = resp.status_code
        
        # Consider these status codes as reachable
        if resp.status_code in (200, 201, 202, 204, 301, 302, 303, 307, 308):
            res["reachable"] = True
            page_text = resp.text.lower()
            
            # Check Name Match
            for full_name in candidate_names:
                # Split name into parts to be more flexible (e.g. "Manas Garikapati" matched if "Manas" and "Garikapati" appear)
                parts = [p.strip().lower() for p in full_name.split() if p.strip()]
                if parts and all(p in page_text for p in parts):
                    res["name_match"] = True
                    break
            
            # Check ID Match
            for i in ids:
                if len(i) >= 6 and i.lower() in page_text:
                    res["id_match"] = True
                    break
                    
    except Exception as e:
        res["error"] = str(e)
        
    return res

def run_auto_verification(file_path: str) -> Dict:
    """
    High-level pipeline.
    """
    # 1. Extract Text
    cert_text_raw = extract_text_from_file(file_path)
    cert_text = clean_text(cert_text_raw)
    
    # 2. QR Extraction
    from .qr_reader import extract_qr_data
    qr_values = []
    ext = os.path.splitext(file_path)[1].lower()
    
    # For now, only processing images for QR. PDF support would require pdf2image.
    if ext in ['.jpg', '.jpeg', '.png']:
        qr_values = extract_qr_data(file_path)
    
    # 3. Parse and Clean Data
    parsed = extract_urls_and_ids(cert_text)
    
    urls_from_text = [clean_url(u) for u in parsed['urls'] if clean_url(u)]
    ids = [clean_text(i) for i in parsed['ids']]
    clean_qr_values = [clean_url(v) for v in qr_values if clean_url(v)]
    
    candidate_names = guess_candidate_names(cert_text)
    
    # Merge URLs (QR + Text)
    # We treat QR values that look like URLs as URLs check.
    urls_for_check = []
    
    # Add Text URLs
    for u in urls_from_text:
        urls_for_check.append(u)
        
    # Add QR URLs
    for v in clean_qr_values:
        if re.match(r'(?:https?://|www\.)', v):
            urls_for_check.append(v)
            
    # Deduplicate while preserving order
    urls_for_check = list(dict.fromkeys(urls_for_check))
    
    print(f"[AUTO] urls_for_check: {urls_for_check}")
    
    # 4. Check Links
    link_checks = [check_url_with_text(u, candidate_names, ids) for u in urls_for_check]
    
    # 5. Make Decision
    verification_mode = "text_only"
    if clean_qr_values:
        verification_mode = "qr_only" # Initial state, might upgrade

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
        is_qr_url = any(clean_url(strong["url"]) == v for v in clean_qr_values)
        
        if is_qr_url:
            verification_mode = "qr+link"
            reason = "QR code URL reached issuer site and matched name/ID."
        elif clean_qr_values:
            verification_mode = "qr_plus_text_link"
            reason = "Text/URL + QR evidence: issuer site reachable with matching name/ID."
        else:
            verification_mode = "link_only"
            reason = "Issuer link from certificate text matched name/ID."
            
    # 6. Construct Details
    auto_details = json.dumps({
        "reason": reason,
        "qr_found": len(clean_qr_values) > 0,
        "checked_urls": urls_for_check,
        "strong_match_url": strong_match_url,
        "link_checks": link_checks,
        "qr_values": clean_qr_values
    })
    
    print(f"[AUTO] Final decision: {status}, mode: {verification_mode}, reason: {reason}")

    return {
        "cert_text": cert_text,
        "urls": urls_for_check,
        "ids": ids,
        "candidate_names": candidate_names,
        "link_checks": link_checks,
        "strong_auto": strong_auto,
        "auto_decision": reason,
        "verification_mode": verification_mode,
        "auto_details": auto_details
    }
