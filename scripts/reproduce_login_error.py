import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User

app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing

def reproduce_login():
    with app.test_client() as client:
        with app.app_context():
            # Get a user (e.g. Admin)
            user = User.query.first()
            if not user:
                print("❌ No user found.")
                return

            print(f"Attempting login for {user.email}...")
            # Assuming standard login route behavior
            res = client.post('/login', data={'email': user.email, 'password': 'password'}, follow_redirects=True)
            
            if res.status_code != 200:
                 print(f"❌ Login failed with status {res.status_code}")
                 print(res.get_data(as_text=True)[:1000])
            else:
                 # Check if we are redirected to dashboard or still on login page (if auth failed)
                 # If error occurred, it might be a 500 error page or a flash message
                 print(f"✅ Request completed with status {res.status_code}")
                 if "Internal Server Error" in res.get_data(as_text=True):
                     print("❌ Internal Server Error detected!")
                     print(res.get_data(as_text=True)[:2000])
                 else:
                     print("Login seems successful or handled.")

if __name__ == "__main__":
    try:
        reproduce_login()
    except Exception as e:
        print(f"❌ Script Error: {e}")
        import traceback
        traceback.print_exc()
