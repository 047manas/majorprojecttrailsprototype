from flask import Flask
from flask_login import LoginManager
from config import Config
from app.models import db, User

from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()
migrate = Migrate()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # Register Blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.student_routes import student_bp
    from app.routes.faculty_routes import faculty_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.analytics_routes import analytics_bp
    from app.routes.public_routes import public_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(public_bp)
    
    # Legacy Routes - Disabled for Refactoring
    # from app.routes import bp as main_bp
    # app.register_blueprint(main_bp)

    return app
