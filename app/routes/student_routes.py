from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, make_response, send_from_directory, abort
from flask_login import login_required, current_user
from app.models import ActivityType, StudentActivity, db, User
from app.services.verification.verification_service import VerificationService
from app.verification import extract, hashstore
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
import os
import io
import json
import secrets
from datetime import datetime
import uuid
import uuid
import filetype

student_bp = Blueprint('student', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
ALLOWED_MIME_TYPES = {'application/pdf', 'image/png', 'image/jpeg', 'image/jpg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_mime_type(file_stream):
    # Read first 2048 bytes for signature checking
    header = file_stream.read(2048)
    file_stream.seek(0) # Reset stream pointer
    
    kind = filetype.guess(header)
    if kind is None:
        return False
        
    return kind.mime in ALLOWED_MIME_TYPES

@student_bp.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin.users_dashboard'))
    elif current_user.role == 'faculty':
        return redirect(url_for('faculty.dashboard'))

    if request.method == 'POST':
        # Use hidden field or current_user data if student
        roll_number = request.form.get('roll_number') if not (current_user.role == 'student' and current_user.institution_id) else current_user.institution_id
        
        activity_type_id = request.form.get('activity_type_id')
        title = request.form.get('title')
        issuer = request.form.get('issuer_name')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        # Basic Form Validation
        if not activity_type_id:
            flash("Please select an Activity Type.")
            return redirect(request.url)
        if not title:
            flash("Activity Title is required.")
            return redirect(request.url)

        selected_activity = None
        custom_category = None
        
        if activity_type_id == 'other':
            custom_category = request.form.get('custom_category')
            if not custom_category:
                 flash("Custom Category is required for 'Other'.")
                 return redirect(request.url)
        else:
            selected_activity = ActivityType.query.get(int(activity_type_id))
            if not selected_activity:
                flash("Invalid Activity Type.")
                return redirect(request.url)
        
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
            
        # Secure Upload Logic
        if file and allowed_file(file.filename):
            if not validate_mime_type(file.stream):
               flash('Invalid file type detected. Please upload a valid PDF or Image.')
               return redirect(request.url)

            original_filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
            
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            
            filepath = os.path.join(upload_folder, unique_filename)
            file.save(filepath)
            
            # --- Verification Logic (Refactored) ---
            # 1. New Auto-Verifier Service
            verifier = VerificationService()
            verification = verifier.verify(filepath)
            print("AUTO VERIFICATION RESULT:", verification)
            
            # 2. Defaults
            status = 'pending'
            auto_decision = verification['auto_decision']
            decision = auto_decision 
            
            # 3. Hash Checks
            file_hash = hashstore.calculate_file_hash(filepath)
            approved_record = hashstore.lookup_hash(file_hash)
            
            if approved_record:
                status = 'auto_verified'
                decision = "Verified by previously stored hash (tamper-proof)."
                auto_decision = decision
            elif verification['strong_auto']:
                status = 'auto_verified'
                # auto_decision already set from module
            
            print("Final status for this activity:", status)
            
            # --- Routing Logic (Assigned Reviewer) ---
            assigned_reviewer_id = None
            if status == 'pending':
                # 1. Specific Activity In-Charge
                if selected_activity and selected_activity.faculty_incharge_id:
                    assigned_reviewer_id = selected_activity.faculty_incharge_id
                else:
                    # 2. Routing to HOD (Generic/Other)
                    hod = User.query.filter_by(
                        department=current_user.department, 
                        role='faculty',
                        position='hod'
                    ).first()
                    if hod:
                        assigned_reviewer_id = hod.id

            # --- Create StudentActivity Record ---
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

            # Get Previous Activity (Linked List)
            prev_activity = StudentActivity.query.filter_by(student_id=current_user.id).order_by(StudentActivity.created_at.desc()).first()
            prev_id = prev_activity.id if prev_activity else None

            new_activity = StudentActivity(
                student_id=current_user.id,
                activity_type_id=selected_activity.id if selected_activity else None,
                custom_category=custom_category,
                title=title,
                issuer_name=issuer,
                start_date=start_date,
                end_date=end_date,
                certificate_file=unique_filename,
                certificate_hash=file_hash,
                urls_json=json.dumps(verification['urls']),
                ids_json=json.dumps(verification['ids']),
                status=status,
                auto_decision=auto_decision,
                prev_activity_id=prev_id,
                assigned_reviewer_id=assigned_reviewer_id,
                verification_token=secrets.token_urlsafe(16) if status == 'auto_verified' else None,
                verification_mode=verification.get('verification_mode', 'text_only'),
                auto_details=verification.get('auto_details')
            )
            db.session.add(new_activity)
            db.session.commit()
            
            msg_status = "Verified!" if status == "auto_verified" else "Queued for Faculty."
            flash(f"Activity '{title}' Recorded. {msg_status}")

            return redirect(url_for('student.dashboard'))

            msg_status = "Verified!" if status == "auto_verified" else "Queued for Faculty."
            flash(f"Activity '{title}' Recorded. {msg_status}")

            return redirect(url_for('student.dashboard'))

        else:
            flash('Invalid file type.')
            return redirect(request.url)
    
    return render_template('index.html', result=result, user_roll_no=user_roll_no, activity_types=activity_types)

@student_bp.route('/portfolio')
@login_required
def portfolio():
    activities = StudentActivity.query.filter_by(student_id=current_user.id).order_by(StudentActivity.created_at.desc()).all()
    return render_template('portfolio.html', activities=activities)

@student_bp.route('/portfolio.pdf')
@login_required
def portfolio_pdf():
    mode = request.args.get('mode', 'full')
    
    query = StudentActivity.query.filter_by(student_id=current_user.id)
    
    if mode == 'verified':
        query = query.filter(StudentActivity.status.in_(['auto_verified', 'faculty_verified']))
        
    activities = query.order_by(StudentActivity.created_at.desc()).all()
    
    html = render_template('student/portfolio_pdf.html', 
                           activities=activities, 
                           user=current_user,
                           generation_date=datetime.now().strftime('%Y-%m-%d'))
    
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    
    if pisa_status.err:
       return f"Error creating PDF: {pisa_status.err}", 500
       
    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=portfolio_{current_user.institution_id}.pdf'
    
    return response

@student_bp.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    if current_user.role not in ['faculty', 'admin', 'student']:
        pass
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
