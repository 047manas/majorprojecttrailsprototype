
from typing import List
import cv2
import os

def extract_qr_data(image_path: str) -> List[str]:
    """
    Given a path to an image (PNG/JPG) of a certificate page,
    detect and decode any QR codes and return the decoded strings.
    If no QR codes are found, return an empty list.
    """
    print(f"[QR] Trying to decode: {image_path}")
    if not os.path.exists(image_path):
        print(f"[QR] File not found: {image_path}")
        return []

    try:
        # Load image via OpenCV
        img = cv2.imread(image_path)
        if img is None:
            print("[QR] Failed to load image with OpenCV")
            return []

        # Initialize QRCode Detector
        detector = cv2.QRCodeDetector()
        
        # Detect and decode
        print("[QR] Detecting...")
        retval, decoded_info, points, straight_qrcode = detector.detectAndDecodeMulti(img)
        
        if retval:
            print(f"[QR] Raw results: {decoded_info}")
            # decoded_info provides a list of strings if multiple found (or tuple/list)
            # Filter empty strings
            valid_qr = [s for s in decoded_info if s]
            print(f"[QR] Decoded values: {valid_qr}")
            return valid_qr
            
        print("[QR] No QR codes found.")
        return []
    except Exception as e:
        print(f"[QR] Error while decoding: {e}")
        return []
