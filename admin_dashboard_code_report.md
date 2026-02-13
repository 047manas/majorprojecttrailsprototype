# NAAC Analytics Dashboard - Code Report

This document contains the complete source code for the NAAC Analytics Dashboard, including the backend logic (Python/Flask), frontend template (HTML/Bootstrap), and client-side logic (JavaScript).

## 1. Backend Routes (`app/routes/analytics_routes.py`)
Handling API endpoints and page rendering.

```python
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
```

## 2. Backend Service Logic (`app/services/analytics_service.py`)
Core business logic, SQL queries, and Excel generation.

```python
from app.models import db, User, StudentActivity, ActivityType
from sqlalchemy import func, case, or_, and_, distinct, extract, Integer, tuple_, literal
from flask_login import current_user
from flask import url_for
from datetime import datetime
import pandas as pd
import io
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

class AnalyticsService:

    @staticmethod
    def _format_excel_sheet(writer, df, sheet_name):
        """
        Helper: Apply formatting (Bold Header, Auto Width)
        """
        try:
            worksheet = writer.sheets[sheet_name]
            
            # Check if dataframe is empty
            if df.empty:
                return

            for idx, col in enumerate(df.columns):
                # Header Bold
                cell = worksheet.cell(row=1, column=idx+1)
                cell.font = Font(bold=True)
                
                # Auto Width (Basic Approximation)
                # Handle empty column data safety
                col_data = df[col].astype(str)
                max_len = 0
                if not col_data.empty:
                     max_len = col_data.map(len).max()
                
                final_width = max((max_len, len(str(col)))) + 2
                worksheet.column_dimensions[get_column_letter(idx+1)].width = min(final_width, 50)
        except Exception as e:
            print(f"Excel Formatting Error on {sheet_name}: {e}")


    @staticmethod
    def _apply_role_scope(query):
        """
        [PART 4] STRICT ROLE-BASED DATA SCOPE
        """
        if not current_user.is_authenticated:
            return query.filter(1 == 0) # No access
            
        if current_user.role == 'admin':
            return query
            
        if current_user.role == 'faculty':
            conditions = []
            
            # 1. HOD: Filter by User.department
            if current_user.position and current_user.position.lower() == 'hod':
                if current_user.department:
                    conditions.append(User.department == current_user.department)
            
            # 2. Event In-Charge: Filter by Activity Types managed
            managed_activities = ActivityType.query.filter_by(faculty_incharge_id=current_user.id).all()
            if managed_activities:
                managed_ids = [a.id for a in managed_activities]
                conditions.append(StudentActivity.activity_type_id.in_(managed_ids))
                
            if conditions:
                return query.filter(or_(*conditions))
            else:
                 return query.filter(1 == 0)

        if current_user.role == 'student':
             return query.filter(StudentActivity.student_id == current_user.id)
             
        return query.filter(1 == 0)

    @staticmethod
    def _get_event_date_expr():
        """
        Helper: Coalesce start_date or created_at (cast to date)
        MANDATORY: Use this everywhere for date logic.
        """
        return func.coalesce(StudentActivity.start_date, func.cast(StudentActivity.created_at, db.Date))

    @staticmethod
    def _get_event_identity_expr():
        """
        Helper: Unique Event Identity - STRICT RULE
        - IF Activity Type is Defined (ID Not None): 'TYPE-' + ID + '-' + Date
        - ELSE (Custom): 'CUSTOM-' + Clean Title + '-' + Date
        """
        # Logic: Case when ActivityTypeID is NOT NULL -> Use TYPE-ID-Date
        # Logic: Case when ActivityTypeID IS NULL -> Use CUSTOM-Title-Date
        
        event_date = str(func.coalesce(StudentActivity.start_date, literal('nodate')))
        
        return case(
            (StudentActivity.activity_type_id.isnot(None),
             func.concat('TYPE-', StudentActivity.activity_type_id, '-', func.coalesce(func.cast(StudentActivity.start_date, db.String), 'nodate'))),
            else_=func.concat('CUSTOM-', func.coalesce(StudentActivity.custom_category, 'other'), '-', func.lower(func.trim(StudentActivity.title)), '-', func.coalesce(func.cast(StudentActivity.start_date, db.String), 'nodate'))
        )

    @staticmethod
    def _apply_filters(query, filters):
        """
        Dynamic Query Builder - Stateless
        """
        if not filters:
            return query
        
        # Use coalesced date for filtering
        event_date = AnalyticsService._get_event_date_expr()
            
        # 1. Academic Year
        if filters.get('year'):
            try:
                year = int(filters['year'])
                query = query.filter(extract('year', event_date) == year)
            except: pass

        # 2. Department
        if filters.get('department'):
            query = query.filter(User.department == filters['department'])
            
        # 3. Batch
        if filters.get('batch'):
             query = query.filter(User.batch_year == str(filters['batch']))

        # 4. Verified Only
        if filters.get('verified_only'):
             query = query.filter(or_(
                StudentActivity.status == 'faculty_verified',
                StudentActivity.status == 'auto_verified'
            ))
            
        # 5. Date Range
        if filters.get('start_date'):
            try:
                sd = filters['start_date']
                query = query.filter(event_date >= sd)
            except: pass
            
        if filters.get('end_date'):
            try:
                ed = filters['end_date']
                query = query.filter(event_date <= ed)
            except: pass
            
        return query

    @staticmethod
    def _get_base_query(filters=None):
        """
        SINGLE SOURCE OF TRUTH
        All data retrieval must start here.
        """
        query = db.session.query(StudentActivity).join(User, StudentActivity.student_id == User.id)
        query = AnalyticsService._apply_role_scope(query)
        query = AnalyticsService._apply_filters(query, filters)
        return query

    @staticmethod
    def get_test_student_list(activity_type_id):
        return []

    @staticmethod
    def get_institution_kpis(filters=None):
        """
        [FIXED] KPIs with Strict Identity & Zero State
        """
        base_q = AnalyticsService._get_base_query(filters)
        
        # 1. Total Students (Active) - Sourced from User table directly for normalization
        # Note: 'Total Students' in KPI usually means relevant students context. 
        # But per request, let's keep it scoped to Active students in DB matching Dept/Batch filters.
        total_students_q = db.session.query(func.count(User.id)).filter(User.role == 'student', User.is_active == True)
        if filters:
            if filters.get('department'):
                total_students_q = total_students_q.filter(User.department == filters['department'])
            if filters.get('batch'):
                total_students_q = total_students_q.filter(User.batch_year == str(filters['batch']))
        total_students = total_students_q.scalar() or 0

        # 2. Total Events - Strict Identity
        total_events = base_q.with_entities(
            func.count(distinct(AnalyticsService._get_event_identity_expr()))
        ).scalar() or 0
        
        # 3. Total Participations
        total_participations = base_q.with_entities(func.count(StudentActivity.id)).scalar() or 0
        
        # 4. Unique Students
        unique_students = base_q.with_entities(func.count(distinct(StudentActivity.student_id))).scalar() or 0
        
        # 5. Engagement Rate
        engagement_rate = round((unique_students / total_students * 100), 1) if total_students > 0 else 0
        
        # 6. Avg Activities
        avg_activities_per_student = round((total_participations / unique_students), 2) if unique_students > 0 else 0
        
        # 7. Verified Rate
        verified_count = base_q.filter(or_(
            StudentActivity.status == 'faculty_verified',
            StudentActivity.status == 'auto_verified'
        )).with_entities(func.count(StudentActivity.id)).scalar() or 0
        
        verified_rate = round((verified_count / total_participations * 100), 1) if total_participations > 0 else 0

        print(f"DEBUG KPI: Events={total_events}, Part={total_participations}, Unique={unique_students}")

        return {
            "total_students": total_students,
            "total_events": total_events,
            "total_participations": total_participations,
            "unique_students": unique_students,
            "engagement_rate": engagement_rate,
            "avg_activities_per_student": avg_activities_per_student,
            "verified_rate": verified_rate
        }

    @staticmethod
    def get_event_distribution(filters=None):
        """
        [FIXED] Group by Category with Strict Identity
        """
        base_q = AnalyticsService._get_base_query(filters)
        base_q = base_q.outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)
        
        cat_name = func.coalesce(ActivityType.name, 'Other / Custom').label('category_name')
        
        query = base_q.with_entities(
            cat_name,
            func.count(distinct(AnalyticsService._get_event_identity_expr())).label('total_events'),
            func.count(StudentActivity.id).label('participations')
        ).group_by(cat_name)
        
        results = query.all()
        if not results:
            return {"empty": True}
            
        return [{
            "category": r.category_name, 
            "count": r.total_events,
            "participations": r.participations
        } for r in results]

    @staticmethod
    def get_department_participation(filters=None):
        """
        [FIXED] Dept Participation
        """
        # Note: Must align with _get_base_query logic, but group by Dept.
        # Calling _get_base_query ensures filters are applied.
        base_q = AnalyticsService._get_base_query(filters)
        
        query = base_q.with_entities(
            User.department,
            func.count(distinct(StudentActivity.student_id)).label('participated_students'),
            func.count(distinct(AnalyticsService._get_event_identity_expr())).label('events'),
            func.count(StudentActivity.id).label('participations')
        ).group_by(User.department)
        
        results = query.all()
        if not results:
            return {"empty": True}

        # Fetch total students per dept for normalization (Active Only context)
        all_depts = db.session.query(User.department, func.count(User.id))\
            .filter(User.role == 'student', User.is_active == True)\
            .group_by(User.department).all()
        dept_counts = {r[0]: r[1] for r in all_depts if r[0]}
        
        data = []
        for r in results:
            if not r.department: continue
            total = dept_counts.get(r.department, 0)
            rate = round((r.participated_students / total * 100), 1) if total > 0 else 0
            
            data.append({
                "department": r.department,
                "engagement_percent": rate,
                "participated": r.participated_students,
                "events": r.events,
                "participations": r.participations,
                "unique": r.participated_students, # alias for excel
                "total": total
            })
            
        return sorted(data, key=lambda x: x['engagement_percent'], reverse=True)

    @staticmethod
    def get_yearly_trend(filters=None):
        """
        [FIXED] Yearly Trend with Null Handling (Year 0)
        """
        base_q = AnalyticsService._get_base_query(filters)
        
        event_date = AnalyticsService._get_event_date_expr()
        year_expr = extract('year', event_date).label('year')
        
        query = base_q.with_entities(
            year_expr,
            func.count(distinct(AnalyticsService._get_event_identity_expr())).label('total_events'),
            func.count(StudentActivity.id).label('total_participations')
        ).group_by(year_expr).order_by(year_expr)
        
        results = query.all()
        if not results:
            return {"empty": True}
            
        return [{
            "year": int(r.year) if r.year != 0 else "Unspecified",
            "total_events": r.total_events,
            "total_participations": r.total_participations
        } for r in results]

    @staticmethod
    def get_verification_summary(filters=None):
        """
        [FIXED] Verification Logic
        """
        base_q = AnalyticsService._get_base_query(filters)
        
        query = base_q.with_entities(
            func.sum(case((or_(StudentActivity.status == 'faculty_verified', StudentActivity.status == 'auto_verified'), 1), else_=0)),
            func.sum(case((StudentActivity.status == 'pending', 1), else_=0)),
            func.sum(case((StudentActivity.status == 'rejected', 1), else_=0))
        )
        
        row = query.first()
        if not row:
             return {"empty": True}
             
        verified = int(row[0] or 0)
        pending = int(row[1] or 0)
        rejected = int(row[2] or 0)
        
        if (verified + pending + rejected) == 0:
            return {"empty": True}

        return {
            "verified": verified,
            "not_verified": pending + rejected,
            "details": {"pending": pending, "rejected": rejected}
        }

    @staticmethod
    def get_student_list(category_name=None, department=None, page=1, per_page=20, filters=None, search=None, status=None, paginate=True):
        """
        [FIXED] Drilldown List with DEBUG LOGGING
        """
        print(f"DEBUG SVC: get_student_list args: cat={category_name}, dept={department}, search={search}, status={status}")
        
        # 1. Base Query with Scope & Filters
        base_q = AnalyticsService._get_base_query(filters)
        # Note: _get_base_query ALREADY joins User.
        
        print(f"DEBUG SVC: Base Count (Filtered): {base_q.count()}")
        
        # 2. Additional Drilldown Filters (If not covered by main filters)
        # These come from table-specific interactions
        if department and department != 'All':
            base_q = base_q.filter(User.department == department)
        
        if status and status != 'All':
            # Map status string if needed, currently direct match
            base_q = base_q.filter(StudentActivity.status == status)

        if category_name and category_name != 'All':
            if category_name == 'Other / Custom':
                base_q = base_q.outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)
                base_q = base_q.filter(or_(ActivityType.id.is_(None), ActivityType.name.is_(None)))
            else:
                base_q = base_q.join(ActivityType, StudentActivity.activity_type_id == ActivityType.id)
                base_q = base_q.filter(ActivityType.name == category_name)
        
        if search:
            search_term = f"%{search}%"
            base_q = base_q.filter(or_(
                User.full_name.ilike(search_term),
                User.institution_id.ilike(search_term),
                StudentActivity.title.ilike(search_term)
            ))
            
        print(f"DEBUG SVC: Final Count Before Pagination: {base_q.count()}")

        query = base_q.order_by(AnalyticsService._get_event_date_expr().desc())
        
        if not paginate:
            return query.all()
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            "students": [{
                "student_name": item.student.full_name,
                "roll_number": item.student.institution_id,
                "department": item.student.department,
                "title": item.title,
                "status": item.status,
                "category": item.activity_type.name if item.activity_type else (item.custom_category or 'Other'),
                "date": str(item.start_date or item.created_at.date())
            } for item in pagination.items],
            "total_pages": pagination.pages,
            "current_page": pagination.page,
            "total_records": pagination.total
        }

    @staticmethod
    def _get_event_summary_list(filters=None):
        """
        Helper for Sheet 2: Event Summary
        Groups strictly by Identity.
        """
        base_q = AnalyticsService._get_base_query(filters)
        base_q = base_q.outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)
        
        event_date_expr = AnalyticsService._get_event_date_expr()
        identity_expr = AnalyticsService._get_event_identity_expr()
        
        q = base_q.with_entities(
            # Aggregate non-grouped columns to satisfy SQL Grouping rules
            func.max(func.coalesce(ActivityType.name, StudentActivity.custom_category)).label('category'),
            func.max(case((ActivityType.id.isnot(None), literal('')), else_=func.lower(func.trim(StudentActivity.title)))).label('title_key'),
            func.max(StudentActivity.title).label('raw_title'),
            func.max(event_date_expr).label('date'), # Date is part of identity, so max(date) == date
            
            func.count(StudentActivity.id).label('participations'),
            func.count(distinct(StudentActivity.student_id)).label('unique_students'),
             func.sum(case((or_(StudentActivity.status == 'faculty_verified', StudentActivity.status == 'auto_verified'), 1), else_=0)).label('verified_count')
        ).group_by(
            identity_expr
        )
        
        results = q.all()
        
        # Formatting for Excel
        data = []
        for r in results:
            display_title = r.category if r.title_key == '' else r.raw_title
            
            data.append({
                "Event Category": r.category,
                "Event Title": display_title, 
                "Event Date": r.date,
                "Total Participants": r.participations,
                "Unique Students": r.unique_students,
                "Verified Count": int(r.verified_count or 0),
                "Engagement %": f"{round(r.unique_students/r.participations*100, 1) if r.participations else 0}%"
            })
        return data

    @staticmethod
    def generate_naac_excel(filters=None, export_type='full'):
        """
        [FIXED] 4 Clean Sheets using Pandas & Service Reusability
        """
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        
        # --- SHEET 1: Institutional Summary ---
        if export_type in ['full']:
            kpis = AnalyticsService.get_institution_kpis(filters)
            s1_data = [{
                "Report Date": datetime.now().strftime("%Y-%m-%d"),
                "Applied Filters": str(filters),
                "Total Students (Active)": kpis['total_students'],
                "Total Events": kpis['total_events'],
                "Total Participations": kpis['total_participations'],
                "Unique Students": kpis['unique_students'],
                "Engagement Rate": f"{kpis['engagement_rate']}%",
                "Verified Rate": f"{kpis['verified_rate']}%",
                "Avg Activities/Student": kpis['avg_activities_per_student']
            }]
            df1 = pd.DataFrame(s1_data)
            df1.to_excel(writer, sheet_name='Institutional_Summary', index=False)
            AnalyticsService._format_excel_sheet(writer, df1, 'Institutional_Summary')

        # --- SHEET 2: Event Summary ---
        if export_type in ['full', 'events']:
            s2_data = AnalyticsService._get_event_summary_list(filters)
            df2 = pd.DataFrame(s2_data)
            df2.to_excel(writer, sheet_name='Event_Summary', index=False)
            AnalyticsService._format_excel_sheet(writer, df2, 'Event_Summary')

        # --- SHEET 3: Department Summary ---
        if export_type in ['full']:
            dept_stats = AnalyticsService.get_department_participation(filters)
            if isinstance(dept_stats, dict) and dept_stats.get('empty'):
                 dept_stats = []
            
            s3_data = [{
                "Department": d['department'],
                "Total Students": d['total'],
                "Participated Students": d.get('unique', 0),
                "Engagement %": f"{d['engagement_percent']}%",
                "Total Events": d['events'],
                "Total Participations": d['participations']
            } for d in dept_stats]
            
            df3 = pd.DataFrame(s3_data)
            df3.to_excel(writer, sheet_name='Department_Summary', index=False)
            AnalyticsService._format_excel_sheet(writer, df3, 'Department_Summary')
        
        # --- SHEET 4: Student Participation ---
        if export_type in ['full', 'students']:
            raw_rows = AnalyticsService.get_student_list(paginate=False, filters=filters)
            
            s4_data = []
            for item in raw_rows:
                # Generate Certificate Link
                cert_link = "Not Available"
                if item.certificate_file:
                    try:
                        cert_link = url_for('student.serve_upload', filename=item.certificate_file, _external=True)
                    except Exception:
                        cert_link = item.certificate_file 

                s4_data.append({
                    "Student Name": item.student.full_name,
                    "Roll No": item.student.institution_id,
                    "Department": item.student.department,
                    "Batch": item.student.batch_year, 
                    "Activity Title": item.title,
                    "Category": item.activity_type.name if item.activity_type else (item.custom_category or 'Other'),
                    "Date": str(item.start_date or item.created_at.date()),
                    "Status": item.status,
                    "Verification Mode": item.verification_mode,
                    "Certificate Link": cert_link
                })
            
            df4 = pd.DataFrame(s4_data)
            df4.to_excel(writer, sheet_name='Student_Participation', index=False)
            AnalyticsService._format_excel_sheet(writer, df4, 'Student_Participation')
        
        writer.close()
        output.seek(0)
        return output
```

## 3. Frontend Template (`app/templates/analytics_dashboard.html`)
The HTML structure using Bootstrap and Chart.js integration.

```html
{% extends "base.html" %}

{% block title %}NAAC Analytics | Accreditation Intelligence{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard.css') }}">
<!-- DataTables CSS -->
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css">
<link rel="stylesheet" href="https://cdn.datatables.net/responsive/2.4.1/css/responsive.bootstrap5.min.css">
<link rel="stylesheet" href="https://cdn.datatables.net/buttons/2.3.6/css/buttons.bootstrap5.min.css">
{% endblock %}

{% block content %}
<div class="container-fluid py-4">

    <!-- HEADER -->
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1 class="h4 mb-0 text-dark fw-bold" style="letter-spacing: -0.5px;">Institutional Overview</h1>
            <p class="text-sm text-muted mb-0">Criterion 3 & 5 Real-time Intelligence</p>
        </div>
        <div class="btn-group shadow-sm">
            <button type="button" class="btn btn-success fw-bold px-4 dropdown-toggle" data-bs-toggle="dropdown"
                aria-expanded="false">
                <i class="fas fa-file-excel me-2"></i> Export Report
            </button>
            <ul class="dropdown-menu dropdown-menu-end">
                <li><a class="dropdown-item" href="#" id="exportFull" target="_blank">Full NAAC Report</a></li>
                <li>
                    <hr class="dropdown-divider">
                </li>
                <li><a class="dropdown-item" href="#" id="exportStudents" target="_blank">Student List Only</a></li>
                <li><a class="dropdown-item" href="#" id="exportEvents" target="_blank">Event Summary Only</a></li>
            </ul>
        </div>
    </div>

    <!-- 1. FILTER BAR REDESIGN -->
    <div class="card filter-card p-3 mb-3 section-spacing border-0 shadow-sm"
        style="background: #fff; border-radius: 12px;">
        <form id="filterForm" class="row g-3 align-items-end">
            <!-- Search -->
            <div class="col-lg-3 col-md-6">
                <label class="filter-label fw-bold text-xs text-uppercase text-gray-500">Search</label>
                <div class="input-group">
                    <span class="input-group-text bg-light border-end-0"><i
                            class="fas fa-search text-secondary"></i></span>
                    <input type="text" class="form-control border-start-0 bg-light" id="tableSearch"
                        placeholder="Student Name / ID...">
                </div>
            </div>

            <!-- Department -->
            <div class="col-lg-2 col-md-4">
                <label class="filter-label fw-bold text-xs text-uppercase text-gray-500">Department</label>
                <select class="form-select bg-light border-0" id="deptSelect" name="department">
                    <option value="">All Departments</option>
                    {% for dept in departments %}
                    <option value="{{ dept }}">{{ dept }}</option>
                    {% endfor %}
                </select>
            </div>

            <!-- Batch -->
            <div class="col-lg-2 col-md-4">
                <label class="filter-label fw-bold text-xs text-uppercase text-gray-500">Batch</label>
                <input type="number" class="form-control bg-light border-0" id="batchInput" placeholder="e.g. 2025">
            </div>

            <!-- Status -->
            <div class="col-lg-2 col-md-4">
                <label class="filter-label fw-bold text-xs text-uppercase text-gray-500">Verification</label>
                <select class="form-select bg-light border-0" id="statusSelect" name="status">
                    <option value="">All Status</option>
                    <option value="faculty_verified">Verified Only</option>
                    <option value="pending">Pending</option>
                    <option value="rejected">Rejected</option>
                </select>
            </div>

            <!-- Date Range -->
            <div class="col-lg-3 col-md-6">
                <label class="filter-label fw-bold text-xs text-uppercase text-gray-500">Date Range</label>
                <div class="input-group">
                    <input type="date" class="form-control bg-light border-0" id="dateFrom">
                    <span class="input-group-text bg-light border-0 text-xs">to</span>
                    <input type="date" class="form-control bg-light border-0" id="dateTo">
                </div>
            </div>

            <!-- Actions -->
            <div class="col-12 d-flex justify-content-end gap-2 mt-3">
                <button type="button" class="btn btn-light btn-sm px-3 text-secondary" onclick="resetFilters()">
                    <i class="fas fa-undo me-1"></i> Reset
                </button>
                <button type="button" class="btn btn-primary btn-sm px-4 fw-bold" onclick="reloadDashboard()">
                    <i class="fas fa-filter me-1"></i> Apply Filters
                </button>
            </div>
        </form>
    </div>

    <!-- ACTIVE FILTERS BANNER -->
    <div id="activeFiltersBanner"
        class="alert alert-info d-flex align-items-center py-2 px-3 mb-4 rounded-3 text-sm shadow-sm border-0"
        style="background: rgba(54, 185, 204, 0.1); color: #2c9faf; display: none !important;">
        <i class="fas fa-info-circle me-2"></i>
        <span>Showing results for: <strong id="filterText">All Data</strong></span>
    </div>

    <!-- 2. KPI CARDS REDESIGN -->
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-4 g-4 mb-4">
        <!-- Events -->
        <div class="col">
            <div class="kpi-card purple h-100">
                <div class="kpi-title">Total Events</div>
                <div class="d-flex align-items-center justify-content-between">
                    <div class="kpi-value" id="kpiEvents">0</div>
                    <i class="fas fa-calendar-check fa-2x text-gray-300 opacity-25"></i>
                </div>
            </div>
        </div>

        <!-- Participations -->
        <div class="col">
            <div class="kpi-card info h-100">
                <div class="kpi-title">Total Participations</div>
                <div class="d-flex align-items-center justify-content-between">
                    <div class="kpi-value" id="kpiParticipations">0</div>
                    <i class="fas fa-users fa-2x text-gray-300 opacity-25"></i>
                </div>
            </div>
        </div>

        <!-- Students -->
        <div class="col">
            <div class="kpi-card warning h-100">
                <div class="kpi-title">Active Students</div>
                <div class="d-flex align-items-center justify-content-between">
                    <div class="kpi-value" id="kpiStudents">0</div>
                    <i class="fas fa-user-graduate fa-2x text-gray-300 opacity-25"></i>
                </div>
            </div>
        </div>

        <!-- Verification -->
        <div class="col">
            <div class="kpi-card success h-100">
                <div class="kpi-title">Verified Rate</div>
                <div class="d-flex align-items-center justify-content-between">
                    <div class="kpi-value" id="kpiVerified">0%</div>
                    <i class="fas fa-check-circle fa-2x text-gray-300 opacity-25"></i>
                </div>
            </div>
        </div>
    </div>

    <!-- ROW 2: MAIN CHARTS -->
    <div class="row g-4 section-spacing mb-4">
        <!-- Row 1 Left: Events vs Participations -->
        <div class="col-lg-6">
            <div class="chart-panel h-100 shadow-sm border-0">
                <div class="chart-header bg-white border-bottom-0 pt-3 px-3 fw-bold text-dark">
                    Activity Breakdown
                </div>
                <div class="chart-container-fixed position-relative">
                    <canvas id="eventChart"></canvas>
                    <div id="eventChart-empty" class="empty-state-overlay d-none">
                        <i class="fas fa-chart-pie mb-2 text-gray-300 fa-2x"></i>
                        <p class="text-muted text-xs">No Data Available</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Row 1 Right: Yearly Trend -->
        <div class="col-lg-6">
            <div class="chart-panel h-100 shadow-sm border-0">
                <div class="chart-header bg-white border-bottom-0 pt-3 px-3 fw-bold text-dark">
                    Yearly Participation Trend
                </div>
                <div class="chart-container-fixed position-relative">
                    <canvas id="trendChart"></canvas>
                    <div id="trendChart-empty" class="empty-state-overlay d-none">
                        <i class="fas fa-chart-line mb-2 text-gray-300 fa-2x"></i>
                        <p class="text-muted text-xs">No Data Available</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Row 2 Left: Department Engagement -->
        <div class="col-lg-6">
            <div class="chart-panel h-100 shadow-sm border-0">
                <div class="chart-header bg-white border-bottom-0 pt-3 px-3 fw-bold text-dark">
                    Departmental Engagement
                </div>
                <div class="chart-container-fixed position-relative">
                    <canvas id="deptChart"></canvas>
                    <div id="deptChart-empty" class="empty-state-overlay d-none">
                        <i class="fas fa-chart-bar mb-2 text-gray-300 fa-2x"></i>
                        <p class="text-muted text-xs">No Data Available</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Row 2 Right: Verification Status -->
        <div class="col-lg-6">
            <div class="chart-panel h-100 shadow-sm border-0">
                <div class="chart-header bg-white border-bottom-0 pt-3 px-3 fw-bold text-dark">
                    Verification Status
                </div>
                <div class="chart-container-fixed position-relative">
                    <canvas id="verifyChart"></canvas>
                    <div id="verifyChart-empty" class="empty-state-overlay d-none">
                        <i class="fas fa-clipboard-check mb-2 text-gray-300 fa-2x"></i>
                        <p class="text-muted text-xs">No Data Available</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- DRILLDOWN / RECORD LIST -->
    <div class="card table-card mb-5 border-0 shadow-sm">
        <div class="card-header bg-white py-3 border-0 d-flex justify-content-between align-items-center">
            <h6 class="m-0 fw-bold text-primary">Student Participation Details</h6>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table id="studentTable" class="table table-hover w-100 align-middle">
                    <thead class="bg-light text-uppercase text-xs fw-bold text-secondary">
                        <tr>
                            <th class="border-0">Student Name</th>
                            <th class="border-0">Department</th>
                            <th class="border-0">Activity Title</th>
                            <th class="border-0">Date</th>
                            <th class="border-0">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Populated by DataTables via JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    {% endblock %}

    {% block scripts %}
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <!-- DataTables JS -->
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/dataTables.bootstrap5.min.js"></script>
    <script src="https://cdn.datatables.net/responsive/2.4.1/js/dataTables.responsive.min.js"></script>
    <script src="https://cdn.datatables.net/buttons/2.3.6/js/dataTables.buttons.min.js"></script>
    <script src="https://cdn.datatables.net/buttons/2.3.6/js/buttons.bootstrap5.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
    <script src="https://cdn.datatables.net/buttons/2.3.6/js/buttons.html5.min.js"></script>

    <script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
    {% endblock %}
```

## 4. Frontend Logic (`app/static/js/dashboard.js`)
Handles interactivity, chart rendering, data fetching, and dynamic filtering.

```javascript
// Dashboard Logic with DataTables and Chart.js

// Global Chart Instances
let charts = {
    dist: null,
    trend: null,
    dept: null,
    verify: null
};

// Global DataTable Instance
let studentTable = null;

const API = {
    DIST: '/analytics/api/distribution',
    TREND: '/analytics/api/yearly-trend',
    KPIS: '/analytics/api/kpis',
    LIST: '/analytics/api/student-list',
    DEPT: '/analytics/api/department-participation',
    VERIFY: '/analytics/api/verification-summary'
};

// Set Chart Text Color
if (Chart.defaults) {
    Chart.defaults.color = '#858796';
    Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
}

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

function initDashboard() {
    // Initialize DataTable (No Buttons)
    initDataTable();

    // Reset Filters Button
    window.resetFilters = function () {
        document.getElementById('filterForm').reset();
        reloadDashboard();
    };

    // Initial Load
    reloadDashboard();
}

function initDataTable() {
    studentTable = $('#studentTable').DataTable({
        responsive: true,
        pageLength: 20,
        dom: 'frtip', // No Buttons (B)
        order: [[3, 'desc']], // Date desc
        columns: [
            { data: 'student_name' },
            { data: 'department' },
            {
                data: 'title',
                render: function (data, type, row) {
                    // Show title, maybe add category pill?
                    return `<div><div class="fw-bold text-dark">${data}</div><div class="text-xs text-muted">${row.category || ''}</div></div>`;
                }
            },
            { data: 'date' },
            {
                data: 'status',
                render: function (data) {
                    let badgeClass = 'bg-secondary';
                    if (data === 'faculty_verified' || data === 'auto_verified') badgeClass = 'bg-success';
                    else if (data === 'pending') badgeClass = 'bg-warning text-dark';
                    else if (data === 'rejected') badgeClass = 'bg-danger';

                    const statusText = data ? data.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'N/A';
                    return `<span class="badge ${badgeClass}">${statusText}</span>`;
                }
            }
        ],
        language: {
            search: "",
            searchPlaceholder: "Search within results...",
            zeroRecords: "No matching records found",
            emptyTable: "No data available in table"
        }
    });

    // Link custom search input to DataTable
    $('#tableSearch').on('keyup', function () {
        studentTable.search(this.value).draw();
    });
}

function reloadDashboard() {
    // Gather Filter Values
    const filters = new URLSearchParams();
    const activeFilters = [];

    // Status
    const status = document.getElementById('statusSelect').value;
    if (status) {
        filters.append('status', status);
        activeFilters.push(`Status: ${status}`);
    }

    // Department
    const dept = document.getElementById('deptSelect').value;
    if (dept) {
        filters.append('department', dept);
        activeFilters.push(`Dept: ${dept}`);
    }

    // Batch
    const batch = document.getElementById('batchInput').value;
    if (batch) {
        filters.append('batch', batch);
        activeFilters.push(`Batch: ${batch}`);
    }

    // Date Range
    const start = document.getElementById('dateFrom').value;
    const end = document.getElementById('dateTo').value;
    if (start) {
        filters.append('start_date', start);
        activeFilters.push(`From: ${start}`);
    }
    if (end) {
        filters.append('end_date', end);
        activeFilters.push(`To: ${end}`);
    }

    // Update Active Filters Banner
    const banner = document.getElementById('activeFiltersBanner');
    const bannerText = document.getElementById('filterText');

    // Check if we have active filters
    if (activeFilters.length > 0) {
        banner.style.display = 'flex';
        banner.classList.remove('d-none');
        bannerText.textContent = activeFilters.join(' | ');
    } else {
        banner.style.display = 'none';
        banner.classList.add('d-none');
        bannerText.textContent = 'All Data';
    }

    // Update Export URLs
    const exportBase = '/analytics/export-naac';
    const queryString = filters.toString();

    // Use & if queryString exists, else nothing (but base url usually needs ?)
    // Our route is /analytics/export-naac?type=...&filters...

    const setHref = (id, type) => {
        const el = document.getElementById(id);
        if (el) {
            el.href = `${exportBase}?type=${type}&${queryString}`;
        }
    };

    setHref('exportFull', 'full');
    setHref('exportStudents', 'students');
    setHref('exportEvents', 'events');

    // Reload Components
    loadKPIs(filters);

    // Clear charts before loading to prevent 'ghosting' or race conditions? 
    // No, renderChart handles destruction.
    loadCharts(filters);

    loadTableData(filters);
}

async function fetchJSON(url, params) {
    try {
        const response = await fetch(`${url}?${params.toString()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (e) {
        console.error("API Error:", url, e);
        return null;
    }
}

async function loadKPIs(params) {
    const data = await fetchJSON(API.KPIS, params);
    if (!data) return;

    updateKPI('kpiEvents', data.total_events || 0);
    updateKPI('kpiParticipations', data.total_participations || 0);
    updateKPI('kpiStudents', data.total_students || 0);
    updateKPI('kpiVerified', (data.verified_rate || 0) + '%');
}

function updateKPI(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

async function loadTableData(params) {
    params.set('per_page', 500); // Fetch reasonable max for client side table

    try {
        const data = await fetchJSON(API.LIST, params);

        if (studentTable) {
            studentTable.clear();
            if (data && data.students) {
                studentTable.rows.add(data.students);
            }
            studentTable.draw();
        }
    } catch (e) { console.error("Table Error", e); }
}

async function loadCharts(params) {
    // 1. Activity Breakdown
    try {
        const distData = await fetchJSON(API.DIST, params);
        if (Array.isArray(distData) && distData.length > 0) {
            renderChart('dist', 'eventChart', 'doughnut', {
                labels: distData.map(d => d.category),
                datasets: [{
                    data: distData.map(d => d.count),
                    backgroundColor: ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796']
                }]
            });
        } else {
            showEmptyState('eventChart');
        }
    } catch (e) { showEmptyState('eventChart'); }

    // 2. Yearly Trend
    try {
        const trendData = await fetchJSON(API.TREND, params);
        if (Array.isArray(trendData) && trendData.length > 0) {
            renderChart('trend', 'trendChart', 'line', {
                labels: trendData.map(d => d.year),
                datasets: [{
                    label: 'Participations',
                    data: trendData.map(d => d.total_participations),
                    borderColor: '#4e73df',
                    tension: 0.3,
                    fill: true,
                    backgroundColor: 'rgba(78, 115, 223, 0.05)'
                }]
            });
        } else {
            showEmptyState('trendChart');
        }
    } catch (e) { showEmptyState('trendChart'); }

    // 3. Dept Engagement
    try {
        const deptData = await fetchJSON(API.DEPT, params);
        if (Array.isArray(deptData) && deptData.length > 0) {
            renderChart('dept', 'deptChart', 'bar', {
                labels: deptData.map(d => d.department),
                datasets: [{
                    label: 'Engagement %',
                    data: deptData.map(d => d.engagement_percent),
                    backgroundColor: '#36b9cc',
                    borderRadius: 4
                }]
            }, {
                indexAxis: 'y',
                scales: { x: { max: 100 } }
            });
        } else {
            showEmptyState('deptChart');
        }
    } catch (e) { showEmptyState('deptChart'); }

    // 4. Verification Status
    try {
        const verifyData = await fetchJSON(API.VERIFY, params);
        if (verifyData && (verifyData.verified > 0 || verifyData.not_verified > 0)) {
            renderChart('verify', 'verifyChart', 'doughnut', {
                labels: ['Verified', 'Not/Pending'],
                datasets: [{
                    data: [verifyData.verified, verifyData.not_verified],
                    backgroundColor: ['#1cc88a', '#e74a3b']
                }]
            }, {
                cutout: '70%'
            });
        } else {
            showEmptyState('verifyChart');
        }
    } catch (e) { showEmptyState('verifyChart'); }
}

function showEmptyState(canvasId) {
    const canvas = document.getElementById(canvasId);
    const overlay = document.getElementById(canvasId + '-empty');

    // Hide Canvas, Show Overlay
    if (canvas) canvas.classList.add('d-none');
    if (overlay) {
        overlay.classList.remove('d-none');
        overlay.style.display = 'flex'; // Ensure flex
    }
}

function renderChart(key, canvasId, type, data, options = {}) {
    // Reset Visibility (Show Canvas, Hide Overlay)
    const canvas = document.getElementById(canvasId);
    const overlay = document.getElementById(canvasId + '-empty');

    if (canvas) canvas.classList.remove('d-none');
    if (overlay) overlay.classList.add('d-none');

    const ctx = canvas;
    if (!ctx) return;

    if (charts[key]) {
        charts[key].destroy();
        charts[key] = null;
    }

    charts[key] = new Chart(ctx, {
        type: type,
        data: data,
        options: {
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            },
            layout: {
                padding: 10
            },
            ...options
        }
    });
}
```
