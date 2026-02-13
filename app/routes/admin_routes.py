from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models import User, db, ActivityType, StudentActivity
from werkzeug.security import generate_password_hash
from functools import wraps

admin_bp = Blueprint('admin', __name__)

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

@admin_bp.route('/admin/users')
@role_required('admin')
def users_dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@admin_bp.route('/admin/users/create', methods=['POST'])
@role_required('admin')
def create_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    position = request.form.get('position')
    full_name = request.form.get('full_name')
    department = request.form.get('department')
    institution_id = request.form.get('institution_id')
    
    if not full_name:
         flash('Full Name is required.')
         return redirect(url_for('admin.users_dashboard'))
         
    if role == 'faculty':
        if not department or not institution_id:
            flash('Faculty must have Department and Institution ID (Employee ID).')
            return redirect(url_for('admin.users_dashboard'))
            
    if role == 'student':
        if not department:
            flash('Students must have a Department.')
            return redirect(url_for('admin.users_dashboard'))
        if not institution_id:
            flash('Students must have an Institution ID (Roll Number).')
            return redirect(url_for('admin.users_dashboard'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already registered.')
        return redirect(url_for('admin.users_dashboard'))
    
    if institution_id and User.query.filter_by(institution_id=institution_id).first():
        flash('Institution ID (ID/RollNo) must be unique.')
        return redirect(url_for('admin.users_dashboard'))
        
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
    
    return redirect(url_for('admin.users_dashboard'))

@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.users_dashboard'))

    return render_template('admin_user_edit.html', user=user)


@admin_bp.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@role_required('admin')
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin' and user.email == 'admin@example.com':
        flash("Cannot deactivate default admin.")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = "Activated" if user.is_active else "Deactivated"
        flash(f"User {user.email} {status}.")
    return redirect(url_for('admin.users_dashboard'))

@admin_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("Cannot delete your own admin account.")
        return redirect(url_for('admin.users_dashboard'))
        
    if user.role == 'admin' and user.email == 'admin@example.com':
        flash("Cannot delete default admin.")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} deleted.")
    return redirect(url_for('admin.users_dashboard'))

# --- Activity Types ---
@admin_bp.route('/admin/activity-types', methods=['GET', 'POST'])
@role_required('admin')
def activity_types():
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
        return redirect(url_for('admin.activity_types'))
    
    activity_types = ActivityType.query.all()
    faculty_users = User.query.filter_by(role='faculty').all()
    
    return render_template('admin_activity_types.html', activity_types=activity_types, faculty_users=faculty_users)

@admin_bp.route('/admin/activity-types/<int:at_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_activity_type(at_id):
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
            return redirect(url_for('admin.activity_types'))
            
    faculty_users = User.query.filter(User.role.in_(['faculty', 'admin'])).all()
    return render_template('admin_activity_type_edit.html', activity_type=at, faculty_users=faculty_users)

@admin_bp.route('/admin/activity-types/delete/<int:at_id>', methods=['POST'])
@role_required('admin')
def delete_activity_type(at_id):
    at = ActivityType.query.get_or_404(at_id)
    db.session.delete(at)
    db.session.commit()
    flash('Activity Type deleted.')
    return redirect(url_for('admin.activity_types'))
