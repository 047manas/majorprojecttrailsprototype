import os

from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://postgres:root%40123@localhost:5432/smarthub')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB limit
    
    # Security: Max Upload Size 16MB
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Upload Folder
    # Assuming 'app' folder is one level down from root where config.py resides
    # But wait, config.py is in root. So app/uploads is correct relative to root.
    # However, Flask usually handles relative paths from instance_path or root_path.
    # Let's make it absolute to be safe.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'uploads')
