from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models import StudentActivity, ActivityType, db, User
from app.verification import hashstore
import secrets
from functools import wraps

faculty_bp = Blueprint('faculty', __name__)

# --- Auth Helpers ---
# --- Auth Helpers ---
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("You are not authorized to access that page.", "error")
                # Redirect based on role to prevent loops
                if current_user.role == 'student':
                    return redirect(url_for('student.dashboard'))
                elif current_user.role == 'faculty':
                    return redirect(url_for('faculty.dashboard'))
                elif current_user.role == 'admin':
                    return redirect(url_for('analytics.naac_dashboard'))
                return redirect(url_for('public.index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

@faculty_bp.route('/faculty')
@role_required('faculty', 'admin')
def dashboard():
    # Fetch from DB now
    query = db.session.query(StudentActivity).outerjoin(ActivityType).filter(StudentActivity.status == 'pending')
    
    if current_user.role == 'faculty':
        # NEW: Filter by Assigned Reviewer ID (HOD or Activity In-Charge)
        query = query.filter(StudentActivity.assigned_reviewer_id == current_user.id)
        
    pending_activities = query.order_by(StudentActivity.created_at.desc()).all()
    
    return render_template('faculty.html', pending_requests=pending_activities)

@faculty_bp.route('/faculty/review/<int:act_id>')
@role_required('faculty', 'admin')
def review_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    # Optional: Check if assigned to this faculty
    if current_user.role == 'faculty' and activity.assigned_reviewer_id and activity.assigned_reviewer_id != current_user.id:
         flash("You are not assigned to review this activity.", "warning")
         return redirect(url_for('faculty.dashboard'))
         
    return render_template('faculty_review.html', activity=activity)

@faculty_bp.route('/faculty/approve/<int:act_id>', methods=['POST'])
@role_required('faculty', 'admin')
def approve_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    comment = request.form.get('faculty_comment', '')
    
    activity.status = 'faculty_verified'
    activity.faculty_id = current_user.id
    activity.faculty_comment = comment
    
    # Generate Verification Token if not exists
    if not activity.verification_token:
        activity.verification_token = secrets.token_urlsafe(16)
    activity.faculty_id = current_user.id
    activity.faculty_comment = comment
    
    if activity.certificate_hash:
         hashstore.store_approved_hash(
            file_hash=activity.certificate_hash,
            roll_no=activity.student.institution_id,
            filename=activity.certificate_file,
            request_id=activity.id,
            faculty_comment=comment
        )

    db.session.commit()
    flash(f"Activity #{act_id} Approved.")
    return redirect(url_for('faculty.dashboard'))

@faculty_bp.route('/faculty/reject/<int:act_id>', methods=['POST'])
@role_required('faculty', 'admin')
def reject_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    comment = request.form.get('faculty_comment', '')
    
    activity.status = 'rejected'
    activity.faculty_id = current_user.id
    activity.faculty_comment = comment
    
    db.session.commit()
    flash(f"Activity #{act_id} Rejected.")
    return redirect(url_for('faculty.dashboard'))
