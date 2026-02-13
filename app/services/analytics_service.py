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

# ... (Previous code remains unchanged until _get_event_summary_list) ...

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
            func.coalesce(ActivityType.name, StudentActivity.custom_category).label('category'),
            # For Title: If Defined, ignore title (use ''), else use actual title
            case((ActivityType.id.isnot(None), literal('')), else_=func.lower(func.trim(StudentActivity.title))).label('title_key'),
            func.max(StudentActivity.title).label('raw_title'), # FIXED: Use Aggregate to avoid GroupingError
            event_date_expr.label('date'),
            func.count(StudentActivity.id).label('participations'),
            func.count(distinct(StudentActivity.student_id)).label('unique_students'),
             func.sum(case((or_(StudentActivity.status == 'faculty_verified', StudentActivity.status == 'auto_verified'), 1), else_=0)).label('verified_count')
        ).group_by(
            identity_expr,
            ActivityType.id, # Explicitly group by ID to allow Name selection
            ActivityType.name,
            StudentActivity.custom_category,
            event_date_expr,
            case((ActivityType.id.isnot(None), literal('')), else_=func.lower(func.trim(StudentActivity.title)))
        )
        
        results = q.all()
        
        # Formatting for Excel
        # Title display: If category matches key (defined), show Category as Title or Generic.
        data = []
        for r in results:
            # If title_key is empty, it was a defined event. We can use Category name as title or leave blank.
            display_title = r.category if r.title_key == '' else r.raw_title
            
            data.append({
                "Event Category": r.category,
                "Event Title": display_title, # Fallback
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
            # Flatten dictionary for dataframe
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
            # Reuse get_department_participation logic? 
            # It returns list of dicts.
            dept_stats = AnalyticsService.get_department_participation(filters)
            if isinstance(dept_stats, dict) and dept_stats.get('empty'):
                 dept_stats = []
            
            # Remap keys for Excel
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
            # Fetch ALL rows (paginate=False)
            raw_rows = AnalyticsService.get_student_list(paginate=False, filters=filters)
            
            s4_data = []
            for item in raw_rows:
                # Generate Certificate Link if file exists
                cert_link = "Not Available"
                if item.certificate_file:
                    try:
                        # Construct external URL for the certificate
                        cert_link = url_for('student.serve_upload', filename=item.certificate_file, _external=True)
                    except Exception:
                        cert_link = item.certificate_file # Fallback to filename if url_for fails context

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

# ... (rest of class)

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
    



