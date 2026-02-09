
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User

app = create_app()

def list_faculty():
    with app.app_context():
        users = User.query.filter_by(role='faculty').all()
        print(f"Found {len(users)} faculty members:")
        for u in users:
            print(f"- {u.email} (Dept: {u.department})")

if __name__ == "__main__":
    list_faculty()
