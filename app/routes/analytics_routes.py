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
    category = request.args.get('category_name') 
    department = request.args.get('department')
    search = request.args.get('search')
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    data = AnalyticsService.get_student_list(
        category_name=category, 
        department=department, 
        page=page, 
        per_page=per_page, 
        filters=filters,
        search=search,
        status=status
    )
    return jsonify(data)

@analytics_bp.route('/analytics/api/insights')
@login_required
def get_admin_insights():
    filters = get_filters()
    data = AnalyticsService.get_admin_insights(filters)
    return jsonify(data)

@analytics_bp.route('/analytics/api/health')
@login_required
def get_data_health():
    data = AnalyticsService.get_data_health_summary()
    return jsonify(data)

@analytics_bp.route('/analytics/api/comparison')
@login_required
def get_comparison():
    filters = get_filters()
    data = AnalyticsService.get_comparative_stats(filters)
    if data is None:
        return jsonify({"status": "disabled", "reason": "Select Academic Year"})
    return jsonify(data)

@analytics_bp.route('/analytics/test-students/<int:id>')
def test_students(id):
    return jsonify(AnalyticsService.get_test_student_list(id))

# --- Export Endpoints ---

@analytics_bp.route('/analytics/export-naac')
@login_required
def export_naac():
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
        
    filters = get_filters()
    export_type = request.args.get('type', 'full')
    
    excel_file = AnalyticsService.generate_naac_excel(filters, export_type=export_type)
    
    filename = f'NAAC_Analytics_{export_type}_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@analytics_bp.route('/analytics/export-students-table')
@login_required
def export_students_table():
    """Export the currently filtered student table view."""
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
    
    filters = get_filters()
    excel_file = AnalyticsService.generate_filtered_student_export(
        category_name=request.args.get('category_name'),
        department=request.args.get('department'),
        search=request.args.get('search'),
        status=request.args.get('status'),
        filters=filters
    )
    
    filename = f'Filtered_Students_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(excel_file, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)

@analytics_bp.route('/analytics/export-snapshot')
@login_required
def export_snapshot():
    """Lightweight KPI + Insights + Comparison export for meetings."""
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
    
    filters = get_filters()
    excel_file = AnalyticsService.generate_snapshot_export(filters=filters)
    
    filename = f'NAAC_Snapshot_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(excel_file, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)

@analytics_bp.route('/analytics/export-event-instance')
@login_required
def export_event_instance():
    """Export students for a specific event identity (drilldown)."""
    if current_user.role not in ['admin', 'faculty']:
        return abort(403)
    
    event_identity = request.args.get('identity')
    if not event_identity:
        return jsonify({"error": "Missing 'identity' parameter"}), 400
    
    filters = get_filters()
    excel_file = AnalyticsService.generate_event_instance_export(event_identity, filters=filters)
    
    filename = f'Event_Report_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(excel_file, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)
