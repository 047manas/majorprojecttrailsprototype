
import sys
import os
from werkzeug.security import generate_password_hash

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User

app = create_app()

def reset_hod_password():
    with app.app_context():
        # Reset for both potential test users
        for email in ['cseHod@college.edu', 'facultyLMS@college.edu']:
            user = User.query.filter_by(email=email).first()
            if user:
                 user.password_hash = generate_password_hash('password123')
                 db.session.commit()
                 print(f"✅ Password for {email} reset to 'password123'")
        else:
            print(f"❌ User {email} not found!")

if __name__ == "__main__":
    reset_hod_password()
