from app.models import db, User
from werkzeug.security import generate_password_hash, check_password_hash

class UserService:
    @staticmethod
    def get_user_by_email(email):
        return User.query.filter_by(email=email).first()

    @staticmethod
    def create_user(email, password, role, **kwargs):
        if UserService.get_user_by_email(email):
            raise ValueError("Email already exists")
        
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            **kwargs
        )
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def verify_password(user, password):
        return check_password_hash(user.password_hash, password)

    @staticmethod
    def get_user_by_id(user_id):
        return User.query.get(user_id)
