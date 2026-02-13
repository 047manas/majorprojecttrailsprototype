from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, make_response, jsonify, send_file
from flask_login import login_required, current_user
from app.services.analytics_service import AnalyticsService
from functools import wraps
from datetime import datetime
from app.models import db, User

analytics_bp = Blueprint('analytics', __name__)

# --- Helper ---
def get_filters():
    return {
        "year": request.args.get('year', type=int),
        "department": request.args.get('department'),
        "event_type_id": request.args.get('event_type_id', type=int),
        "verified_only": request.args.get('verified_only') == 'true',
        "batch": request.args.get('batch', type=int),
        "start_date": request.args.get('start_date'),
        "end_date": request.args.get('end_date')
    }

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

@analytics_bp.route('/analytics/dashboard')
@login_required
def naac_dashboard():
    # Only Admin and Faculty should access
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
    
    # Fetch distinct departments
    departments = [r[0] for r in db.session.query(User.department).distinct().filter(User.department.isnot(None)).all()]
    
    return render_template('analytics_dashboard.html', departments=departments)

# --- JSON API Endpoints ---

@analytics_bp.route('/analytics/api/kpis')
@login_required
def get_kpi_summary():
    filters = get_filters()
    data = AnalyticsService.get_institution_kpis(filters)
    return jsonify(data)

@analytics_bp.route('/analytics/api/distribution')
@login_required
def get_event_distribution():
    filters = get_filters()
    data = AnalyticsService.get_event_distribution(filters)
    print("EVENT DISTRIBUTION RESPONSE:", data)
    return jsonify(data)

@analytics_bp.route('/analytics/api/department-participation')
@login_required
def get_department_participation():
    filters = get_filters()
    data = AnalyticsService.get_department_participation(filters)
    return jsonify(data)

@analytics_bp.route('/analytics/api/yearly-trend')
@login_required
def get_yearly_trend():
    filters = get_filters()
    data = AnalyticsService.get_yearly_trend(filters)
    return jsonify(data)

@analytics_bp.route('/analytics/api/verification-summary')
@login_required
def get_verification_summary():
    filters = get_filters()
    data = AnalyticsService.get_verification_summary(filters)
    return jsonify(data)

@analytics_bp.route('/analytics/api/student-list')
@login_required
def get_student_list():
    filters = get_filters()
    # Args
    category = request.args.get('category_name') 
    department = request.args.get('department')
    search = request.args.get('search')
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    print("\n--- DEBUG: STUDENT LIST REQUEST ---")
    print(f"Filters: {filters}")
    print(f"Args: Cat='{category}', Dept='{department}', Search='{search}', Status='{status}'")

    print(f"DEBUG RT: Student List Req: filters={filters}, args={request.args}")
    data = AnalyticsService.get_student_list(
        category_name=category, 
        department=department, 
        page=page, 
        per_page=per_page, 
        filters=filters,
        search=search,
        status=status
    )
    print(f"DEBUG RT: Result Count: {data.get('total_records')}")
    return jsonify(data)

@analytics_bp.route('/analytics/test-students/<int:id>')
def test_students(id):
    return jsonify(AnalyticsService.get_test_student_list(id))

@analytics_bp.route('/analytics/export-naac')
@login_required
def export_naac():
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
        
    filters = get_filters()
    export_type = request.args.get('type', 'full') # Default to full
    
    excel_file = AnalyticsService.generate_naac_excel(filters, export_type=export_type)
    
    filename = f'NAAC_Analytics_{export_type}_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
