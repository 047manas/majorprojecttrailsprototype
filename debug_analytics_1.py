from app import create_app, db
from app.models import User, StudentActivity
import os

app = create_app()
with app.app_context():
    print("--- STEP 1: Verify Data Exists ---")
    print(f"Total Users: {User.query.count()}")
    print(f"Total Activities: {StudentActivity.query.count()}")
    
    print("\nSample Activities:")
    for a in StudentActivity.query.limit(5).all():
        print(f"ID: {a.id}, Start: {a.start_date}, Created: {a.created_at}")

    print("\n--- STEP 2: Verify DB URL ---")
    print(f"DB Engine URL: {db.engine.url}")

    print("\n--- STEP 5: Check NULL start_date ---")
    null_start_date = StudentActivity.query.filter(StudentActivity.start_date == None).count()
    print(f"Activities with NULL start_date: {null_start_date}")
