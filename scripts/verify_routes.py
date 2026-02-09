import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User
from flask import url_for

app = create_app()

def test_routes():
    with app.test_client() as client:
        with app.app_context():
            # Get Users
            admin = User.query.filter_by(role='admin').first()
            hod = User.query.filter_by(position='hod').first()
            if not hod:
                # Fallback if seed data different (e.g. HOD CSE)
                hod = User.query.filter(User.email.like('hod%')).first()
            student = User.query.filter_by(role='student').first()

            print(f"Testing with Admin: {admin.email}")
            print(f"Testing with HOD: {hod.email}")
            print(f"Testing with Student: {student.email}")

            # 1. Login as Student
            # (Assuming login works via session, or we can mock login_user if we use flask_login.test_client_mixin? 
            #  Simpler to just use login route if possible, but we don't know raw password for seeded users easily 
            #  Wait, init_db set password to 'password' or 'admin123'. I can use that.)
            
            # Helper to login
            def login(email, password):
                client.get('/logout', follow_redirects=True) # Ensure logout first
                return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

            # C. Admin Access Only (Debugging)
            login(admin.email, 'admin123')
            print("Logged in as Admin. Requesting /admin/stats...")
            res = client.get('/admin/stats')
            print(f"Admin -> /admin/stats: {res.status_code}")
            if res.status_code != 200:
                print(f"Error Response: {res.text}") # Print traceback if debug mode

            res = client.get('/admin/stats/export')
            print(f"Admin -> /admin/stats/export: {res.status_code}")

if __name__ == "__main__":
    try:
        test_routes()
        print("\n✅ Verification Complete")
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()
