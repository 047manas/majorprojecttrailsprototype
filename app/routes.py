import os
import json
import secrets
from functools import wraps
from datetime import datetime
import csv
import io
from flask import Blueprint, request, render_template, flash, redirect, url_for, send_from_directory, abort, make_response, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_, and_, func, desc, case, distinct, extract
from sqlalchemy.orm import aliased

# --- Imports from Modules ---
from app.models import db, User, ActivityType, StudentActivity
from app.verification import extract, analyze, verify, hashstore, queue
from app.verification.auto_verifier import run_auto_verification
from xhtml2pdf import pisa

bp = Blueprint('main', __name__)

# --- Auth Helpers ---

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                return abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- Routes ---

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('main.admin_users'))
        elif current_user.role == 'faculty':
            return redirect(url_for('main.faculty_dashboard'))
        else:
            return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Strict Active Check
            if not user.is_active:
                flash('Account deactivated. Please contact administrator.')
                return render_template('login.html')
            
            login_user(user)
            flash('Logged in successfully.')
            
            # Role-based redirect
            if user.role == 'admin':
                return redirect(url_for('main.admin_users'))
            elif user.role == 'faculty':
                return redirect(url_for('main.faculty_dashboard'))
            else:
                return redirect(url_for('main.index'))
        else:
            flash('Invalid email or password.')
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('main.login'))

@bp.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    if current_user.role not in ['faculty', 'admin', 'student']:
        pass
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@bp.route('/', methods=['GET', 'POST'])
@role_required('student', 'admin') 
def index():
    result = None
    activity_types = ActivityType.query.all()
    
    # Pre-fill/Force Roll Number from Institution ID for Students
    user_roll_no = ""
    if current_user.role == 'student' and current_user.institution_id:
        user_roll_no = current_user.institution_id
    
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
            
        if file and extract.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # --- Verification Logic ---
            # 1. New Auto-Verifier Module
            verification = run_auto_verification(filepath)
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
                certificate_file=filename,
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

            return redirect(url_for('main.index'))

        else:
            flash('Invalid file type.')
            return redirect(request.url)

    return render_template('index.html', result=result, user_roll_no=user_roll_no, activity_types=activity_types)

# --- Faculty / Admin Routes ---

@bp.route('/faculty')
@role_required('faculty', 'admin')
def faculty_dashboard():
    # Fetch from DB now
    query = db.session.query(StudentActivity).outerjoin(ActivityType).filter(StudentActivity.status == 'pending')
    
    if current_user.role == 'faculty':
        # NEW: Filter by Assigned Reviewer ID (HOD or Activity In-Charge)
        query = query.filter(StudentActivity.assigned_reviewer_id == current_user.id)
        
    pending_activities = query.order_by(StudentActivity.created_at.desc()).all()
    
    return render_template('faculty.html', pending_requests=pending_activities)

@bp.route('/hod/stats')
@role_required('faculty')
def hod_stats():
    if current_user.position != 'hod':
        abort(403)
        
    dept = current_user.department
    if not dept:
        flash('Department not assigned to HOD account.', 'error')
        return redirect(url_for('main.index'))

    # Filters
    activity_type_id = request.args.get('activity_type')
    batch_year = request.args.get('batch_year')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    status_filter = request.args.get('status')
    search_query = request.args.get('search')

    def apply_hod_filters(query):
        # Join User to filter by department
        query = query.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
        
        if activity_type_id:
            query = query.filter(StudentActivity.activity_type_id == activity_type_id)
        if batch_year:
            query = query.filter(User.batch_year == batch_year)
        # Use issue_date if available (new standard), fallback to created_at logic if needed
        # Prompt says "Date range (by issue_date or approved_at)"
        # Let's use issue_date for general filtering as it represents the activity time
        if start_date:
            query = query.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
        if status_filter:
            query = query.filter(StudentActivity.status == status_filter)
        if search_query:
            # Search by student name or roll number (institution_id)
            query = query.filter(or_(User.full_name.ilike(f'%{search_query}%'), User.institution_id.ilike(f'%{search_query}%')))
        return query

    # 1. KPIs
    # Total Students in Dept
    total_students = User.query.filter_by(role='student', department=dept).count()
    
    # Participating Students
    part_q = db.session.query(distinct(StudentActivity.student_id))
    part_q = apply_hod_filters(part_q)
    total_participating = part_q.count()

    # Total Certificates (filtered)
    cert_q = db.session.query(func.count(StudentActivity.id))
    cert_q = apply_hod_filters(cert_q)
    total_certificates = cert_q.scalar() or 0
    
    # Status Breakdown
    status_stats = db.session.query(
        StudentActivity.status, func.count(StudentActivity.id)
    ).select_from(StudentActivity)
    status_stats = apply_hod_filters(status_stats).group_by(StudentActivity.status).all()
    status_counts = {s: c for s, c in status_stats}
    
    # Activity Type Breakdown (Chart)
    type_stats = db.session.query(
        ActivityType.name, func.count(StudentActivity.id)
    ).select_from(StudentActivity).outerjoin(ActivityType)
    type_stats = apply_hod_filters(type_stats).group_by(ActivityType.name).all()
    
    # Batch Breakdown (Chart)
    batch_stats = db.session.query(
        User.batch_year, func.count(StudentActivity.id)
    ).select_from(StudentActivity).join(User) # Already joined in filter, but explicit doesn't hurt if we didn't use filter
    # Actually apply_hod_filters joins User.
    # We need to construct query carefully.
    batch_q = db.session.query(User.batch_year, func.count(StudentActivity.id)).select_from(StudentActivity)
    batch_q = apply_hod_filters(batch_q).group_by(User.batch_year)
    batch_stats = batch_q.all()

    # Monthly Trend (Last 12 Months) - HOD only
    trend_stats = db.session.query(
        func.extract('year', StudentActivity.issue_date).label('year'),
        func.extract('month', StudentActivity.issue_date).label('month'),
        func.count(StudentActivity.id)
    ).select_from(StudentActivity)
    trend_stats = apply_hod_filters(trend_stats).group_by('year', 'month').order_by('year', 'month').all()

    # 2. Student Participation Table
    # Student Name, Roll No, Batch, Total Certs, Approved Certs, Last Activity Date
    # We need to query Users then join Activities? Or aggregate from Activities?
    # Listing ALL students including 0 certs might be heavy if many students. 
    # Prompt says "Student participation table". Usually implies those who participated OR all. 
    # "Total students" card implies we know total. Table usually shows relevant ones.
    # Let's show students who match the filter (so if searching "Smith", show Smith).
    # If no search, maybe paginated? For MVP, let's show top 50 or those with activities.
    # But HOD wants to see "students in their department". 
    # Let's query Users in Dept, then outerjoin activities?
    # Filters (date, status) apply to activities. If filtering by "Approved", only count Approved certs.
    
    # Subquery for counts per student based on current filters?
    # This is complex in ORM. 
    # Alternative: Query Activities, group by Student. 
    # This excludes students with 0 matching activities.
    
    # HOD Table 1: Student Participation (Students with activities matching filters)
    student_stats_q = db.session.query(
        User.id,
        User.full_name,
        User.institution_id,
        User.batch_year,
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved_certs'),
        func.max(StudentActivity.issue_date).label('last_activity')
    ).select_from(User).join(StudentActivity, User.id == StudentActivity.student_id)
    
    # Re-apply filters manually because apply_hod_filters assumes StudentActivity base
    student_stats_q = student_stats_q.filter(User.department == dept)
    
    if activity_type_id:
        student_stats_q = student_stats_q.filter(StudentActivity.activity_type_id == activity_type_id)
    if batch_year:
        student_stats_q = student_stats_q.filter(User.batch_year == batch_year)
    if start_date:
        student_stats_q = student_stats_q.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        student_stats_q = student_stats_q.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if status_filter:
        student_stats_q = student_stats_q.filter(StudentActivity.status == status_filter)
    if search_query:
        student_stats_q = student_stats_q.filter(or_(User.full_name.ilike(f'%{search_query}%'), User.institution_id.ilike(f'%{search_query}%')))
        
    student_stats = student_stats_q.group_by(User.id).all()

    # 3. Activity Overview Table
    # Title, Type, Organizer, Total Participants, Status Counts, Date Range
    # Group by Title? Titles can be duplicates. Verify prompt: "activity_title... total participants". 
    # This implies grouping by title.
    activity_overview_q = db.session.query(
        StudentActivity.title,
        func.coalesce(ActivityType.name, StudentActivity.custom_category).label('type_name'),
        StudentActivity.organizer,
        func.count(distinct(StudentActivity.student_id)).label('participants'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved_count'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending_count'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected_count'),
        func.min(StudentActivity.issue_date).label('start_date'),
        func.max(StudentActivity.issue_date).label('end_date')
    ).select_from(StudentActivity).outerjoin(ActivityType)
    
    activity_overview_q = apply_hod_filters(activity_overview_q)
    activity_overview = activity_overview_q.group_by(StudentActivity.title, 'type_name', StudentActivity.organizer).all()

    # Dropdown Options
    activity_types = ActivityType.query.all()
    batches = db.session.query(User.batch_year).filter(User.department == dept, User.batch_year != None).distinct().all()
    batches = [b[0] for b in batches]

    return render_template('hod_stats.html',
        total_students=total_students,
        total_certificates=total_certificates,
        total_participating=total_participating,
        status_counts=status_counts,
        type_stats=type_stats,
        batch_stats=batch_stats,
        trend_stats=trend_stats,
        student_stats=student_stats,
        activity_overview=activity_overview,
        activity_types=activity_types,
        batches=batches
    )

@bp.route('/hod/stats/export-certificates')
@role_required('faculty')
def hod_export_certificates():
    if current_user.position != 'hod': abort(403)
    
    # Re-apply filters logic
    dept = current_user.department
    query = db.session.query(
        User.full_name, User.institution_id, User.batch_year, User.department,
        StudentActivity.title, ActivityType.name, StudentActivity.organizer,
        StudentActivity.issue_date, StudentActivity.status, StudentActivity.approved_at,
        User.full_name.label('verifier_name') # Placeholder, need join with Faculty
    ).join(User, StudentActivity.student_id == User.id).outerjoin(ActivityType)
    
    # TODO: Join verifier
    # We need aliased join for verifier
    from sqlalchemy.orm import aliased
    Verifier = aliased(User)
    query = query.outerjoin(Verifier, StudentActivity.faculty_id == Verifier.id)
    # Fix select to use Verifier.full_name
    query = query.add_columns(Verifier.full_name.label('verified_by'))

    # Filters (Copy-paste logic from stats or refactor... sticking to inline for speed)
    activity_type_id = request.args.get('activity_type')
    batch_year = request.args.get('batch_year')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    status_filter = request.args.get('status')
    search_query = request.args.get('search')

    query = query.filter(User.department == dept)
    if activity_type_id: query = query.filter(StudentActivity.activity_type_id == activity_type_id)
    if batch_year: query = query.filter(User.batch_year == batch_year)
    if start_date: query = query.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date: query = query.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if status_filter: query = query.filter(StudentActivity.status == status_filter)
    if search_query: query = query.filter(or_(User.full_name.ilike(f'%{search_query}%'), User.institution_id.ilike(f'%{search_query}%')))

    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'Roll No', 'Batch', 'Department', 'Title', 'Type', 'Organizer', 'Issue Date', 'Status', 'Approved At', 'Verifier'])
    
    rows = query.all()
    for r in rows:
        # r is a tuple due to add_columns logic sometimes, check structure
        # query structure: [User fields..., Activity fields..., VerifiedBy]
        # Actually sqlalchemy returns a KeyedTuple equivalent
        cw.writerow([
            r.full_name, r.institution_id, r.batch_year, r.department,
            r.title, r.name or 'Other', r.organizer,
            r.issue_date, r.status, r.approved_at, r.verified_by
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=hod_certificates.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@bp.route('/hod/stats/export-students')
@role_required('faculty')
def hod_export_students():
    if current_user.position != 'hod': abort(403)
    dept = current_user.department
    
    # Same logic as Student Participation Table
    student_stats_q = db.session.query(
        User.full_name, User.institution_id, User.batch_year,
        func.count(StudentActivity.id).label('total'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved'),
        func.max(StudentActivity.issue_date).label('last_activity')
    ).select_from(User).join(StudentActivity, User.id == StudentActivity.student_id)
    
    # Filters
    activity_type_id = request.args.get('activity_type')
    batch_year = request.args.get('batch_year')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    status_filter = request.args.get('status')
    search_query = request.args.get('search')
    
    student_stats_q = student_stats_q.filter(User.department == dept)
    if activity_type_id: student_stats_q = student_stats_q.filter(StudentActivity.activity_type_id == activity_type_id)
    if batch_year: student_stats_q = student_stats_q.filter(User.batch_year == batch_year)
    if start_date: student_stats_q = student_stats_q.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date: student_stats_q = student_stats_q.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if status_filter: student_stats_q = student_stats_q.filter(StudentActivity.status == status_filter)
    if search_query: student_stats_q = student_stats_q.filter(or_(User.full_name.ilike(f'%{search_query}%'), User.institution_id.ilike(f'%{search_query}%')))
    
    rows = student_stats_q.group_by(User.id).all()
    
    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'Roll No', 'Batch', 'Total Certificates', 'Approved Certificates', 'Last Activity Date'])
    for r in rows:
        cw.writerow([r.full_name, r.institution_id, r.batch_year, r.total, r.approved, r.last_activity])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=hod_students_summary.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@bp.route('/hod/students')
@role_required('faculty')
def hod_students():
    """Full department student list with advanced filters and pagination."""
    if current_user.position != 'hod': abort(403)
    
    dept = current_user.department
    if not dept:
        flash("Department not assigned.", "error")
        return redirect(url_for('main.index'))
    
    # Filters
    search = request.args.get('search', '').strip()
    batch_filter = request.args.get('batch_year', '')
    min_approved = request.args.get('min_approved', type=int)
    zero_participation = request.args.get('zero_participation', '') == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    # Alias for Student
    Student = aliased(User)
    
    # Base: All students in dept
    base_q = User.query.filter_by(role='student', department=dept)
    
    if search:
        base_q = base_q.filter(
            or_(
                User.full_name.ilike(f'%{search}%'),
                User.institution_id.ilike(f'%{search}%')
            )
        )
    if batch_filter:
        base_q = base_q.filter(User.batch_year == batch_filter)
    
    # Subquery for cert counts
    cert_counts = db.session.query(
        StudentActivity.student_id,
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved_certs'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected_certs'),
        func.max(StudentActivity.updated_at).label('last_activity')
    ).group_by(StudentActivity.student_id).subquery()
    
    # Join students with cert counts
    students_with_stats = db.session.query(
        User.id,
        User.full_name,
        User.institution_id,
        User.batch_year,
        func.coalesce(cert_counts.c.total_certs, 0).label('total_certs'),
        func.coalesce(cert_counts.c.approved_certs, 0).label('approved_certs'),
        func.coalesce(cert_counts.c.rejected_certs, 0).label('rejected_certs'),
        cert_counts.c.last_activity
    ).outerjoin(cert_counts, User.id == cert_counts.c.student_id)\
     .filter(User.role == 'student', User.department == dept)
    
    # Apply search and batch filters
    if search:
        students_with_stats = students_with_stats.filter(
            or_(
                User.full_name.ilike(f'%{search}%'),
                User.institution_id.ilike(f'%{search}%')
            )
        )
    if batch_filter:
        students_with_stats = students_with_stats.filter(User.batch_year == batch_filter)
    
    # Apply min_approved filter
    if min_approved is not None:
        students_with_stats = students_with_stats.having(
            func.coalesce(cert_counts.c.approved_certs, 0) >= min_approved
        )
    
    # Apply zero_participation filter
    if zero_participation:
        students_with_stats = students_with_stats.having(
            func.coalesce(cert_counts.c.approved_certs, 0) == 0
        )
    
    # Group and order
    students_with_stats = students_with_stats.group_by(
        User.id, User.full_name, User.institution_id, User.batch_year,
        cert_counts.c.total_certs, cert_counts.c.approved_certs, 
        cert_counts.c.rejected_certs, cert_counts.c.last_activity
    ).order_by(User.institution_id)
    
    # Pagination
    total = students_with_stats.count()
    students = students_with_stats.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Top 5 students by approved certs
    top_students = db.session.query(
        User.full_name,
        User.institution_id,
        func.count(StudentActivity.id).label('approved_count')
    ).join(StudentActivity, StudentActivity.student_id == User.id)\
     .filter(User.department == dept, StudentActivity.status.in_(['faculty_verified', 'auto_verified']))\
     .group_by(User.id, User.full_name, User.institution_id)\
     .order_by(desc('approved_count'))\
     .limit(5).all()
    
    # Get batches for filter dropdown
    batches = db.session.query(User.batch_year).filter(
        User.role == 'student', User.department == dept, User.batch_year.isnot(None)
    ).distinct().order_by(User.batch_year.desc()).all()
    batches = [b[0] for b in batches]
    
    # Stats
    total_students = User.query.filter_by(role='student', department=dept).count()
    students_with_certs = db.session.query(func.count(distinct(StudentActivity.student_id)))\
        .join(User, StudentActivity.student_id == User.id)\
        .filter(User.department == dept, StudentActivity.status.in_(['faculty_verified', 'auto_verified'])).scalar() or 0
    participation_rate = round(students_with_certs / total_students * 100, 1) if total_students > 0 else 0
    
    return render_template('hod_students.html',
        students=students,
        top_students=top_students,
        batches=batches,
        total_students=total_students,
        students_with_certs=students_with_certs,
        participation_rate=participation_rate,
        page=page,
        total_pages=total_pages,
        total_results=total
    )

@bp.route('/incharge/dashboard')
@role_required('faculty')
def incharge_dashboard():
    """Dashboard for Activity In-Charges showing their managed activities."""
    if current_user.position != 'activity_incharge': abort(403)
    
    dept = current_user.department
    
    # Get activity types assigned to this in-charge
    # For now, we'll show all activity types the in-charge is associated with
    # This could be refined with an assigned_activity_type_id on User model
    assigned_types = ActivityType.query.all()  # Or filter by assigned_user_id if exists
    
    # For each activity type, compute stats
    activities_data = []
    for at in assigned_types:
        # Get all submissions for this type in the in-charge's dept
        Student = aliased(User)
        base_q = db.session.query(StudentActivity).join(Student, StudentActivity.student_id == Student.id).filter(
            Student.department == dept,
            StudentActivity.activity_type_id == at.id
        )
        
        total_submissions = base_q.count()
        if total_submissions == 0:
            continue  # Skip empty activity types
            
        verified = base_q.filter(StudentActivity.status.in_(['faculty_verified', 'auto_verified'])).count()
        pending = base_q.filter(StudentActivity.status == 'pending').count()
        rejected = base_q.filter(StudentActivity.status == 'rejected').count()
        
        # Unique students who submitted
        unique_students = db.session.query(func.count(distinct(StudentActivity.student_id))).join(
            Student, StudentActivity.student_id == Student.id
        ).filter(Student.department == dept, StudentActivity.activity_type_id == at.id).scalar() or 0
        
        activities_data.append({
            'id': at.id,
            'name': at.name,
            'total_submissions': total_submissions,
            'verified': verified,
            'pending': pending,
            'rejected': rejected,
            'unique_students': unique_students,
            'approval_rate': round(verified / total_submissions * 100, 1) if total_submissions > 0 else 0
        })
    
    # Sort by total_submissions descending
    activities_data.sort(key=lambda x: x['total_submissions'], reverse=True)
    
    # Overall stats
    total_students_engaged = db.session.query(func.count(distinct(StudentActivity.student_id))).join(
        User, StudentActivity.student_id == User.id
    ).filter(User.department == dept).scalar() or 0
    
    total_submissions = sum(a['total_submissions'] for a in activities_data)
    total_verified = sum(a['verified'] for a in activities_data)
    
    # Lowest participation types (for insights)
    lowest_participation = sorted(activities_data, key=lambda x: x['unique_students'])[:3] if activities_data else []
    
    return render_template('incharge_dashboard.html',
        activities=activities_data,
        total_students_engaged=total_students_engaged,
        total_submissions=total_submissions,
        total_verified=total_verified,
        lowest_participation=lowest_participation
    )

@bp.route('/insights')
@role_required('faculty', 'hod', 'admin')
def insights_page():
    """
    Insights & Analytics page with drill-down capabilities.
    Section A, B, C combined.
    """
    # Get departments list for admin filter
    departments = []
    if current_user.role == 'admin':
        depts = db.session.query(User.department).filter(
            User.role == 'student',
            User.department.isnot(None)
        ).distinct().all()
        departments = [d[0] for d in depts if d[0]]
    
    return render_template('insights.html', departments=departments)

@bp.route('/admin/stats')

@role_required('admin')
def admin_stats():
    # Filters
    dept = request.args.get('department')
    activity_type_id = request.args.get('activity_type')
    batch_year = request.args.get('batch_year')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    status_filter = request.args.get('status')

    def apply_admin_filters(query):
        # Always join User for dept/batch filtering availability
        # Use outerjoin if not filtering by user fields to include orphan activities? 
        # No, activities must have a student. Inner join is safe.
        query = query.join(User, StudentActivity.student_id == User.id)
        
        if dept:
            query = query.filter(User.department == dept)
        if activity_type_id:
            query = query.filter(StudentActivity.activity_type_id == activity_type_id)
        if batch_year:
            query = query.filter(User.batch_year == batch_year)
        if start_date:
            query = query.filter(StudentActivity.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(StudentActivity.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
        if status_filter:
            query = query.filter(StudentActivity.status == status_filter)
        return query

    # 1. Global KPIs
    # Total Students
    student_q = User.query.filter_by(role='student')
    if dept:
        student_q = student_q.filter_by(department=dept)
    if batch_year:
        student_q = student_q.filter_by(batch_year=batch_year)
    total_students = student_q.count()

    # Total Certificates & Participating
    base_q = db.session.query(StudentActivity)
    base_q = apply_admin_filters(base_q)
    total_certificates = base_q.count()
    
    # Participating Students (distinct)
    part_q = db.session.query(func.current_date()).select_from(StudentActivity) # dummy select
    part_q = apply_admin_filters(db.session.query(distinct(StudentActivity.student_id)))
    participating_students = part_q.count()

    # Unique Activities (Distinct Title + Organizer + Date)
    # This represents distinct "Events" properly
    unique_activities_q = db.session.query(StudentActivity.title, StudentActivity.organizer, StudentActivity.issue_date)
    unique_activities_q = apply_admin_filters(unique_activities_q)
    total_unique_activities = unique_activities_q.distinct().count()

    # 2. Status Breakdown
    status_stats = db.session.query(
        StudentActivity.status, func.count(StudentActivity.id)
    ).select_from(StudentActivity)
    status_stats = apply_admin_filters(status_stats).group_by(StudentActivity.status).all()
    status_counts = {s: c for s, c in status_stats}

    # 6. Department Overview Table
    # Dept Name, Total Students, Participating Students, Total Certs, Approved/Pending/Rejected
    # Use existing dept_stats but add status breakdown per dept? 
    # Or query separately. 
    # Current dept_stats has cert_count and student_count. 
    # Let's clean up dept_stats to be more comprehensive.
    
    dept_overview_q = db.session.query(
        User.department,
        func.count(distinct(User.id)).label('total_students'),
        func.count(distinct(case((StudentActivity.id != None, StudentActivity.student_id), else_=None))).label('participating_students'),
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
    ).select_from(User).outerjoin(StudentActivity, User.id == StudentActivity.student_id)
    
    # Filter logic for Dept Overview? 
    # Usually global, but if date filters applied, should reflect in counts.
    if start_date:
        dept_overview_q = dept_overview_q.filter(or_(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date(), StudentActivity.id == None))
    if end_date:
        dept_overview_q = dept_overview_q.filter(or_(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date(), StudentActivity.id == None))
    
    # Group by Dept
    # Group by Dept
    dept_overview = dept_overview_q.group_by(User.department).all()

    # Reuse dept_overview for dept_stats (charts) or re-query if needed. 
    # Let's map dept_overview for charts: {department, cert_count, student_count}
    # Or just use raw dept_overview in template if adapted.
    # But template likely expects `dept_stats` to have cert_count/student_count attributes or tuple.
    # dept_overview is list of named tuples-like results.
    # Let's alias it for simplicity or make a compatibility object.
    # Actually, let's just re-run the simple dept_stats query for charts to be safe and clear.
    dept_stats = db.session.query(
        User.department, 
        func.count(StudentActivity.id).label('cert_count'),
        func.count(distinct(StudentActivity.student_id)).label('student_count')
    ).select_from(StudentActivity)
    dept_stats = apply_admin_filters(dept_stats).group_by(User.department).all()

    # 4. Activity Type Breakdown
    type_stats = db.session.query(
        ActivityType.name, func.count(StudentActivity.id)
    ).select_from(StudentActivity).outerjoin(ActivityType)
    type_stats = apply_admin_filters(type_stats).group_by(ActivityType.name).all()

    # 5. Monthly Trend (Last 12 Months)
    trend_stats = db.session.query(
        func.extract('year', StudentActivity.issue_date).label('year'),
        func.extract('month', StudentActivity.issue_date).label('month'),
        func.count(StudentActivity.id)
    ).select_from(StudentActivity)
    trend_stats = apply_admin_filters(trend_stats).group_by('year', 'month').order_by('year', 'month').all()

    # 7. Detailed Certificates Table (Paginated ideally, but MVP all)
    # Student Name, Roll, Dept, Batch, Title, Type, Organizer, Issue Date, Status, Verifier
    detailed_certs_q = db.session.query(
        User.full_name, User.institution_id, User.department, User.batch_year, 
        StudentActivity.title, func.coalesce(ActivityType.name, StudentActivity.custom_category).label('type_name'),
        StudentActivity.organizer, StudentActivity.issue_date, StudentActivity.status,
        StudentActivity.approved_at
    ).select_from(StudentActivity).join(User, StudentActivity.student_id == User.id).outerjoin(ActivityType)
    
    # Manually apply filters to avoid duplicate join from apply_admin_filters
    if dept: detailed_certs_q = detailed_certs_q.filter(User.department == dept)
    if activity_type_id: detailed_certs_q = detailed_certs_q.filter(StudentActivity.activity_type_id == activity_type_id)
    if batch_year: detailed_certs_q = detailed_certs_q.filter(User.batch_year == batch_year)
    if start_date: detailed_certs_q = detailed_certs_q.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date: detailed_certs_q = detailed_certs_q.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if status_filter: detailed_certs_q = detailed_certs_q.filter(StudentActivity.status == status_filter)

    if request.args.get('search'):
        search = request.args.get('search')
        detailed_certs_q = detailed_certs_q.filter(or_(
            User.full_name.ilike(f'%{search}%'), 
            User.institution_id.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%')
        ))
    
    detailed_certs = detailed_certs_q.order_by(StudentActivity.created_at.desc()).limit(200).all() # Limit for display

    # Dropdowns
    departments = db.session.query(User.department).filter(User.department != None).distinct().all()
    departments = [d[0] for d in departments]
    activity_types = ActivityType.query.all()
    batches = db.session.query(User.batch_year).filter(User.batch_year != None).distinct().all()
    batches = [b[0] for b in batches]

    return render_template('admin_stats.html',
        total_students=total_students,
        total_certificates=total_certificates,
        participating_students=participating_students,
        total_unique_activities=total_unique_activities, # New
        status_counts=status_counts,
        dept_stats=dept_stats,
        dept_overview=dept_overview, # New
        detailed_certs=detailed_certs, # New
        type_stats=type_stats,
        trend_stats=trend_stats,
        departments=departments,
        activity_types=activity_types,
        batches=batches
    )

@bp.route('/admin/stats/export-certificates')
@role_required('admin')
def admin_export_certificates():
    # Re-implement filters logic (DRY would be better but keeping simple for now)
    dept = request.args.get('department')
    activity_type_id = request.args.get('activity_type')
    batch_year = request.args.get('batch_year')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    status_filter = request.args.get('status')
    search = request.args.get('search')

    query = db.session.query(
        User.full_name, User.institution_id, User.department, User.batch_year,
        StudentActivity.title, func.coalesce(ActivityType.name, StudentActivity.custom_category).label('type_name'),
        StudentActivity.organizer, StudentActivity.issue_date, StudentActivity.status, StudentActivity.approved_at
    ).select_from(StudentActivity).join(User, StudentActivity.student_id == User.id).outerjoin(ActivityType)

    if dept: query = query.filter(User.department == dept)
    if activity_type_id: query = query.filter(StudentActivity.activity_type_id == activity_type_id)
    if batch_year: query = query.filter(User.batch_year == batch_year)
    if start_date: query = query.filter(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date: query = query.filter(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if status_filter: query = query.filter(StudentActivity.status == status_filter)
    if search: query = query.filter(or_(User.full_name.ilike(f'%{search}%'), User.institution_id.ilike(f'%{search}%')))

    results = query.all()

    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'ID', 'Department', 'Batch', 'Activity Title', 'Type', 'Organizer', 'Issue Date', 'Status', 'Approved Date'])
    
    for row in results:
        cw.writerow([
            row.full_name, row.institution_id, row.department, row.batch_year,
            row.title, row.type_name, row.organizer,
            row.issue_date, row.status, row.approved_at
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=admin_certificates.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@bp.route('/admin/stats/export-departments')
@role_required('admin')
def admin_export_departments():
    # Similar to Dept Overview Query
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = db.session.query(
        User.department,
        func.count(distinct(User.id)).label('total_students'),
        func.count(distinct(case((StudentActivity.id != None, StudentActivity.student_id), else_=None))).label('participating'),
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved')
    ).select_from(User).outerjoin(StudentActivity, User.id == StudentActivity.student_id)
    
    if start_date: query = query.filter(or_(StudentActivity.issue_date >= datetime.strptime(start_date, '%Y-%m-%d').date(), StudentActivity.id == None))
    if end_date: query = query.filter(or_(StudentActivity.issue_date <= datetime.strptime(end_date, '%Y-%m-%d').date(), StudentActivity.id == None))
    
    rows = query.group_by(User.department).all()
    
    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Department', 'Total Students', 'Participating', 'Total Certificates', 'Approved Certificates'])
    for r in rows:
        cw.writerow([r.department, r.total_students, r.participating, r.total_certs, r.approved])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=admin_departments.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@bp.route('/admin/stats/students')
@role_required('admin')
def admin_student_stats():
    # Filters
    dept = request.args.get('department')
    batch_year = request.args.get('batch_year')
    min_certs = request.args.get('min_certs', type=int)
    max_certs = request.args.get('max_certs', type=int)
    search = request.args.get('search')
    
    query = db.session.query(
        User.full_name, User.institution_id, User.department, User.batch_year,
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved_certs'),
        func.max(StudentActivity.issue_date).label('last_activity')
    ).select_from(User).outerjoin(StudentActivity, User.id == StudentActivity.student_id)
    # Using outerjoin to include 0-cert students
    
    query = query.filter(User.role == 'student')
    
    if dept: query = query.filter(User.department == dept)
    if batch_year: query = query.filter(User.batch_year == batch_year)
    if search: query = query.filter(or_(User.full_name.ilike(f'%{search}%'), User.institution_id.ilike(f'%{search}%')))
    
    # Group by student
    query = query.group_by(User.id)
    
    # Having clause for min/max certs
    if min_certs is not None: query = query.having(func.count(StudentActivity.id) >= min_certs)
    if max_certs is not None: query = query.having(func.count(StudentActivity.id) <= max_certs)
    
    students = query.all()
    
    # Dropdowns 
    departments = db.session.query(User.department).filter(User.department != None).distinct().all()
    departments = [d[0] for d in departments]
    batches = db.session.query(User.batch_year).filter(User.batch_year != None).distinct().all()
    batches = [b[0] for b in batches]
    
    return render_template('admin_student_stats.html', 
        students=students,
        departments=departments,
        batches=batches
    )

@bp.route('/admin/stats/export-students')
@role_required('admin')
def admin_export_students():
     # Same logic as admin_student_stats but export
    dept = request.args.get('department')
    batch_year = request.args.get('batch_year')
    min_certs = request.args.get('min_certs', type=int)
    
    query = db.session.query(
        User.full_name, User.institution_id, User.department, User.batch_year,
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved_certs'),
        func.max(StudentActivity.issue_date).label('last_activity')
    ).select_from(User).outerjoin(StudentActivity, User.id == StudentActivity.student_id).filter(User.role == 'student')
    
    if dept: query = query.filter(User.department == dept)
    if batch_year: query = query.filter(User.batch_year == batch_year)
    
    query = query.group_by(User.id)
    if min_certs: query = query.having(func.count(StudentActivity.id) >= min_certs)
    
    rows = query.all()
    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'ID', 'Department', 'Batch', 'Total', 'Approved', 'Last Activity'])
    for r in rows:
        cw.writerow([r.full_name, r.institution_id, r.department, r.batch_year, r.total_certs, r.approved_certs, r.last_activity])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=admin_students.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@bp.route('/faculty/review/<int:act_id>')
@role_required('faculty', 'admin')
def review_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    # Optional: Check if assigned to this faculty
    if current_user.role == 'faculty' and activity.assigned_reviewer_id and activity.assigned_reviewer_id != current_user.id:
         flash("You are not assigned to review this activity.", "warning")
         return redirect(url_for('main.faculty_dashboard'))
         
    return render_template('faculty_review.html', activity=activity)

@bp.route('/faculty/approve/<int:act_id>', methods=['POST'])
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
    return redirect(url_for('main.faculty_dashboard'))

@bp.route('/faculty/reject/<int:act_id>', methods=['POST'])
@role_required('faculty', 'admin')
def reject_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    comment = request.form.get('faculty_comment', '')
    
    activity.status = 'rejected'
    activity.faculty_id = current_user.id
    activity.faculty_comment = comment
    
    db.session.commit()
    flash(f"Activity #{act_id} Rejected.")
    return redirect(url_for('main.faculty_dashboard'))

# --- Admin Routes ---

@bp.route('/admin/users')
@role_required('admin')
def admin_users():
    search_query = request.args.get('search')
    query = User.query
    
    if search_query:
        query = query.filter(or_(
            User.full_name.ilike(f'%{search_query}%'),
            User.email.ilike(f'%{search_query}%'),
            User.institution_id.ilike(f'%{search_query}%'),
            User.department.ilike(f'%{search_query}%')
        ))
        
    users = query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users, search_query=search_query)

@bp.route('/faculty/stats')
@role_required('faculty')
def faculty_stats():
    dept = current_user.department
    if not dept:
        flash("Department not assigned.", "error")
        return redirect(url_for('main.index'))

    # --- 1. KPIs ---
    # Total Students
    total_students = User.query.filter_by(role='student', department=dept).count()
    
    # Alias for Student User
    Student = aliased(User)

    # Base Query for Dept Activities
    # Explicitly join StudentActivity -> Student (User)
    base_q = db.session.query(StudentActivity).join(Student, StudentActivity.student_id == Student.id).filter(Student.department == dept)
    
    # Total Certificates
    total_certs = base_q.count()
    
    # Status Breakdown
    status_stats = db.session.query(
        StudentActivity.status, func.count(StudentActivity.id)
    ).join(Student, StudentActivity.student_id == Student.id).filter(Student.department == dept).group_by(StudentActivity.status).all()
    status_counts = {s: c for s, c in status_stats}
    
    # Unique Events (Implicit)
    # Event = (Title, Organizer, IssueDate, TypeID)
    unique_events_q = db.session.query(
        StudentActivity.title, 
        StudentActivity.organizer, 
        StudentActivity.issue_date,
        StudentActivity.activity_type_id
    ).join(Student, StudentActivity.student_id == Student.id).filter(Student.department == dept)
    
    total_events = unique_events_q.distinct().count()

    # --- 2. Recent Activity Timeline ---
    recent_activities = base_q.order_by(StudentActivity.updated_at.desc()).limit(10).all()

    # --- 3. Events List (Aggregated) ---
    # Group by Event -> Count Participants, Count Verified
    events_list_q = db.session.query(
        StudentActivity.title,
        StudentActivity.organizer,
        StudentActivity.issue_date,
        ActivityType.name.label('type_name'),
        func.count(StudentActivity.id).label('participant_count'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('verified_count')
    ).join(Student, StudentActivity.student_id == Student.id).outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)\
     .filter(Student.department == dept)\
     .group_by(StudentActivity.title, StudentActivity.organizer, StudentActivity.issue_date, ActivityType.name)\
     .order_by(StudentActivity.issue_date.desc())
     
    events_list = events_list_q.all()

    return render_template('faculty_stats.html',
        total_students=total_students,
        total_certs=total_certs,
        total_events=total_events,
        status_counts=status_counts,
        recent_activities=recent_activities,
        events_list=events_list
    )
@bp.route('/admin/users/create', methods=['POST'])
@role_required('admin')
def admin_create_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    position = request.form.get('position')
    full_name = request.form.get('full_name')
    department = request.form.get('department')
    institution_id = request.form.get('institution_id')
    
    if not full_name:
         flash('Full Name is required.')
         return redirect(url_for('main.admin_users'))
         
    if role == 'faculty':
        if not department or not institution_id:
            flash('Faculty must have Department and Institution ID (Employee ID).')
            return redirect(url_for('main.admin_users'))
            
    if role == 'student':
        if not department:
            flash('Students must have a Department.')
            return redirect(url_for('main.admin_users'))
        if not institution_id:
            flash('Students must have an Institution ID (Roll Number).')
            return redirect(url_for('main.admin_users'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already registered.')
        return redirect(url_for('main.admin_users'))
    
    if institution_id and User.query.filter_by(institution_id=institution_id).first():
        flash('Institution ID (ID/RollNo) must be unique.')
        return redirect(url_for('main.admin_users'))
        
    new_user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        position=position,
        full_name=full_name,
        department=department,
        institution_id=institution_id
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f'User {email} created successfully.')
    
    return redirect(url_for('main.admin_users'))

@bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        role = request.form.get('role')
        position = request.form.get('position')
        department = request.form.get('department')
        institution_id = request.form.get('institution_id')
        password = request.form.get('password')
        is_active = request.form.get('is_active') == 'on'
        
        if not full_name:
            flash('Full Name is required.')
            return render_template('admin_user_edit.html', user=user)

        if role in ['faculty', 'student']:
            if not department or not institution_id:
                 flash(f'{role.capitalize()} requires Department and Institution ID.')
                 return render_template('admin_user_edit.html', user=user)
        
        existing_email = User.query.filter(User.email == email, User.id != user_id).first()
        if existing_email:
            flash('Email already in use.')
            return render_template('admin_user_edit.html', user=user)
            
        if institution_id:
            existing_id = User.query.filter(User.institution_id == institution_id, User.id != user_id).first()
            if existing_id:
                flash('Institution ID already in use.')
                return render_template('admin_user_edit.html', user=user)
        
        if user.role == 'admin' and user.email == 'admin@example.com':
             if not is_active:
                 flash("Cannot deactivate default admin.")
                 is_active = True
             if role != 'admin':
                 flash("Cannot change role of default admin.")
                 role = 'admin'

        user.full_name = full_name
        user.email = email
        user.role = role
        user.position = position
        user.department = department
        user.institution_id = institution_id
        user.is_active = is_active
        
        if password:
             user.password_hash = generate_password_hash(password)
        
        db.session.commit()
        flash('User updated successfully.')
        return redirect(url_for('main.admin_users'))

    return render_template('admin_user_edit.html', user=user)


@bp.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@role_required('admin')
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin' and user.email == 'admin@example.com':
        flash("Cannot deactivate default admin.")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = "Activated" if user.is_active else "Deactivated"
        flash(f"User {user.email} {status}.")
    return redirect(url_for('main.admin_users'))

@bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("Cannot delete your own admin account.")
        return redirect(url_for('main.admin_users'))
        
    if user.role == 'admin' and user.email == 'admin@example.com':
        flash("Cannot delete default admin.")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} deleted.")
    return redirect(url_for('main.admin_users'))

# --- NAAC / Admin Analytics ---

@bp.route('/admin/naac-dashboard')
@role_required('admin')
def admin_naac_dashboard():
    # 1. Filters
    dept = request.args.get('department')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base Query Helper
    def apply_filters(query, model=StudentActivity):
        if start_date:
            query = query.filter(model.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(model.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
        if dept:
            # Join with User (student) to filter by department
            query = query.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
        return query

    # 2. Activity Type Stats (Aggregated)
    # Join ActivityType (outer) to get name, or fallback to custom_category
    base_activity_q = db.session.query(
        func.coalesce(ActivityType.name, StudentActivity.custom_category).label('activity_name'),
        func.count(StudentActivity.id).label('total'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
        func.sum(case((StudentActivity.status == 'auto_verified', 1), else_=0)).label('auto_verified'),
        func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('faculty_verified'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
    ).select_from(StudentActivity).outerjoin(ActivityType).group_by(func.coalesce(ActivityType.name, StudentActivity.custom_category))

    base_activity_q = apply_filters(base_activity_q)
    type_stats_rows = base_activity_q.all()

    # Prep Data for Chart.js
    type_labels = [row.activity_name for row in type_stats_rows]
    data_pending = [int(row.pending) for row in type_stats_rows]
    data_auto = [int(row.auto_verified) for row in type_stats_rows]
    data_faculty = [int(row.faculty_verified) for row in type_stats_rows]
    data_rejected = [int(row.rejected) for row in type_stats_rows]
    
    # 3. Overall Counts
    total_q = db.session.query(func.count(StudentActivity.id))
    total_q = apply_filters(total_q)
    total_activities = total_q.scalar() or 0

    verified_q = db.session.query(func.count(StudentActivity.id)).filter(or_(StudentActivity.status == 'faculty_verified', StudentActivity.status == 'auto_verified'))
    verified_q = apply_filters(verified_q)
    verified_count = verified_q.scalar() or 0

    verified_percentage = round((verified_count / total_activities * 100), 1) if total_activities > 0 else 0

    # 4. Student Participation
    participating_q = db.session.query(func.count(distinct(StudentActivity.student_id)))
    participating_q = apply_filters(participating_q)
    participating_students = participating_q.scalar() or 0

    total_students_q = db.session.query(func.count(User.id)).filter(User.role == 'student')
    if dept:
        total_students_q = total_students_q.filter(User.department == dept)
    total_students = total_students_q.scalar() or 0
    
    participation_percentage = round((participating_students / total_students * 100), 1) if total_students > 0 else 0

    # 5. MOOC Logic (Simple Str Check)
    mooc_keywords = ['MOOC', 'Course', 'Certificate', 'NPTEL', 'Coursera', 'Udemy', 'edX']
    mooc_cond = or_(*[func.coalesce(ActivityType.name, StudentActivity.custom_category).ilike(f'%{kw}%') for kw in mooc_keywords])
    
    mooc_q = db.session.query(func.count(StudentActivity.id)).outerjoin(ActivityType).filter(mooc_cond)
    mooc_q = apply_filters(mooc_q)
    mooc_count = mooc_q.scalar() or 0

    return render_template('admin_naac_dashboard.html',
        type_stats=type_stats_rows,
        type_labels=type_labels,
        data_pending=data_pending,
        data_auto=data_auto,
        data_faculty=data_faculty,
        data_rejected=data_rejected,
        total_activities=total_activities,
        verified_count=verified_count,
        verified_percentage=verified_percentage,
        participating_students=participating_students,
        total_students=total_students,
        participation_percentage=participation_percentage,
        mooc_count=mooc_count
    )

@bp.route('/admin/export-naac')
@role_required('admin')
def admin_export_naac():
    export_type = request.args.get('type')
    dept = request.args.get('department')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    def apply_filters(query):
        if start_date:
            query = query.filter(StudentActivity.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(StudentActivity.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
        if dept:
            query = query.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
        return query

    si = io.StringIO()
    cw = csv.writer(si)

    if export_type == 'activities_by_type':
        cw.writerow(['Activity Name', 'Total', 'Pending', 'Auto Verified', 'Faculty Verified', 'Rejected'])
        stats = db.session.query(
            func.coalesce(ActivityType.name, StudentActivity.custom_category).label('activity_name'),
            func.count(StudentActivity.id).label('total'),
            func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
            func.sum(case((StudentActivity.status == 'auto_verified', 1), else_=0)).label('auto_verified'),
            func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('faculty_verified'),
            func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
        ).select_from(StudentActivity).outerjoin(ActivityType).group_by(func.coalesce(ActivityType.name, StudentActivity.custom_category))
        
        if start_date:
            stats = stats.filter(StudentActivity.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            stats = stats.filter(StudentActivity.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
        if dept:
            stats = stats.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
            
        rows = stats.all()
        for r in rows:
            cw.writerow([r.activity_name, r.total, r.pending, r.auto_verified, r.faculty_verified, r.rejected])

    elif export_type == 'mooc_details':
        cw.writerow(['Student ID', 'Student Name', 'Activity', 'Title', 'Issuer', 'Date', 'Status'])
        mooc_keywords = ['MOOC', 'Course', 'Certificate', 'NPTEL', 'Coursera', 'Udemy', 'edX']
        mooc_cond = or_(*[func.coalesce(ActivityType.name, StudentActivity.custom_category).ilike(f'%{kw}%') for kw in mooc_keywords])
        
        q = db.session.query(StudentActivity).outerjoin(ActivityType).filter(mooc_cond)
        q = apply_filters(q) 
        
        activities = q.all()
        for act in activities:
            cw.writerow([
                act.student.institution_id, 
                act.student.full_name, 
                act.activity_type.name if act.activity_type else f"{act.custom_category} (Other)",
                act.title,
                act.issuer_name,
                act.start_date,
                act.status
            ])
            
    else:
        return abort(400, "Invalid export type")

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=naac_export_{export_type}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# --- Activity Type Routes ---

@bp.route('/admin/activity-types', methods=['GET', 'POST'])
@role_required('admin')
def admin_activity_types():
    if request.method == 'POST':
        name = request.form.get('name')
        faculty_id = request.form.get('faculty_id')
        description = request.form.get('description')
        
        if ActivityType.query.filter_by(name=name).first():
            flash('Activity Type already exists.')
        else:
            new_at = ActivityType(name=name, faculty_incharge_id=faculty_id, description=description)
            db.session.add(new_at)
            db.session.commit()
            flash('Activity Type created.')
        return redirect(url_for('main.admin_activity_types'))
    
    activity_types = ActivityType.query.all()
    faculty_users = User.query.filter_by(role='faculty').all()
    
    return render_template('admin_activity_types.html', activity_types=activity_types, faculty_users=faculty_users)

@bp.route('/admin/activity-types/<int:at_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_activity_type(at_id):
    at = ActivityType.query.get_or_404(at_id)
    
    if request.method == 'POST':
        at.name = request.form.get('name')
        at.faculty_incharge_id = request.form.get('faculty_id')
        at.description = request.form.get('description')
        
        existing = ActivityType.query.filter(ActivityType.name == at.name, ActivityType.id != at.id).first()
        if existing:
            flash(f"Activity Type '{at.name}' already exists.")
        else:
            db.session.commit()
            flash(f"Activity Type '{at.name}' updated.")
            return redirect(url_for('main.admin_activity_types'))
            
    faculty_users = User.query.filter(User.role.in_(['faculty', 'admin'])).all()
    return render_template('admin_activity_type_edit.html', activity_type=at, faculty_users=faculty_users)

@bp.route('/admin/activity-types/delete/<int:at_id>', methods=['POST'])
@role_required('admin')
def admin_delete_activity_type(at_id):
    at = ActivityType.query.get_or_404(at_id)
    db.session.delete(at)
    db.session.commit()
    flash('Activity Type deleted.')
    return redirect(url_for('main.admin_activity_types'))

# --- Portfolio Route ---

@bp.route('/student/portfolio')
@role_required('student')
def student_portfolio():
    activities = StudentActivity.query.filter_by(student_id=current_user.id).order_by(StudentActivity.created_at.desc()).all()
    return render_template('portfolio.html', activities=activities)


@bp.route('/student/portfolio.pdf')
@role_required('student')
def student_portfolio_pdf():
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

# --- Public Verification Route ---

@bp.route('/verify/<token>')
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
            if activity.certificate_hash and recomputed_hash == activity.certificate_hash:
                hash_match = True
    
    return render_template('verify_public.html', activity=activity, hash_match=hash_match, recomputed_hash=recomputed_hash)

# --- Enhanced Stats Routes ---

@bp.route('/faculty/event_participants')
@role_required('faculty', 'hod', 'admin')
def event_participants():
    # Identifiers for the "Implicit Event"
    title = request.args.get('title')
    organizer = request.args.get('organizer')
    issue_date_str = request.args.get('date') # YYYY-MM-DD
    
    if not title:
        flash("Event Title required.", "error")
        return redirect(url_for('main.faculty_stats'))

    # Determine Dept context
    if current_user.role == 'admin':
        dept = request.args.get('department') # Admin can see any dept
    else:
        dept = current_user.department

    if not dept:
         flash("Department context missing.", "error")
         return redirect(url_for('main.index'))

    # 1. Get All Students in Dept
    all_students = User.query.filter_by(role='student', department=dept).order_by(User.institution_id).all()
    
    # 2. Get Participants for this Event
    # Use Aliased Student
    Student = aliased(User)
    
    # Filter StudentActivity by Title, Organizer, Date (if provided)
    q = db.session.query(StudentActivity).join(Student, StudentActivity.student_id == Student.id).filter(Student.department == dept, StudentActivity.title == title)
    
    if organizer:
        q = q.filter(StudentActivity.organizer == organizer)
    if issue_date_str and issue_date_str != 'None':
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            q = q.filter(StudentActivity.issue_date == issue_date)
        except ValueError:
            pass # Ignore invalid date
            
    participants = q.all()
    
    # 3. Merge Data (Student -> Status)
    # Map student_id -> activity
    part_map = {p.student_id: p for p in participants}
    
    student_data = []
    for s in all_students:
        act = part_map.get(s.id)
        status = act.status if act else 'not_submitted'
        verifier = act.faculty.full_name if (act and act.faculty) else None
        
        student_data.append({
            'full_name': s.full_name,
            'institution_id': s.institution_id,
            'batch_year': s.batch_year,
            'status': status,
            'verifier': verifier,
            'updated_at': act.updated_at if act else None,
            'activity_id': act.id if act else None
        })
        
    return render_template('event_participants.html', 
        event_title=title, 
        organizer=organizer, 
        issue_date=issue_date_str,
        department=dept,
        students=student_data
    )

# --- API Routes (JSON) ---

@bp.route('/api/event/participants')
@role_required('faculty', 'hod', 'admin')
def api_event_participants():
    """
    JSON API for event participants (used by AJAX modal).
    Returns: { submitted: [...], not_submitted: [...], stats: {...} }
    """
    from flask import jsonify
    
    title = request.args.get('title')
    organizer = request.args.get('organizer')
    issue_date_str = request.args.get('date')
    
    # Filters
    status_filter = request.args.get('status')
    batch_filter = request.args.get('batch_year')
    search_query = request.args.get('search', '').strip().lower()
    
    if not title:
        return jsonify({'error': 'Event title required'}), 400
    
    # Determine Dept context
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    if not dept:
        return jsonify({'error': 'Department context missing'}), 400
    
    # Alias for Student
    Student = aliased(User)
    
    # Get all students in dept
    students_q = User.query.filter_by(role='student', department=dept)
    if batch_filter:
        students_q = students_q.filter(User.batch_year == batch_filter)
    if search_query:
        students_q = students_q.filter(
            or_(
                User.full_name.ilike(f'%{search_query}%'),
                User.institution_id.ilike(f'%{search_query}%')
            )
        )
    all_students = students_q.order_by(User.institution_id).all()
    
    # Get participants for this event
    q = db.session.query(StudentActivity).join(Student, StudentActivity.student_id == Student.id).filter(
        Student.department == dept,
        StudentActivity.title == title
    )
    if organizer:
        q = q.filter(StudentActivity.organizer == organizer)
    if issue_date_str and issue_date_str != 'None':
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            q = q.filter(StudentActivity.issue_date == issue_date)
        except ValueError:
            pass
    
    participants = q.all()
    part_map = {p.student_id: p for p in participants}
    
    # 3 groups for enhanced bar click
    participated_submitted = []   # Students who participated AND have verified certificate
    participated_no_cert = []     # Students who participated but cert is pending/rejected
    not_participated = []         # Students who didn't participate at all
    
    for s in all_students:
        act = part_map.get(s.id)
        student_info = {
            'id': s.id,
            'full_name': s.full_name,
            'institution_id': s.institution_id or '',
            'batch_year': s.batch_year or '',
            'status': act.status if act else 'not_participated',
            'updated_at': act.updated_at.strftime('%Y-%m-%d %H:%M') if (act and act.updated_at) else None
        }
        
        if act:
            # Student has a submission for this event
            if act.status in ('faculty_verified', 'auto_verified'):
                # Verified = participated + submitted
                if status_filter and status_filter not in ('faculty_verified', 'auto_verified', 'participated_submitted'):
                    continue
                participated_submitted.append(student_info)
            else:
                # Pending or Rejected = participated but no cert yet
                if status_filter and status_filter not in ('pending', 'rejected', 'participated_no_cert'):
                    continue
                participated_no_cert.append(student_info)
        else:
            # No submission = not participated
            if status_filter and status_filter not in ('not_participated', 'not_submitted'):
                continue
            not_participated.append(student_info)
    
    stats = {
        'total_students': len(all_students),
        'participated_submitted_count': len(participated_submitted),
        'participated_no_cert_count': len(participated_no_cert),
        'not_participated_count': len(not_participated),
        # Legacy stats for backward compatibility
        'submitted_count': len(participated_submitted) + len(participated_no_cert),
        'not_submitted_count': len(not_participated),
        'verified_count': len(participated_submitted),
        'pending_count': sum(1 for s in participated_no_cert if s['status'] == 'pending'),
        'rejected_count': sum(1 for s in participated_no_cert if s['status'] == 'rejected')
    }
    
    return jsonify({
        # New 3-group structure
        'participated_submitted': participated_submitted,
        'participated_no_cert': participated_no_cert,
        'not_participated': not_participated,
        # Legacy keys for backward compatibility
        'submitted': participated_submitted + participated_no_cert,
        'not_submitted': not_participated,
        'stats': stats,
        'event': {
            'title': title,
            'organizer': organizer,
            'date': issue_date_str
        }
    })

@bp.route('/faculty/export/participants')
@role_required('faculty', 'hod', 'admin')
def export_event_participants():
    """Export event participants to CSV with filters."""
    import csv
    import io
    
    title = request.args.get('title')
    organizer = request.args.get('organizer')
    issue_date_str = request.args.get('date')
    
    # Filters
    status_filter = request.args.get('status')
    batch_filter = request.args.get('batch_year')
    search_query = request.args.get('search', '').strip().lower()
    
    if not title:
        flash("Event title required for export.", "error")
        return redirect(request.referrer or url_for('main.faculty_stats'))
    
    # Determine Dept context
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    if not dept:
        flash("Department context missing.", "error")
        return redirect(request.referrer or url_for('main.faculty_stats'))
    
    # Alias for Student
    Student = aliased(User)
    
    # Get all students in dept
    students_q = User.query.filter_by(role='student', department=dept)
    if batch_filter:
        students_q = students_q.filter(User.batch_year == batch_filter)
    if search_query:
        students_q = students_q.filter(
            or_(
                User.full_name.ilike(f'%{search_query}%'),
                User.institution_id.ilike(f'%{search_query}%')
            )
        )
    all_students = students_q.order_by(User.institution_id).all()
    
    # Get participants for this event
    q = db.session.query(StudentActivity).join(Student, StudentActivity.student_id == Student.id).filter(
        Student.department == dept,
        StudentActivity.title == title
    )
    if organizer:
        q = q.filter(StudentActivity.organizer == organizer)
    if issue_date_str and issue_date_str != 'None':
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            q = q.filter(StudentActivity.issue_date == issue_date)
        except ValueError:
            pass
    
    participants = q.all()
    part_map = {p.student_id: p for p in participants}
    
    # Build CSV
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Name', 'Roll No', 'Batch', 'Status', 'Updated'])
    
    for s in all_students:
        act = part_map.get(s.id)
        status = act.status if act else 'not_submitted'
        updated = act.updated_at.strftime('%Y-%m-%d %H:%M') if (act and act.updated_at) else ''
        
        # Apply status filter
        if status_filter and status != status_filter:
            continue
        
        cw.writerow([s.full_name, s.institution_id or '', s.batch_year or '', status, updated])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={title.replace(' ', '_')}_participants.csv"
    output.headers["Content-type"] = "text/csv"
    return output


# --- Stats Card Click API Endpoints ---

@bp.route('/api/stats/activities')
@role_required('faculty', 'hod', 'admin')
def api_stats_activities():
    """
    Returns all activities/events for the department.
    For "Total Activities" card click.
    """
    from flask import jsonify
    
    # Determine dept context
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    if not dept:
        return jsonify({'error': 'Department context missing'}), 400
    
    # Filters
    search = request.args.get('search', '').strip().lower()
    activity_type = request.args.get('activity_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    # Alias for Student
    Student = aliased(User)
    
    # Get all unique events (grouped by title, organizer, date)
    events_q = db.session.query(
        StudentActivity.title,
        StudentActivity.organizer,
        StudentActivity.issue_date,
        StudentActivity.activity_type_id,
        ActivityType.name.label('type_name'),
        func.count(StudentActivity.id).label('participant_count'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
    ).join(Student, StudentActivity.student_id == Student.id)\
     .outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)\
     .filter(Student.department == dept)
    
    # Apply filters
    if search:
        events_q = events_q.filter(
            or_(
                StudentActivity.title.ilike(f'%{search}%'),
                StudentActivity.organizer.ilike(f'%{search}%')
            )
        )
    if activity_type:
        events_q = events_q.filter(StudentActivity.activity_type_id == activity_type)
    if date_from:
        try:
            d = datetime.strptime(date_from, '%Y-%m-%d').date()
            events_q = events_q.filter(StudentActivity.issue_date >= d)
        except ValueError:
            pass
    if date_to:
        try:
            d = datetime.strptime(date_to, '%Y-%m-%d').date()
            events_q = events_q.filter(StudentActivity.issue_date <= d)
        except ValueError:
            pass
    
    events_q = events_q.group_by(
        StudentActivity.title, StudentActivity.organizer, StudentActivity.issue_date,
        StudentActivity.activity_type_id, ActivityType.name
    ).order_by(StudentActivity.issue_date.desc())
    
    # Pagination
    total = events_q.count()
    events = events_q.offset((page - 1) * per_page).limit(per_page).all()
    
    activities = []
    for e in events:
        activities.append({
            'title': e.title,
            'organizer': e.organizer or '',
            'date': str(e.issue_date) if e.issue_date else '',
            'type': e.type_name or 'Other',
            'participants': e.participant_count,
            'approved': e.approved or 0,
            'pending': e.pending or 0,
            'rejected': e.rejected or 0
        })
    
    return jsonify({
        'activities': activities,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@bp.route('/api/stats/verified')
@role_required('faculty', 'hod', 'admin')
def api_stats_verified():
    """
    Returns all verified/approved certificates.
    For "Verified Portfolio" card click.
    """
    from flask import jsonify
    
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    if not dept:
        return jsonify({'error': 'Department context missing'}), 400
    
    # Filters
    search = request.args.get('search', '').strip().lower()
    batch_year = request.args.get('batch_year')
    activity_type = request.args.get('activity_type')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    # Query verified certificates
    Student = aliased(User)
    Faculty = aliased(User)
    
    certs_q = db.session.query(
        Student.full_name.label('student_name'),
        Student.institution_id.label('roll_number'),
        Student.batch_year,
        StudentActivity.id.label('cert_id'),
        StudentActivity.title.label('event_name'),
        StudentActivity.updated_at.label('approval_date'),
        StudentActivity.status,
        Faculty.full_name.label('verifier')
    ).join(Student, StudentActivity.student_id == Student.id)\
     .outerjoin(Faculty, StudentActivity.verified_by_id == Faculty.id)\
     .filter(
         Student.department == dept,
         StudentActivity.status.in_(['faculty_verified', 'auto_verified'])
     )
    
    if search:
        certs_q = certs_q.filter(
            or_(
                Student.full_name.ilike(f'%{search}%'),
                Student.institution_id.ilike(f'%{search}%'),
                StudentActivity.title.ilike(f'%{search}%')
            )
        )
    if batch_year:
        certs_q = certs_q.filter(Student.batch_year == batch_year)
    if activity_type:
        certs_q = certs_q.filter(StudentActivity.activity_type_id == activity_type)
    
    certs_q = certs_q.order_by(StudentActivity.updated_at.desc())
    
    total = certs_q.count()
    certs = certs_q.offset((page - 1) * per_page).limit(per_page).all()
    
    verified = []
    for c in certs:
        verified.append({
            'student_name': c.student_name,
            'roll_number': c.roll_number or '',
            'batch_year': c.batch_year or '',
            'cert_id': c.cert_id,
            'event_name': c.event_name,
            'approval_date': c.approval_date.strftime('%Y-%m-%d %H:%M') if c.approval_date else '',
            'status': c.status,
            'verifier': c.verifier or 'Auto-Verified'
        })
    
    return jsonify({
        'verified': verified,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@bp.route('/api/stats/participation')
@role_required('faculty', 'hod', 'admin')
def api_stats_participation():
    """
    Returns student participation summary.
    For "Student Participation" card click.
    """
    from flask import jsonify
    
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    if not dept:
        return jsonify({'error': 'Department context missing'}), 400
    
    # Filters
    search = request.args.get('search', '').strip().lower()
    batch_year = request.args.get('batch_year')
    min_events = request.args.get('min_events', type=int)
    zero_participation = request.args.get('zero_participation', '') == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    # Subquery for counts per student
    cert_counts = db.session.query(
        StudentActivity.student_id,
        func.count(distinct(func.concat(StudentActivity.title, StudentActivity.organizer, StudentActivity.issue_date))).label('events_participated'),
        func.count(StudentActivity.id).label('submitted'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected'),
        func.max(StudentActivity.updated_at).label('last_activity')
    ).group_by(StudentActivity.student_id).subquery()
    
    # Join with students
    students_q = db.session.query(
        User.id,
        User.full_name,
        User.institution_id,
        User.batch_year,
        func.coalesce(cert_counts.c.events_participated, 0).label('events_participated'),
        func.coalesce(cert_counts.c.submitted, 0).label('submitted'),
        func.coalesce(cert_counts.c.approved, 0).label('approved'),
        func.coalesce(cert_counts.c.rejected, 0).label('rejected'),
        cert_counts.c.last_activity
    ).outerjoin(cert_counts, User.id == cert_counts.c.student_id)\
     .filter(User.role == 'student', User.department == dept)
    
    if search:
        students_q = students_q.filter(
            or_(
                User.full_name.ilike(f'%{search}%'),
                User.institution_id.ilike(f'%{search}%')
            )
        )
    if batch_year:
        students_q = students_q.filter(User.batch_year == batch_year)
    
    # Having filters
    if min_events is not None:
        students_q = students_q.having(func.coalesce(cert_counts.c.events_participated, 0) >= min_events)
    if zero_participation:
        students_q = students_q.having(func.coalesce(cert_counts.c.events_participated, 0) == 0)
    
    students_q = students_q.group_by(
        User.id, User.full_name, User.institution_id, User.batch_year,
        cert_counts.c.events_participated, cert_counts.c.submitted,
        cert_counts.c.approved, cert_counts.c.rejected, cert_counts.c.last_activity
    ).order_by(desc('approved'))
    
    total = students_q.count()
    students = students_q.offset((page - 1) * per_page).limit(per_page).all()
    
    participation = []
    for s in students:
        participation.append({
            'id': s.id,
            'student_name': s.full_name,
            'roll_number': s.institution_id or '',
            'batch_year': s.batch_year or '',
            'events_participated': s.events_participated,
            'submitted': s.submitted,
            'approved': s.approved,
            'rejected': s.rejected,
            'last_activity': s.last_activity.strftime('%Y-%m-%d') if s.last_activity else ''
        })
    
    return jsonify({
        'participation': participation,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


# --- Insights & Analytics API Endpoints ---

@bp.route('/api/insights/certificate-metrics')
@role_required('faculty', 'hod', 'admin')
def api_certificate_metrics():
    """
    Returns aggregate certificate KPIs with optional filters.
    Section A: Certificate metrics
    """
    from flask import jsonify
    from sqlalchemy import func, case
    from datetime import datetime
    import hashlib
    
    # Role-based department filtering
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    # Date filters
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Base query
    query = db.session.query(StudentActivity)
    
    # Apply department filter
    if dept:
        query = query.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
    
    # Apply date filters
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StudentActivity.created_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(StudentActivity.created_at <= dt)
        except ValueError:
            pass
    
    # Get all activities for calculations
    activities = query.all()
    
    # Calculate metrics
    total_submitted = len(activities)
    total_approved = sum(1 for a in activities if a.status in ('faculty_verified', 'auto_verified'))
    total_rejected = sum(1 for a in activities if a.status == 'rejected')
    total_pending = sum(1 for a in activities if a.status == 'pending')
    total_auto_verified = sum(1 for a in activities if a.status == 'auto_verified')
    total_faculty_verified = sum(1 for a in activities if a.status == 'faculty_verified')
    
    # Average verification time (for approved only)
    verification_times = []
    for a in activities:
        if a.approved_at and a.created_at and a.status in ('faculty_verified', 'auto_verified'):
            delta = (a.approved_at - a.created_at).total_seconds() / 3600  # hours
            verification_times.append(delta)
    
    avg_verification_time = sum(verification_times) / len(verification_times) if verification_times else 0
    
    # Average verification time by department (admin only)
    avg_by_dept = {}
    if current_user.role == 'admin' and not dept:
        dept_query = db.session.query(
            User.department,
            func.avg(
                func.extract('epoch', StudentActivity.approved_at) - 
                func.extract('epoch', StudentActivity.created_at)
            ).label('avg_seconds')
        ).join(User, StudentActivity.student_id == User.id)\
         .filter(StudentActivity.status.in_(['faculty_verified', 'auto_verified']))\
         .filter(StudentActivity.approved_at.isnot(None))
        
        if date_from:
            try:
                df = datetime.strptime(date_from, '%Y-%m-%d')
                dept_query = dept_query.filter(StudentActivity.created_at >= df)
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                dept_query = dept_query.filter(StudentActivity.created_at <= dt)
            except ValueError:
                pass
        
        dept_times = dept_query.group_by(User.department).all()
        for d, avg_sec in dept_times:
            if d and avg_sec:
                avg_by_dept[d] = round(avg_sec / 3600, 2)  # hours
    
    # Hash mismatch detection (sample check - computationally expensive for all)
    hash_mismatch_count = 0
    # Note: Full hash verification should be done in background job, here we report stored flag
    # For now, count activities where certificate_hash exists but verification failed
    # This would need a separate flag in the model - simplified here
    
    return jsonify({
        'total_submitted': total_submitted,
        'total_approved': total_approved,
        'total_rejected': total_rejected,
        'total_pending': total_pending,
        'total_auto_verified': total_auto_verified,
        'verification_mode_distribution': {
            'auto_verified': total_auto_verified,
            'faculty_verified': total_faculty_verified
        },
        'avg_verification_time_hours': round(avg_verification_time, 2),
        'avg_verification_time_by_dept': avg_by_dept,
        'hash_mismatch_count': hash_mismatch_count
    })


@bp.route('/api/insights/certificates-timeseries')
@role_required('faculty', 'hod', 'admin')
def api_certificates_timeseries():
    """
    Returns monthly time-series data for certificates.
    Section A: Time-series views
    """
    from flask import jsonify
    from sqlalchemy import func, extract, case
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    # Role-based department filtering
    if current_user.role == 'admin':
        dept = request.args.get('department')
    else:
        dept = current_user.department
    
    # Date filters (default: last 12 months)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    if not date_from:
        # Default to 12 months ago
        date_from = (datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = datetime.utcnow().strftime('%Y-%m-%d')
    
    try:
        df = datetime.strptime(date_from, '%Y-%m-%d')
        dt = datetime.strptime(date_to, '%Y-%m-%d')
    except ValueError:
        df = datetime.utcnow() - timedelta(days=365)
        dt = datetime.utcnow()
    
    # Query for monthly aggregates
    query = db.session.query(
        func.to_char(StudentActivity.created_at, 'YYYY-MM').label('month'),
        func.count(StudentActivity.id).label('submitted'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending')
    ).filter(StudentActivity.created_at >= df, StudentActivity.created_at <= dt)
    
    # Apply department filter
    if dept:
        query = query.join(User, StudentActivity.student_id == User.id).filter(User.department == dept)
    
    results = query.group_by('month').order_by('month').all()
    
    months = []
    submitted = []
    approved = []
    rejected = []
    pending = []
    
    for r in results:
        months.append(r.month)
        submitted.append(r.submitted or 0)
        approved.append(r.approved or 0)
        rejected.append(r.rejected or 0)
        pending.append(r.pending or 0)
    
    return jsonify({
        'months': months,
        'submitted': submitted,
        'approved': approved,
        'rejected': rejected,
        'pending': pending
    })


@bp.route('/api/insights/departments')
@role_required('faculty', 'hod', 'admin')
def api_insights_departments():
    """
    Returns department-level aggregated stats for drill-down.
    Section C: Level 1 - Department bar chart
    """
    from flask import jsonify
    from sqlalchemy import func, case, distinct
    
    metric = request.args.get('metric', 'students')  # 'students' or 'certificates'
    
    # Role-based access
    if current_user.role == 'admin':
        allowed_depts = None  # All departments
    else:
        allowed_depts = [current_user.department]
    
    # Get all departments with students
    dept_query = db.session.query(
        User.department,
        func.count(distinct(User.id)).label('total_students')
    ).filter(User.role == 'student')
    
    if allowed_depts:
        dept_query = dept_query.filter(User.department.in_(allowed_depts))
    
    dept_query = dept_query.group_by(User.department)
    departments = {d.department: {'total_students': d.total_students} for d in dept_query.all() if d.department}
    
    # Get participation and certificate stats per department
    cert_query = db.session.query(
        User.department,
        func.count(distinct(StudentActivity.student_id)).label('participating_students'),
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved_certs'),
        func.count(distinct(func.concat(StudentActivity.title, '-', StudentActivity.organizer, '-', 
                                         func.coalesce(StudentActivity.issue_date, '')))).label('events_count')
    ).join(User, StudentActivity.student_id == User.id)\
     .filter(User.role == 'student')
    
    if allowed_depts:
        cert_query = cert_query.filter(User.department.in_(allowed_depts))
    
    cert_query = cert_query.group_by(User.department)
    
    for r in cert_query.all():
        if r.department in departments:
            departments[r.department].update({
                'participating_students': r.participating_students or 0,
                'total_certs': r.total_certs or 0,
                'approved_certs': r.approved_certs or 0,
                'events_count': r.events_count or 0
            })
    
    # Format response
    result = []
    for dept, stats in departments.items():
        result.append({
            'department': dept,
            'total_students': stats.get('total_students', 0),
            'participating_students': stats.get('participating_students', 0),
            'total_approved_certs': stats.get('approved_certs', 0),
            'events_count': stats.get('events_count', 0)
        })
    
    result.sort(key=lambda x: x['participating_students'] if metric == 'students' else x['total_approved_certs'], reverse=True)
    
    return jsonify({'departments': result})


@bp.route('/api/insights/department/<department>/events')
@role_required('faculty', 'hod', 'admin')
def api_department_events(department):
    """
    Returns events within a department for drill-down.
    Section C: Level 2 - Event bar chart
    """
    from flask import jsonify
    from sqlalchemy import func, case, distinct
    from urllib.parse import unquote
    
    department = unquote(department)
    
    # Role-based access check
    if current_user.role not in ('admin',) and current_user.department != department:
        return jsonify({'error': 'Unauthorized access to this department'}), 403
    
    # Get unique events (grouped by title + organizer + date)
    events_query = db.session.query(
        StudentActivity.title,
        StudentActivity.organizer,
        StudentActivity.issue_date,
        func.count(distinct(StudentActivity.student_id)).label('participating_students'),
        func.count(StudentActivity.id).label('total_certs'),
        func.sum(case((StudentActivity.status.in_(['faculty_verified', 'auto_verified']), 1), else_=0)).label('approved'),
        func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
        func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
    ).join(User, StudentActivity.student_id == User.id)\
     .filter(User.department == department, User.role == 'student')\
     .group_by(StudentActivity.title, StudentActivity.organizer, StudentActivity.issue_date)\
     .order_by(StudentActivity.issue_date.desc())
    
    # Activity In-charge filter
    if current_user.role == 'faculty' and current_user.position != 'hod':
        # Check if they manage any activity types
        managed_types = ActivityType.query.filter_by(faculty_incharge_id=current_user.id).all()
        if managed_types:
            type_ids = [t.id for t in managed_types]
            events_query = events_query.filter(StudentActivity.activity_type_id.in_(type_ids))
    
    events = events_query.all()
    
    result = []
    for e in events:
        event_key = f"{e.title or ''}|{e.organizer or ''}|{str(e.issue_date) if e.issue_date else ''}"
        result.append({
            'event_key': event_key,
            'title': e.title,
            'organizer': e.organizer or '',
            'date': e.issue_date.strftime('%Y-%m-%d') if e.issue_date else '',
            'participating_students': e.participating_students or 0,
            'certificates': e.total_certs or 0,
            'approved': e.approved or 0,
            'pending': e.pending or 0,
            'rejected': e.rejected or 0
        })
    
    return jsonify({
        'department': department,
        'events': result
    })


@bp.route('/api/insights/department/<department>/event/<path:event_key>/students')
@role_required('faculty', 'hod', 'admin')
def api_event_students(department, event_key):
    """
    Returns students for a specific event with participation status.
    Section D: Event → student list
    """
    from flask import jsonify
    from urllib.parse import unquote
    
    department = unquote(department)
    event_key = unquote(event_key)
    
    # Role-based access check
    if current_user.role not in ('admin',) and current_user.department != department:
        return jsonify({'error': 'Unauthorized access to this department'}), 403
    
    # Parse event key (title|organizer|date)
    parts = event_key.split('|')
    title = parts[0] if len(parts) > 0 else ''
    organizer = parts[1] if len(parts) > 1 else ''
    date_str = parts[2] if len(parts) > 2 else ''
    
    # Filters
    year_filter = request.args.get('year')
    section_filter = request.args.get('section')
    participation_filter = request.args.get('participation_status')
    cert_status_filter = request.args.get('certificate_status')
    search = request.args.get('search', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Get all students in department
    students_query = User.query.filter(User.role == 'student', User.department == department)
    
    if year_filter:
        students_query = students_query.filter(User.batch_year == year_filter)
    if search:
        students_query = students_query.filter(
            or_(
                User.full_name.ilike(f'%{search}%'),
                User.institution_id.ilike(f'%{search}%')
            )
        )
    
    all_students = students_query.all()
    
    # Get students who submitted certificates for this event
    cert_query = StudentActivity.query.join(User, StudentActivity.student_id == User.id)\
        .filter(User.department == department, User.role == 'student')\
        .filter(StudentActivity.title == title)
    
    if organizer:
        cert_query = cert_query.filter(StudentActivity.organizer == organizer)
    if date_str:
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            cert_query = cert_query.filter(StudentActivity.issue_date == event_date)
        except ValueError:
            pass
    
    certificates = cert_query.all()
    cert_map = {c.student_id: c for c in certificates}
    
    # Build result with participation status
    result = []
    stats = {'participated_submitted': 0, 'participated_no_cert': 0, 'not_participated': 0}
    
    for s in all_students:
        cert = cert_map.get(s.id)
        
        if cert:
            participation_status = 'Participated + Submitted'
            certificate_status = {
                'faculty_verified': 'Faculty Verified',
                'auto_verified': 'Auto Verified',
                'pending': 'Pending',
                'rejected': 'Rejected'
            }.get(cert.status, cert.status)
            last_updated = cert.updated_at.strftime('%Y-%m-%d %H:%M') if cert.updated_at else ''
            stats['participated_submitted'] += 1
        else:
            # For now, treat no certificate as "Not participated"
            # In a full system, we'd have a participation table
            participation_status = 'Not Participated'
            certificate_status = ''
            last_updated = ''
            stats['not_participated'] += 1
        
        # Apply filters
        if participation_filter:
            if participation_filter == 'participated_submitted' and participation_status != 'Participated + Submitted':
                continue
            if participation_filter == 'not_participated' and participation_status != 'Not Participated':
                continue
        
        if cert_status_filter and certificate_status.lower().replace(' ', '_') != cert_status_filter.lower():
            continue
        
        result.append({
            'id': s.id,
            'name': s.full_name,
            'roll_number': s.institution_id or '',
            'year': s.batch_year or '',
            'section': '',  # Section not in current model, placeholder
            'participation_status': participation_status,
            'certificate_status': certificate_status,
            'last_updated': last_updated
        })
    
    # Paginate
    total = len(result)
    result = result[(page - 1) * per_page:page * per_page]
    
    return jsonify({
        'event': {
            'title': title,
            'organizer': organizer,
            'date': date_str
        },
        'students': result,
        'stats': stats,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@bp.route('/api/insights/department/<department>/event/<path:event_key>/students/export')
@role_required('faculty', 'hod', 'admin')
def api_event_students_export(department, event_key):
    """
    CSV export for event students with all filters.
    Section D: Download CSV
    """
    from urllib.parse import unquote
    import csv
    import io
    
    department = unquote(department)
    event_key = unquote(event_key)
    
    # Role-based access check
    if current_user.role not in ('admin',) and current_user.department != department:
        return abort(403)
    
    # Parse event key
    parts = event_key.split('|')
    title = parts[0] if len(parts) > 0 else ''
    organizer = parts[1] if len(parts) > 1 else ''
    date_str = parts[2] if len(parts) > 2 else ''
    
    # Filters
    year_filter = request.args.get('year')
    participation_filter = request.args.get('participation_status')
    cert_status_filter = request.args.get('certificate_status')
    search = request.args.get('search', '').strip().lower()
    
    # Get students
    students_query = User.query.filter(User.role == 'student', User.department == department)
    if year_filter:
        students_query = students_query.filter(User.batch_year == year_filter)
    if search:
        students_query = students_query.filter(
            or_(User.full_name.ilike(f'%{search}%'), User.institution_id.ilike(f'%{search}%'))
        )
    
    all_students = students_query.all()
    
    # Get certificates
    cert_query = StudentActivity.query.join(User, StudentActivity.student_id == User.id)\
        .filter(User.department == department, StudentActivity.title == title)
    if organizer:
        cert_query = cert_query.filter(StudentActivity.organizer == organizer)
    if date_str:
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            cert_query = cert_query.filter(StudentActivity.issue_date == event_date)
        except ValueError:
            pass
    
    cert_map = {c.student_id: c for c in cert_query.all()}
    
    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Roll Number', 'Year', 'Section', 'Participation Status', 'Certificate Status', 'Last Updated'])
    
    for s in all_students:
        cert = cert_map.get(s.id)
        
        if cert:
            participation_status = 'Participated + Submitted'
            certificate_status = {
                'faculty_verified': 'Faculty Verified',
                'auto_verified': 'Auto Verified',
                'pending': 'Pending',
                'rejected': 'Rejected'
            }.get(cert.status, cert.status)
            last_updated = cert.updated_at.strftime('%Y-%m-%d %H:%M') if cert.updated_at else ''
        else:
            participation_status = 'Not Participated'
            certificate_status = ''
            last_updated = ''
        
        # Apply filters
        if participation_filter:
            if participation_filter == 'participated_submitted' and participation_status != 'Participated + Submitted':
                continue
            if participation_filter == 'not_participated' and participation_status != 'Not Participated':
                continue
        
        if cert_status_filter and certificate_status.lower().replace(' ', '_') != cert_status_filter.lower():
            continue
        
        writer.writerow([s.full_name, s.institution_id or '', s.batch_year or '', '', participation_status, certificate_status, last_updated])
    
    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename="{title}_students.csv"'
    return response
