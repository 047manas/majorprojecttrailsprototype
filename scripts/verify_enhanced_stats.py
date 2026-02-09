import sys
import os
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, StudentActivity, ActivityType
from datetime import date

app = create_app()
app.config['TESTING'] = True

def verify_enhanced_stats():
    with app.app_context():
        # Setup Test Data
        # Hardcode known working user
        faculty = User.query.filter_by(email='cseHod@college.edu').first()
        student = User.query.filter_by(role='student', department='CSE').first()
        
        if not faculty or not student:
            print("❌ Setup Failed: Faculty (cseHod@college.edu) or Student not found.")
            return

        print(f"Testing with Faculty: {faculty.email} (Dept: {faculty.department})")

        with app.test_client() as client:
            res = client.post('/login', data={'email': faculty.email, 'password': 'faculty123'}, follow_redirects=True)
            print(f"Login Response: {res.status_code}")
            if "Invalid email or password" in res.get_data(as_text=True):
                 print("❌ Login Failed: Invalid credentials")
            elif "Logged in successfully" in res.get_data(as_text=True):
                 print("✅ Login Successful")
            else:
                 print(f"⚠️ Login Result Unknown: {res.get_data(as_text=True)[:100]}")
            
            # 1. Test Faculty Stats Page
            print("Testing /faculty/stats...")
            res = client.get('/faculty/stats')
            if res.status_code == 200:
                print("✅ /faculty/stats loaded successfully")
                content = res.get_data(as_text=True)
                if f"Dept. Insights: {faculty.department}" in content:
                    print("✅ Department context correct")
                else:
                    print("❌ Department header missing")
            else:
                 print(f"❌ /faculty/stats failed: {res.status_code}")
                 return

            # 2. Test Event Participants View
            # Use a known event title from DB or just test the route logic with dummy data
            # First, check if there's any activity to use as reference
            act = StudentActivity.query.join(User, StudentActivity.student_id == User.id).filter(User.department == faculty.department).first()
            if act:
                title = act.title
                organizer = act.organizer or ''
                issue_date = str(act.issue_date) if act.issue_date else ''
                
                print(f"Testing /faculty/event_participants for '{title}'...")
                url = f"/faculty/event_participants?title={title}&organizer={organizer}&date={issue_date}"
                res = client.get(url)
                
                if res.status_code == 200:
                    print("✅ /faculty/event_participants loaded successfully")
                    content = res.get_data(as_text=True)
                    # Check if student is listed
                    if student.full_name in content:
                         print(f"✅ Student {student.full_name} found in list")
                    else:
                         print(f"⚠️ Student {student.full_name} NOT found in list (might be wrong dept?)")
                else:
                    print(f"❌ /faculty/event_participants failed: {res.status_code}")
            else:
                print("⚠️ No activities found to test Event Participants view.")

if __name__ == "__main__":
    try:
        verify_enhanced_stats()
    except Exception as e:
        print(f"❌ Script Error: {e}")
        import traceback
        traceback.print_exc()
