import hashlib
from models import StudentActivity

def calculate_file_hash(filepath):
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
    except FileNotFoundError:
        return None
    return sha256_hash.hexdigest()

def lookup_hash(file_hash):
    # Look for approved/verified activities with this hash
    record = StudentActivity.query.filter_by(certificate_hash=file_hash).filter(
        StudentActivity.status.in_(['auto_verified', 'faculty_verified'])
    ).first()
    return record

def store_approved_hash(file_hash, roll_no, filename, request_id, faculty_comment):
    # DB is updated via app.py directly on the Activity record.
    # This function exists to satisfy the interface or future extension.
    pass
