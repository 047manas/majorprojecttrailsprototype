from app import create_app, db
from app.models import User, StudentActivity, ActivityType
from sqlalchemy import func, or_
from app.services.analytics_service import AnalyticsService

app = create_app()
with app.app_context():
    print("--- STEP 1: VERIFY DATA ---")
    total_activities = StudentActivity.query.count()
    print(f"Total StudentActivities: {total_activities}")
    
    if total_activities == 0:
        print("CRITICAL: No activities found!")
    else:
        activities = StudentActivity.query.limit(5).all()
        for a in activities:
            print(f"ID: {a.id}, TypeID: {a.activity_type_id}, Title: '{a.title}', StudentID: {a.student_id}, Date: {a.start_date}, Created: {a.created_at}")

    print("\n--- STEP 2: TEST STUDENT LIST QUERY (Direct) ---")
    # Simulate what get_student_list does
    
    # Try fetching ALL first
    try:
        results = AnalyticsService.get_student_list(category_name=None, department=None, page=1, per_page=5)
        print(f"Service Call (No Filters) Total Records: {results.get('total_records')}")
        for s in results.get('students', []):
            print(f" - {s['student_name']} ({s['department']}): {s['title']}")
    except Exception as e:
        print(f"Service Call Failed: {e}")

    # Try fetching with category "Other / Custom" if implied
    print("\n--- Test 'Other / Custom' Category Filter ---")
    try:
        results = AnalyticsService.get_student_list(category_name="Other / Custom", department=None, page=1, per_page=5)
        print(f"Service Call ('Other / Custom') Total Records: {results.get('total_records')}")
    except Exception as e:
         print(f"Service Call Failed: {e}")
         
    # Check distinct Activity Types
    print("\n--- distinct Activity Types ---")
    types = db.session.query(ActivityType.name).distinct().all()
    print([t[0] for t in types])
