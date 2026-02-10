import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    # Use environment variable for DB URI, fallback to SQLite for local development
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI') or 'sqlite:///smarthub.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Folder
    # Assuming 'app' folder is one level down from root where config.py resides
    # But wait, config.py is in root. So app/uploads is correct relative to root.
    # However, Flask usually handles relative paths from instance_path or root_path.
    # Let's make it absolute to be safe.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'uploads')
