"""
Database Initialization Script
Initializes PostgreSQL database and creates all tables with default admin
"""

import sys
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Add parent dir to path to import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, User, ActivityType

app = create_app()

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
            prof_hod_cse = User(
                email='hod.cse@college.edu',
                password_hash=generate_password_hash('password'),
                role='faculty',
                position='hod',
                full_name='Prof. HOD CSE',
                department='CSE',
                institution_id='FAC_HOD_CSE_01'
            )
            db.session.add(prof_hod_cse)

            # Create HOD ECE: Prof. HOD ECE
            prof_hod_ece = User(
                email='hod.ece@college.edu',
                password_hash=generate_password_hash('password'),
                role='faculty',
                position='hod',
                full_name='Prof. HOD ECE',
                department='ECE',
                institution_id='FAC_HOD_ECE_01'
            )
            db.session.add(prof_hod_ece)
            
            # Create Students
            student1 = User(
                email='student.cse@college.edu',
                password_hash=generate_password_hash('password'),
                role='student',
                full_name='Student CSE',
                department='CSE',
                batch_year='2022-2026',
                institution_id='STU_CSE_01'
            )
            db.session.add(student1)

            student2 = User(
                email='student.ece@college.edu',
                password_hash=generate_password_hash('password'),
                role='student',
                full_name='Student ECE',
                department='ECE',
                batch_year='2023-2027',
                institution_id='STU_ECE_01'
            )
            db.session.add(student2)

            student3 = User(
                email='student.cse2@college.edu',
                password_hash=generate_password_hash('password'),
                role='student',
                full_name='Student CSE 2',
                department='CSE',
                batch_year='2022-2026',
                institution_id='STU_CSE_02'
            )
            db.session.add(student3)
            
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

            # Create Sample Certificates
            from app.models import StudentActivity
            from datetime import date, timedelta
            
            # 1. Approved CSE Cert (Technical)
            cert1 = StudentActivity(
                student_id=student1.id,
                activity_type_id=act1.id,
                title="Python Workshop",
                certificate_file="dummy.pdf",
                status="faculty_verified",
                faculty_id=dr_smith.id,
                approved_at=datetime.utcnow() - timedelta(days=5),
                created_at=datetime.utcnow() - timedelta(days=10),
                start_date=date(2023, 1, 10),
                end_date=date(2023, 1, 12)
            )
            db.session.add(cert1)

            # 2. Pending CSE Cert (Sports)
            cert2 = StudentActivity(
                student_id=student1.id,
                activity_type_id=act2.id,
                title="Intra-College Football",
                certificate_file="dummy2.pdf",
                status="pending",
                created_at=datetime.utcnow() - timedelta(days=2),
                start_date=date(2023, 2, 15)
            )
            db.session.add(cert2)

            # 3. Approved ECE Cert (Technical)
            cert3 = StudentActivity(
                student_id=student2.id,
                activity_type_id=act1.id,
                title="Robotics Workshop",
                certificate_file="dummy3.pdf",
                status="faculty_verified",
                faculty_id=prof_hod_ece.id,
                approved_at=datetime.utcnow() - timedelta(days=1),
                created_at=datetime.utcnow() - timedelta(days=3),
                start_date=date(2023, 3, 20)
            )
            db.session.add(cert3)

            # 4. Rejected ECE Cert
            cert4 = StudentActivity(
                student_id=student2.id,
                activity_type_id=act2.id,
                title="Invalid Event",
                certificate_file="dummy4.pdf",
                status="rejected",
                faculty_id=prof_hod_ece.id,
                faculty_comment="Blurry Image",
                created_at=datetime.utcnow() - timedelta(days=20),
                start_date=date(2023, 1, 1)
            )
            db.session.add(cert4)
            
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
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
