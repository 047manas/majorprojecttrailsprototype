
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# Initialize SQLAlchemy
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') # 'student', 'faculty', 'admin'
    position = db.Column(db.String(50), nullable=True) # e.g. 'hod'
    
    # Extended Fields
    
    # Extended Fields
    full_name = db.Column(db.String(100), nullable=False, default="Unknown")
    department = db.Column(db.String(100), nullable=True) # For Faculty AND Students
    batch_year = db.Column(db.String(20), nullable=True) # Legacy field found in DB
    
    # Generic ID: Roll Number (Student) or Employee ID (Faculty)
    institution_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.email}>'

    def is_admin(self):
        return self.role == 'admin'
    
    def is_faculty(self):
        return self.role == 'faculty'

class ActivityType(db.Model):
    __tablename__ = 'activity_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    
    # Changed: Responsible Person instead of Dept String
    faculty_incharge_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Relationship
    faculty_incharge = db.relationship('User', foreign_keys=[faculty_incharge_id], backref=db.backref('managed_activities', lazy=True))
    
    def __repr__(self):
        return f'<ActivityType {self.name}>'

class StudentActivity(db.Model):
    __tablename__ = 'student_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    activity_type_id = db.Column(db.Integer, db.ForeignKey('activity_types.id'), nullable=True, index=True)
    custom_category = db.Column(db.String(100), nullable=True)
    
    title = db.Column(db.String(200), nullable=False)
    issuer_name = db.Column(db.String(200), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    # Legacy fields found in DB
    organizer = db.Column(db.String(200), nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    certificate_file = db.Column(db.String(255), nullable=False)
    certificate_hash = db.Column(db.String(255), nullable=True, index=True)
    
    urls_json = db.Column(db.Text, nullable=True)
    ids_json = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(50), default='pending', index=True) # pending, auto_verified, faculty_verified, rejected
    auto_decision = db.Column(db.String(255), nullable=True)
    
    # New: Public Verification Token
    verification_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    
    # New: Track verification method (e.g., 'qr+link', 'link_only')
    verification_mode = db.Column(db.String(50), nullable=True)
    
    # New: Detailed JSON logs for auto-verification
    auto_details = db.Column(db.Text, nullable=True)
    
    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    assigned_reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    faculty_comment = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    prev_activity_id = db.Column(db.Integer, db.ForeignKey('student_activities.id'), nullable=True)
    
    # Relationships
    student = db.relationship('User', foreign_keys=[student_id], backref=db.backref('activities', lazy=True, cascade="all, delete-orphan"))
    activity_type = db.relationship('ActivityType', backref=db.backref('student_activities', lazy=True))
    faculty = db.relationship('User', foreign_keys=[faculty_id], backref=db.backref('reviewed_activities', lazy=True))
    prev_activity = db.relationship('StudentActivity', remote_side=[id], backref=db.backref('next_activity', uselist=False))

    def __repr__(self):
        return f'<StudentActivity {self.id} - {self.title}>'
