import json
import pytest
from app.services.verification.decision_engine import DecisionEngine

class TestDecisionEngine:
    def test_auto_verified_link_only(self):
        """Test simple success case: Link reachable and name match."""
        link_checks = [
            {
                "url": "https://example.com/cert/123",
                "reachable": True,
                "name_match": True,
                "id_match": False,
                "status_code": 200
            }
        ]
        qr_values = []
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "auto_verified"
        assert mode == "link_only"
        assert strong_auto is True
        assert strong_url == "https://example.com/cert/123"
        assert "matched name/ID" in reason

    def test_auto_verified_qr_match(self):
        """Test success case: Strong match is also in QR codes."""
        url = "https://example.com/cert/qr"
        link_checks = [
            {
                "url": url,
                "reachable": True,
                "name_match": False,
                "id_match": True, # Match by ID
                "status_code": 200
            }
        ]
        qr_values = ["https://example.com/cert/qr"]
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "auto_verified"
        assert mode == "qr+link"
        assert strong_auto is True
        assert strong_url == url

    def test_auto_verified_qr_plus_text_link(self):
        """Test success case: Strong match via Text URL, but QR also exists (different or same)."""
        # If QR exists but the strong match url is NOT in QR??
        # Logic says: if is_qr_url (strong matched url in qr_values) -> qr+link
        # elif clean_qr_values -> qr_plus_text_link
        
        text_url = "https://example.com/text"
        qr_url = "https://example.com/qr"
        
        link_checks = [
            {
                "url": text_url,
                "reachable": True,
                "name_match": True,
                "id_match": False,
                "status_code": 200
            },
            {
                "url": qr_url,
                "reachable": False, # QR link failed
                "name_match": False,
                "id_match": False,
                "status_code": 404
            }
        ]
        qr_values = [qr_url]
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "auto_verified"
        # Since strong match (text_url) is NOT in qr_values, but qr_values is not empty -> qr_plus_text_link
        assert mode == "qr_plus_text_link"
        assert strong_auto is True
        assert strong_url == text_url

    def test_pending_no_match(self):
        """Test failure case: Reachable but no name/ID match."""
        link_checks = [
            {
                "url": "https://example.com/generic",
                "reachable": True,
                "name_match": False,
                "id_match": False,
                "status_code": 200
            }
        ]
        qr_values = []
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "pending"
        assert mode == "text_only"
        assert strong_auto is False
        assert strong_url is None
        assert "No strong signal" in reason

    def test_pending_unreachable(self):
        """Test failure case: Unreachable URL."""
        link_checks = [
            {
                "url": "https://example.com/dead",
                "reachable": False,
                "name_match": False,
                "id_match": False,
                "status_code": 404
            }
        ]
        qr_values = []
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "pending"
        assert strong_auto is False

    def test_qr_only_pending(self):
        """Test case where only QR exists but processing resulted in no strong match."""
        link_checks = [] # Maybe we didn't check it or it failed check
        qr_values = ["https://qr.com"]
        
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate(link_checks, qr_values)
        
        assert status == "pending"
        assert mode == "qr_only"
        assert strong_auto is False

    def test_empty_inputs(self):
        """Test edge case: Empty inputs."""
        status, mode, reason, strong_url, strong_auto, details = DecisionEngine.evaluate([], [])
        
        assert status == "pending"
        assert mode == "text_only"
        assert strong_auto is False
