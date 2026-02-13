from app import create_app, db
from app.models import StudentActivity, ActivityType, User
from app.services.analytics_service import AnalyticsService
from sqlalchemy import func, distinct
from flask_login import LoginManager

app = create_app()

# bypass login if needed or manually query
with app.app_context():
    print("--- DEBUG DISTRIBUTION ---")
    
    # 1. Check Activity Types
    types = ActivityType.query.all()
    print(f"Activity Types: {[(t.id, t.name) for t in types]}")
    
    # 2. Check Student Activities with Type
    acts = db.session.query(StudentActivity.id, StudentActivity.activity_type_id, StudentActivity.title).all()
    print(f"Activities: {acts}")

    # 3. Simulate get_event_distribution Query MANUALLY (bypassing role scope)
    # Copying logic from AnalyticsService.get_event_distribution but removing _get_base_query dependency on current_user
    
    base_q = db.session.query(StudentActivity).join(User, StudentActivity.student_id == User.id)
    # Assume admin, so no filter
    
    base_q = base_q.outerjoin(ActivityType, StudentActivity.activity_type_id == ActivityType.id)
    cat_name = func.coalesce(ActivityType.name, 'Other / Custom').label('category_name')
    
    query = base_q.with_entities(
        cat_name,
        func.count(distinct(AnalyticsService._get_event_identity_expr())).label('total_events'),
        func.count(StudentActivity.id).label('participations')
    ).group_by(cat_name)
    
    try:
        results = query.all()
        print("\n--- QUERY RESULTS ---")
        for r in results:
            print(f"Category: {r.category_name} | Events: {r.total_events} | Parts: {r.participations}")
    except Exception as e:
        print(f"Query Failed: {e}")

