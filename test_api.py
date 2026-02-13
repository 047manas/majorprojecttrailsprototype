from app import create_app, db
from app.models import User, StudentActivity
from flask import json
from flask_login import login_user

app = create_app()

with app.app_context():
    print("--- TEST API ---")
    
    # 1. Find a student who has activities
    student_id = db.session.query(StudentActivity.student_id).first()[0]
    user = User.query.get(student_id)
    print(f"Testing as user: {user.email} (Role: {user.role})")
    
    # 2. Test Client
    with app.test_client() as client:
        # Login
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
            
        # 3. Call Event Distribution API
        resp = client.get('/analytics/api/distribution')
        print(f"Status Code: {resp.status_code}")
        print(f"Response Data: {resp.data.decode('utf-8')}")
