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
