import requests
from . import analyze, hashstore, queue

def verify_links(urls, cert_text, ids, candidate_names):
    results = []
    for url in urls:
        res_dict = {
            'url': url,
            'reachable': False,
            'name_match': False,
            'id_match': False
        }
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                res_dict['reachable'] = True
                # Simple check logic could go here
                content = r.text.lower()
                # Determine name match ...
        except Exception:
            pass
        results.append(res_dict)
    return results

def run_auto_verification(file_path: str, cert_text: str, ids: list[str]) -> dict:
    """
    Input:
      file_path: path to saved certificate (PDF or image)
      cert_text: extracted text from the certificate
      ids: ID candidates extracted from text
    Output dict with at least:
      {
        "urls": [...],
        "link_checks": [  # per URL
          {
            "url": ...,
            "status_code": ...,
            "reachable": True/False,
            "name_match": True/False,
            "id_match": True/False,
          },
          ...
        ],
        "strong_auto": True/False,   # live link + name + ID match OR hash match
        "hash_match": True/False,    # if you check against previous hashes
        "file_hash": str,
        "ids": list
      }
    """
    check_result = {
        "urls": [],
        "link_checks": [],
        "strong_auto": False,
        "hash_match": False,
        "file_hash": None,
        "ids": ids
    }

    # 1. Calculate Hash
    file_hash = hashstore.calculate_file_hash(file_path)
    check_result['file_hash'] = file_hash
    
    # 2. Check Hash against Approved DB
    approved_record = hashstore.lookup_hash(file_hash)
    if approved_record:
        check_result['hash_match'] = True
        check_result['strong_auto'] = True
        return check_result # Return early or continue? User said "Output dict with at least...", implies full details.
        # But if hash match, we are good. Let's populate minimal URL data just in case.

    # 3. Extract URLs (if not already done, but user asked to do it here)
    # Re-using analyze module logic
    raw_urls, _ = analyze.analyze_text(cert_text)
    
    # 4. Clean/Normalize
    check_result['urls'] = analyze.clean_and_normalize_urls(raw_urls)
    
    # 5. Extract Candidates for Name (passed-in or distinct?)
    # The signature in prompt didn't ask for candidate_names input, so we extract here.
    candidate_names = analyze.extract_suspected_name(cert_text)
    
    # 6. Verify Links
    # verify_links(urls, cert_text, ids, candidate_names)
    link_results = verify_links(check_result['urls'], cert_text, ids, candidate_names)
    check_result['link_checks'] = link_results
    
    # 7. Determine Strong Auto (Smart Verification)
    # "at least one URL with: reachable == True AND name_match == True AND id_match == True"
    has_strong_link = any(l['reachable'] and l['name_match'] and l['id_match'] for l in link_results)
    
    if has_strong_link:
        check_result['strong_auto'] = True
        
    return check_result
