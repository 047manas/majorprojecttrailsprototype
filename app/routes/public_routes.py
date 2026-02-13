from flask import Blueprint, render_template, current_app
from app.models import StudentActivity
from app.verification import hashstore
import os

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def index():
    return render_template('index.html')

@public_bp.route('/verify/<token>')
def verify_public(token):
    activity = StudentActivity.query.filter_by(verification_token=token).first_or_404()
    
    if activity.status not in ['faculty_verified', 'auto_verified']:
        return render_template('verify_public.html', error="This record is not fully verified yet.")
        
    hash_match = False
    recomputed_hash = None
    
    if activity.certificate_file:
         filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], activity.certificate_file)
         if os.path.exists(filepath):
             recomputed_hash = hashstore.calculate_file_hash(filepath)
             if recomputed_hash == activity.certificate_hash:
                 hash_match = True
    
    return render_template('verify_public.html', activity=activity, hash_match=hash_match)
