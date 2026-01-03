
"""
Certificate Verification App
----------------------------
Modular Structure with Authentication (Flask-Login) & PostgreSQL (SQLAlchemy).

- app.py: Routes, Auth, Orchestration
- verification/: Logic Modules
- models.py: DB Models
"""

import os
import json
import secrets
from functools import wraps
from datetime import datetime
import csv
import io
from flask import Flask, request, render_template, flash, redirect, url_for, send_from_directory, abort, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func, case, distinct, or_

# --- Imports from Modules ---
from verification import extract, analyze, verify, hashstore, queue
from verification.auto_verifier import run_auto_verification
from models import db, User, ActivityType, StudentActivity
from xhtml2pdf import pisa

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
# SECRET_KEY should be strong in prod
SECRET_KEY = 'dev-secret-key' 
# Edit the URI below to match your local setup
# URL-encoded password for 'root@123' is 'root%40123'
SQLALCHEMY_DATABASE_URI = "postgresql://postgres:root%40123@localhost:5432/smarthub"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Init extensions ---
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# --- Auth Helpers ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

# --- CLI Commands ---

@app.cli.command("init-db")
def init_db():
    """Create database tables and default admin."""
    with app.app_context():
        # Drop all to ensure schema updates are applied (Prototype only)
        db.drop_all()
        db.create_all()
        
        # Create default admin
        admin = User(
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            full_name='System Administrator',
            department='IT',
            institution_id='ADMIN001'
        )
        db.session.add(admin)
        
        # Create Faculty: Dr. Smith
        dr_smith = User(
            email='drsmith@college.edu',
            password_hash=generate_password_hash('password'),
            role='faculty',
            full_name='Dr. Smith',
            department='CSE',
            institution_id='FAC001'
        )
        db.session.add(dr_smith)
        db.session.add(dr_smith)
        
        # Create HOD CSE: Prof. HOD
        prof_hod = User(
            email='hod.cse@college.edu',
            password_hash=generate_password_hash('password'),
            role='faculty',
            position='hod',
            full_name='Prof. HOD CSE',
            department='CSE',
            institution_id='FAC_HOD_01'
        )
        db.session.add(prof_hod)
        
        db.session.commit() # Commit to get ID for Dr. Smith & HOD
        
        # Create Dummy Activity Types
        act1 = ActivityType(name="Technical Workshop", faculty_incharge_id=dr_smith.id, description="Workshops on coding, robotics, etc.")
        act2 = ActivityType(name="Sports Meet", faculty_incharge_id=admin.id, description="Inter-college and Intra-college sports.")
        db.session.add(act1)
        db.session.add(act2)
        
        db.session.commit()
        print("Initialized DB (Table Reset), created users (Admin, Dr. Smith), and seeded activity types.")

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_users'))
        elif current_user.role == 'faculty':
            return redirect(url_for('faculty_dashboard'))
        else:
            return redirect(url_for('index'))
    
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
                return redirect(url_for('admin_users'))
            elif user.role == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid email or password.')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('login'))

@app.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    if current_user.role not in ['faculty', 'admin', 'student']:
        pass
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/', methods=['GET', 'POST'])
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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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

            return redirect(url_for('index'))

        else:
            flash('Invalid file type.')
            return redirect(request.url)

    return render_template('index.html', result=result, user_roll_no=user_roll_no, activity_types=activity_types)

# --- Faculty / Admin Routes ---

@app.route('/faculty')
@role_required('faculty', 'admin')
def faculty_dashboard():
    # Fetch from DB now
    query = db.session.query(StudentActivity).outerjoin(ActivityType).filter(StudentActivity.status == 'pending')
    
    if current_user.role == 'faculty':
        # NEW: Filter by Assigned Reviewer ID (HOD or Activity In-Charge)
        query = query.filter(StudentActivity.assigned_reviewer_id == current_user.id)
        
    pending_activities = query.order_by(StudentActivity.created_at.desc()).all()
    
    return render_template('faculty.html', pending_requests=pending_activities)

@app.route('/faculty/approve/<int:act_id>', methods=['POST'])
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
    return redirect(url_for('faculty_dashboard'))

@app.route('/faculty/reject/<int:act_id>', methods=['POST'])
@role_required('faculty', 'admin')
def reject_request(act_id):
    activity = StudentActivity.query.get_or_404(act_id)
    comment = request.form.get('faculty_comment', '')
    
    activity.status = 'rejected'
    activity.faculty_id = current_user.id
    activity.faculty_comment = comment
    
    db.session.commit()
    flash(f"Activity #{act_id} Rejected.")
    return redirect(url_for('faculty_dashboard'))

# --- Admin Routes ---

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/create', methods=['POST'])
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
         return redirect(url_for('admin_users'))
         
    if role == 'faculty':
        if not department or not institution_id:
            flash('Faculty must have Department and Institution ID (Employee ID).')
            return redirect(url_for('admin_users'))
            
    if role == 'student':
        if not department:
            flash('Students must have a Department.')
            return redirect(url_for('admin_users'))
        if not institution_id:
            flash('Students must have an Institution ID (Roll Number).')
            return redirect(url_for('admin_users'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already registered.')
        return redirect(url_for('admin_users'))
    
    if institution_id and User.query.filter_by(institution_id=institution_id).first():
        flash('Institution ID (ID/RollNo) must be unique.')
        return redirect(url_for('admin_users'))
        
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
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
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
        return redirect(url_for('admin_users'))

    return render_template('admin_user_edit.html', user=user)


@app.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
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
    return redirect(url_for('admin_users'))

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("Cannot delete your own admin account.")
        return redirect(url_for('admin_users'))
        
    if user.role == 'admin' and user.email == 'admin@example.com':
        flash("Cannot delete default admin.")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} deleted.")
    return redirect(url_for('admin_users'))

# --- NAAC / Admin Analytics ---

@app.route('/admin/naac-dashboard')
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

@app.route('/admin/export-naac')
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
        
        # Apply filters (Note: apply_filters helper above uses join logic which might duplicate unless careful, but for stats grouping it's ok)
        # Re-implementing simplified filter for aggregate query
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
        q = apply_filters(q) # Uses standard join
        
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

@app.route('/admin/activity-types', methods=['GET', 'POST'])
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
        return redirect(url_for('admin_activity_types'))
    
    # Render with Faculty List for Dropdown
    activity_types = ActivityType.query.all()
    faculty_users = User.query.filter_by(role='faculty').all()
    
    return render_template('admin_activity_types.html', activity_types=activity_types, faculty_users=faculty_users)

@app.route('/admin/activity-types/<int:at_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_activity_type(at_id):
    at = ActivityType.query.get_or_404(at_id)
    
    if request.method == 'POST':
        at.name = request.form.get('name')
        at.faculty_incharge_id = request.form.get('faculty_id')
        at.description = request.form.get('description')
        
        # Check Uniqueness
        existing = ActivityType.query.filter(ActivityType.name == at.name, ActivityType.id != at.id).first()
        if existing:
            flash(f"Activity Type '{at.name}' already exists.")
        else:
            db.session.commit()
            flash(f"Activity Type '{at.name}' updated.")
            return redirect(url_for('admin_activity_types'))
            
    faculty_users = User.query.filter(User.role.in_(['faculty', 'admin'])).all()
    return render_template('admin_activity_type_edit.html', activity_type=at, faculty_users=faculty_users)

@app.route('/admin/activity-types/delete/<int:at_id>', methods=['POST'])
@role_required('admin')
def admin_delete_activity_type(at_id):
    at = ActivityType.query.get_or_404(at_id)
    db.session.delete(at)
    db.session.commit()
    flash('Activity Type deleted.')
    return redirect(url_for('admin_activity_types'))

# --- Portfolio Route ---

@app.route('/student/portfolio')
@role_required('student')
def student_portfolio():
    activities = StudentActivity.query.filter_by(student_id=current_user.id).order_by(StudentActivity.created_at.desc()).all()
    return render_template('portfolio.html', activities=activities)


@app.route('/student/portfolio.pdf')
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
    
    # Create PDF
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    
    if pisa_status.err:
       return f"Error creating PDF: {pisa_status.err}", 500
       
    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=portfolio_{current_user.institution_id}.pdf'
    
    return response



# --- Public Verification Route ---

@app.route('/verify/<token>')
def verify_public(token):
    activity = StudentActivity.query.filter_by(verification_token=token).first_or_404()
    
    # Ensure it is actually verified
    if activity.status not in ['faculty_verified', 'auto_verified']:
        # Should not happen if token is only generated on verification, but safety check
        return render_template('verify_public.html', error="This record is not fully verified yet.")
        
    # Recompute Hash for Verification
    hash_match = False
    recomputed_hash = None
    
    if activity.certificate_file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], activity.certificate_file)
        if os.path.exists(filepath):
            recomputed_hash = hashstore.calculate_file_hash(filepath)
            # Compare with database stored hash
            if activity.certificate_hash and recomputed_hash == activity.certificate_hash:
                hash_match = True
    
    return render_template('verify_public.html', activity=activity, hash_match=hash_match, recomputed_hash=recomputed_hash)

if __name__ == '__main__':
    app.run(debug=True)