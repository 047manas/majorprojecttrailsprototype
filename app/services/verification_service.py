import os
import secrets
from app.verification.auto_verifier import run_auto_verification
from app.verification import hashstore
from app.models import db, StudentActivity, ActivityType
from werkzeug.utils import secure_filename
import json

class VerificationService:
    @staticmethod
    def process_new_activity(student_id, activity_type_id, title, issuer, start_date, end_date, file, upload_folder, existing_hash_list=None):
        filename = secure_filename(file.filename)
        # TODO: Add UUID prefix logic later in Phase 2 for full compliance
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # Auto Verification
        verification = run_auto_verification(filepath)
        
        # Hash Check
        file_hash = hashstore.calculate_file_hash(filepath)
        approved_record = hashstore.lookup_hash(file_hash)
        
        status = 'pending'
        auto_decision = verification['auto_decision']
        
        if approved_record:
            status = 'auto_verified'
            auto_decision = "Verified by previously stored hash (tamper-proof)."
        elif verification['strong_auto']:
            status = 'auto_verified'
            
        return {
            'filename': filename,
            'file_hash': file_hash,
            'status': status,
            'auto_decision': auto_decision,
            'verification_data': verification
        }
