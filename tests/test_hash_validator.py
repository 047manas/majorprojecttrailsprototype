import os
import hashlib
import tempfile
import pytest
from app.services.verification.hash_validator import HashValidator

class TestHashValidator:
    def test_compute_hash_consistency(self):
        """Test that hash computation is consistent and correct."""
        content = b"Hello World"
        expected_hash = hashlib.sha256(content).hexdigest()
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
            
        try:
            computed = HashValidator.compute_hash(tmp_path)
            assert computed == expected_hash
            
            # Run again to ensure deterministic
            computed2 = HashValidator.compute_hash(tmp_path)
            assert computed2 == expected_hash
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_compute_hash_file_not_found(self):
        """Test behavior definition for non-existent file."""
        # implementation currently returns None for FileNotFoundError
        result = HashValidator.compute_hash("non_existent_file_12345.txt")
        assert result is None
