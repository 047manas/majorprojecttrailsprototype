from models import StudentActivity

def find_rejected_by_hash(file_hash):
    # Check if this certificate was previously rejected
    return StudentActivity.query.filter_by(certificate_hash=file_hash, status='rejected').first()
