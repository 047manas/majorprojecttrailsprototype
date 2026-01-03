"""
Database Initialization Script
Initializes PostgreSQL database and creates all tables with default admin
"""

from app import app, db
from models import User, ActivityType
from werkzeug.security import generate_password_hash
import sys

def init_database():
    """Create all database tables and seed default data"""
    with app.app_context():
        try:
            print("🔧 Creating database tables...")
            # Drop all to ensure schema updates
            db.drop_all()
            db.create_all()
            print("✅ Database tables created successfully!")
            
            print("👤 Creating default admin user...")
            # Create default admin
            admin = User(
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                full_name='System Administrator',
                department='IT',
                institution_id='ADMIN001'
            )
            db.session.add(admin)
            
            # Create Faculty: Dr. Smith
            dr_smith = User(
                email='drsmith@college.edu',
                password_hash=generate_password_hash('password'),
                role='faculty',
                full_name='Dr. Smith',
                department='CSE',
                institution_id='FAC001'
            )
            db.session.add(dr_smith)
            
            # Create HOD CSE: Prof. HOD
            prof_hod = User(
                email='hod.cse@college.edu',
                password_hash=generate_password_hash('password'),
                role='faculty',
                position='hod',
                full_name='Prof. HOD CSE',
                department='CSE',
                institution_id='FAC_HOD_01'
            )
            db.session.add(prof_hod)
            
            db.session.commit()  # Commit to get IDs
            
            # Create Dummy Activity Types
            act1 = ActivityType(
                name="Technical Workshop",
                faculty_incharge_id=dr_smith.id,
                description="Workshops on coding, robotics, etc."
            )
            act2 = ActivityType(
                name="Sports Meet",
                faculty_incharge_id=admin.id,
                description="Inter-college and Intra-college sports."
            )
            db.session.add(act1)
            db.session.add(act2)
            db.session.commit()
            
            print("✅ Default users created successfully!")
            print("\nTables created:")
            print("  - users")
            print("  - activity_types")
            print("  - student_activities")
            print("\nDefault Admin Account:")
            print("  Email: admin@example.com")
            print("  Password: admin123")
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
