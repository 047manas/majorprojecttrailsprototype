from app import create_app, db
from app.models import StudentActivity, User, ActivityType
from sqlalchemy import func

app = create_app()

with app.app_context():
    print("--- DATA DIAGNOSIS ---")
    
    # 1. Total Activites
    total_activities = db.session.query(StudentActivity).count()
    print(f"Total StudentActivities: {total_activities}")
    
    # 2. Total Users
    total_users = db.session.query(User).count()
    print(f"Total Users: {total_users}")
    
    # 3. Activity Types
    types = db.session.query(ActivityType).all()
    print(f"Activity Types: {[t.name for t in types]}")
    
    # 4. Check for NULL Dates
    null_dates = db.session.query(StudentActivity).filter(StudentActivity.start_date == None).count()
    print(f"Activities with NULL start_date: {null_dates}")
    
    # 5. Check for NULL Activity Types
    null_types = db.session.query(StudentActivity).filter(StudentActivity.activity_type_id == None).count()
    print(f"Activities with NULL activity_type_id: {null_types}")
    
    # 6. Sample Activity
    last = db.session.query(StudentActivity).first()
    if last:
        print(f"Sample Activity: Title='{last.title}', Date='{last.start_date}', TypeID='{last.activity_type_id}'")
    else:
        print("No activities found.")
