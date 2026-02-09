import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, StudentActivity, ActivityType
from datetime import date
import re

app = create_app()
app.config['TESTING'] = True

def verify_unique_count():
    with app.app_context():
        # 1. Get current Admin and Student
        admin = User.query.filter_by(role='admin').first()
        student = User.query.filter_by(role='student').first()
        
        if not admin or not student:
            print("❌ Setup Failed: Admin or Student not found.")
            return

        print(f"Testing with Admin: {admin.email}")

        with app.test_client() as client:
            client.post('/login', data={'email': admin.email, 'password': 'admin123'}, follow_redirects=True)
            
            # 2. Get initial count
            res = client.get('/admin/stats')
            content = res.get_data(as_text=True)
            
            # Extract Unique Activities count using Regex
            # Loop for <h5 class="card-title">Unique Activities</h5>...<p ...>X</p>
            match = re.search(r'Unique Activities</h5>\s*<p class="card-text display-6">\s*(\d+)\s*</p>', content)
            initial_count = int(match.group(1)) if match else 0
            print(f"Initial Unique Activities: {initial_count}")

            # 3. Add 2 Certificates for the SAME Activity (Same Title, Organizer, Date)
            act1 = StudentActivity(
                student_id=student.id,
                title="Duplicate Event 2025",
                organizer="Test Org",
                issue_date=date(2025, 1, 1),
                status="pending",
                certificate_file="test1.pdf"
            )
            act2 = StudentActivity(
                student_id=student.id,
                title="Duplicate Event 2025", # Same Title
                organizer="Test Org",         # Same Organizer
                issue_date=date(2025, 1, 1),  # Same Date
                status="pending",
                certificate_file="test2.pdf"
            )
            
            # 4. Add 1 Certificate for DIFFERENT Activity
            act3 = StudentActivity(
                student_id=student.id,
                title="Unique Event 2025",
                organizer="Test Org",
                issue_date=date(2025, 1, 2), # Different Date
                status="pending",
                certificate_file="test3.pdf"
            )

            db.session.add_all([act1, act2, act3])
            db.session.commit()
            print("Added 3 certificates (2 for Event A, 1 for Event B)")

            # 5. Check Count Again
            res = client.get('/admin/stats')
            content = res.get_data(as_text=True)
            match = re.search(r'Unique Activities</h5>\s*<p class="card-text display-6">\s*(\d+)\s*</p>', content)
            new_count = int(match.group(1)) if match else 0
            print(f"New Unique Activities: {new_count}")

            # 6. Verify
            # Expected increase: +2 (Event A and Event B)
            # act1 and act2 are same event -> +1
            # act3 is new event -> +1
            expected_increase = 2
            actual_increase = new_count - initial_count
            
            if actual_increase == expected_increase:
                print(f"✅ Success: Count increased by {actual_increase} (Expected 2)")
            else:
                print(f"❌ Failure: Count increased by {actual_increase} (Expected 2). Logic might be wrong.")

            # Cleanup
            db.session.delete(act1)
            db.session.delete(act2)
            db.session.delete(act3)
            db.session.commit()
            print("Cleanup complete.")

if __name__ == "__main__":
    try:
        verify_unique_count()
    except Exception as e:
        print(f"❌ Script Error: {e}")
        import traceback
        traceback.print_exc()
