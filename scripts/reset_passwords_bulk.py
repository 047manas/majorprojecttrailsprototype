
import sys
import os
from werkzeug.security import generate_password_hash

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User

app = create_app()

def reset_all_passwords():
    with app.app_context():
        # 1. Reset Faculty
        faculties = User.query.filter_by(role='faculty').all()
        print(f"🔄 Resetting {len(faculties)} faculty passwords to 'faculty123'...")
        for u in faculties:
            u.password_hash = generate_password_hash('faculty123')
        
        # 2. Reset Students
        students = User.query.filter_by(role='student').all()
        print(f"🔄 Resetting {len(students)} student passwords to 'student123'...")
        for u in students:
            u.password_hash = generate_password_hash('student123')
            
        db.session.commit()
        print("✅ All passwords updated successfully!")

if __name__ == "__main__":
    reset_all_passwords()
