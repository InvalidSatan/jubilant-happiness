from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        from config import Config
        config_class = Config

    app.config.from_object(config_class)

    # Let config classes perform custom app initialization
    if hasattr(config_class, "init_app") and callable(config_class.init_app):
        config_class.init_app(app)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import Monitor, Faculty

    @login_manager.user_loader
    def load_user(user_id):
        if ":" in str(user_id):
            user_type, uid = user_id.split(":", 1)
            uid = int(uid)
            if user_type == "faculty":
                return db.session.get(Faculty, uid)
            return db.session.get(Monitor, uid)
        # Backwards compatibility: bare integer means Monitor
        return db.session.get(Monitor, int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.monitor import monitor_bp
    from app.routes.student import student_bp
    from app.routes.admin import admin_bp
    from app.routes.integration import integration_bp
    from app.routes.kiosk import kiosk_bp
    from app.routes.reports import reports_bp
    from app.routes.faculty import faculty_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(monitor_bp, url_prefix="/monitor")
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(integration_bp, url_prefix="/integration")
    app.register_blueprint(kiosk_bp, url_prefix="/kiosk")
    app.register_blueprint(reports_bp, url_prefix="/admin/reports")
    app.register_blueprint(faculty_bp, url_prefix="/faculty")

    with app.app_context():
        db.create_all()
        _seed_areas()

    return app


def _seed_areas():
    """Ensure the five shop areas exist."""
    from app.models import ShopArea

    area_names = ["Sculpture", "Ceramics", "Metal Smithing", "DigiLab", "Woodworking"]
    for name in area_names:
        if not ShopArea.query.filter_by(name=name).first():
            db.session.add(ShopArea(name=name))
    db.session.commit()
