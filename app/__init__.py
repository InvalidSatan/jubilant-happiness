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

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import Monitor

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Monitor, int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.monitor import monitor_bp
    from app.routes.student import student_bp
    from app.routes.admin import admin_bp
    from app.routes.integration import integration_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(monitor_bp, url_prefix="/monitor")
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(integration_bp, url_prefix="/integration")

    with app.app_context():
        db.create_all()
        _seed_areas()

    return app


def _seed_areas():
    """Ensure the four shop areas exist."""
    from app.models import ShopArea

    area_names = ["Sculpture", "Ceramics", "Metal Smithing", "DigiLab"]
    for name in area_names:
        if not ShopArea.query.filter_by(name=name).first():
            db.session.add(ShopArea(name=name))
    db.session.commit()
