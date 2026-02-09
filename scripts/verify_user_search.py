import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User

app = create_app()
app.config['TESTING'] = True

def verify_search():
    with app.test_client() as client:
        with app.app_context():
            # Login as Admin
            admin = User.query.filter_by(role='admin').first()
            if not admin:
                print("❌ No admin user found for testing.")
                return

            client.post('/login', data={'email': admin.email, 'password': 'admin123'}, follow_redirects=True)
            print(f"Logged in as {admin.email}")

            # Test 1: Load Page without search
            res = client.get('/admin/users')
            if res.status_code == 200:
                print("✅ /admin/users loaded successfully")
            else:
                print(f"❌ /admin/users failed: {res.status_code}")

            # Test 2: Search for Admin by name
            search_term = admin.full_name.split()[0] # First name
            res = client.get(f'/admin/users?search={search_term}')
            if res.status_code == 200:
                 # In a real DOM check we'd parse content, but status 200 confirms route didn't crash
                print(f"✅ Search for '{search_term}' returned 200 OK")
            else:
                print(f"❌ Search for '{search_term}' failed: {res.status_code}")

            # Test 3: Search for non-existent user
            res = client.get('/admin/users?search=NONEXISTENTUSER12345')
            if res.status_code == 200:
                print("✅ Search for non-existent user returned 200 OK")
            else:
                print(f"❌ Search for non-existent user failed: {res.status_code}")

if __name__ == "__main__":
    try:
        verify_search()
        print("\nVerification Script Completed.")
    except Exception as e:
        print(f"\n❌ Script Failed: {e}")
        import traceback
        traceback.print_exc()
