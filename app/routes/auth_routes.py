from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app.models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.users_dashboard')) # Will need to update these endpoints too
        elif current_user.role == 'faculty':
            return redirect(url_for('faculty.dashboard'))
        else:
            return redirect(url_for('student.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Account deactivated. Please contact administrator.')
                return render_template('login.html')
            
            login_user(user)
            flash('Logged in successfully.')
            
            if user.role == 'admin':
                return redirect(url_for('admin.users_dashboard'))
            elif user.role == 'faculty':
                return redirect(url_for('faculty.dashboard'))
            else:
                return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid email or password.')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('auth.login'))
