import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, StudentActivity, ActivityType
from sqlalchemy import func, case, distinct, or_
from datetime import datetime

app = create_app()

def test_admin_query():
    with app.app_context():
        print("Testing Dept Overview Query...")
        try:
            # Replicating logic
            dept_overview_q = db.session.query(
                User.department,
                func.count(distinct(User.id)).label('total_students'),
                func.count(distinct(case((StudentActivity.id != None, StudentActivity.student_id), else_=None))).label('participating_students'),
                func.count(StudentActivity.id).label('total_certs'),
                func.sum(case((StudentActivity.status == 'faculty_verified', 1), else_=0)).label('approved'),
                func.sum(case((StudentActivity.status == 'pending', 1), else_=0)).label('pending'),
                func.sum(case((StudentActivity.status == 'rejected', 1), else_=0)).label('rejected')
            ).select_from(User).outerjoin(StudentActivity, User.id == StudentActivity.student_id)
            dept_overview = dept_overview_q.group_by(User.department).all()
            print("Dept Overview Query Success")
        except Exception as e:
            print(f"Dept Overview Query Failed: {e}")
            import traceback
            traceback.print_exc()

        print("Testing Trend Stats Query...")
        try:
            # Replicating trend logic
            # Note: extract might be shadowed in routes.py, so we test func.extract
            trend_stats = db.session.query(
                func.extract('year', StudentActivity.created_at).label('year'),
                func.extract('month', StudentActivity.created_at).label('month'),
                func.count(StudentActivity.id)
            ).select_from(StudentActivity)
            trend_stats = trend_stats.group_by('year', 'month').order_by('year', 'month').all()
            print("Trend Stats Query Success")
        except Exception as e:
            print(f"Trend Stats Query Failed: {e}")
            import traceback
            traceback.print_exc()

        print("Testing Detailed Certs Query...")
        try:
            detailed_certs_q = db.session.query(
                User.full_name, User.institution_id, User.department, User.batch_year, 
                StudentActivity.title, func.coalesce(ActivityType.name, StudentActivity.custom_category).label('type_name'),
                StudentActivity.organizer, StudentActivity.issue_date, StudentActivity.status,
                StudentActivity.approved_at
            ).join(User, StudentActivity.student_id == User.id).outerjoin(ActivityType)
            detailed_certs = detailed_certs_q.limit(5).all()
            print("Detailed Certs Query Success")
        except Exception as e:
            print(f"Detailed Certs Query Failed: {e}")
            import traceback
            traceback.print_exc()

        print("Testing Participating Students Query...")
        try:
            # Replicate apply_admin_filters for this specific query
            part_q = db.session.query(distinct(StudentActivity.student_id))
            part_q = part_q.join(User, StudentActivity.student_id == User.id)
            # No filters applied in simple test
            count = part_q.count()
            print(f"Participating Students Query Success: {count}")
        except Exception as e:
            print(f"Participating Students Query Failed: {e}")
            import traceback
            traceback.print_exc()
            
        print("Testing Status Stats Query...")
        try:
             status_stats = db.session.query(
                StudentActivity.status, func.count(StudentActivity.id)
            ).select_from(StudentActivity)
             status_stats = status_stats.join(User, StudentActivity.student_id == User.id)
             status_stats = status_stats.group_by(StudentActivity.status).all()
             print(f"Status Stats Query Success: {status_stats}")
        except Exception as e:
            print(f"Status Stats Query Failed: {e}")
            import traceback
            traceback.print_exc()
