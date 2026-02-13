import logging
from app.verification import hashstore

logger = logging.getLogger(__name__)

class HashValidator:
    @staticmethod
    def compute_hash(file_path: str) -> str:
        """
        Compute SHA-256 hash of the file.
        """
        return hashstore.calculate_file_hash(file_path)

    @staticmethod
    def validate(file_hash: str):
        """
        Check if hash exists in DB (auto_verified or faculty_verified).
        Returns the record if found, else None.
        """
        if not file_hash:
            return None
        return hashstore.lookup_hash(file_hash)
