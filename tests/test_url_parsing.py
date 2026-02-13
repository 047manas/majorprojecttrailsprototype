import pytest
from app.services.verification.text_extractor import TextExtractor
from app.services.verification.qr_extractor import QRExtractor

class TestURLParsing:
    def test_extract_urls_from_text(self):
        """Test extraction of URLs from text blob."""
        text = """
        Visit us at https://example.com/page.
        Also check www.test.org for details.
        Ignore this.
        """
        parsed = TextExtractor.extract_urls_and_ids(text)
        urls = parsed['urls']
        
        assert "https://example.com/page." in urls
        assert "www.test.org" in urls
        assert len(urls) >= 2

    def test_extract_ids_from_text_ids(self):
        """Test extraction of ID-like patterns."""
        text = "ID: 1234567890-ABC  References: XYZ-9876543210"
        parsed = TextExtractor.extract_urls_and_ids(text)
        ids = parsed['ids']
        
        assert "1234567890-ABC" in ids
        assert "XYZ-9876543210" in ids

    def test_clean_url(self):
        """Test URL cleaning util."""
        raw = " https://example.com/  "
        assert TextExtractor.clean_url(raw) == "https://example.com/"
        
        raw_broken = "https:// ex ample .com"
        # The current implementation just removes spaces.
        assert TextExtractor.clean_url(raw_broken) == "https://example.com"

    def test_qr_url_filter(self):
        """Test QR Extractor logic for filtering valid URLs."""
        raw_qr = [
            "https://valid.com",
            "http://also.valid.org",
            "Not A URL",
            "123456",
            "www.missing-schema.com"
        ]
        
        filtered = QRExtractor.filter_urls(raw_qr)
        
        assert "https://valid.com" in filtered
        assert "http://also.valid.org" in filtered
        assert "www.missing-schema.com" in filtered
        assert "Not A URL" not in filtered
        assert "123456" not in filtered
