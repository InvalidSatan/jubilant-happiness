import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
csrf = CSRFProtect()


@login_manager.unauthorized_handler
def _unauthorized():
    """Route unauthenticated users to the login page that matches the area they
    were trying to reach (faculty pages → faculty login), preserving ``next``."""
    from flask import redirect, request, url_for

    if request.path.startswith("/faculty"):
        return redirect(url_for("faculty.login", next=request.url))
    return redirect(url_for("auth.login", next=request.url))


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        from config import Config
        config_class = Config

    app.config.from_object(config_class)

    # Let config classes perform custom app initialization
    if hasattr(config_class, "init_app") and callable(config_class.init_app):
        config_class.init_app(app)

    # Ensure the SQLite instance directory exists before SQLAlchemy connects.
    _ensure_sqlite_dir(app)

    db.init_app(app)
    # Import models before init_migrate so Alembic autogenerate sees them
    from app import models  # noqa: F401
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Jinja filter to render stored UTC datetimes in the shop's local timezone.
    from app.utils import format_local

    app.jinja_env.filters["localdt"] = format_local

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

    _register_error_handlers(app)
    _register_healthcheck(app)

    # In TESTING mode (in-memory SQLite), create schema directly and seed
    # the baseline shop areas. In dev/prod, `flask db upgrade` handles the
    # schema and the initial migration seeds the shop areas.
    if app.config.get("TESTING"):
        with app.app_context():
            db.create_all()
            _seed_areas()

    return app


def _register_error_handlers(app):
    """Friendly, styled error pages — and roll the DB session back on 500 so a
    failed request can't poison the next one served by the same worker."""
    from flask import render_template, redirect, request, url_for, flash
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # Usually a stale tab or an expired session, not an attack — guide the
        # user to retry instead of showing a bare 400.
        flash(
            "Your session expired or the form was invalid. Please try again.",
            "warning",
        )
        target = request.referrer if request.referrer else url_for("auth.login")
        return redirect(target)


def _register_healthcheck(app):
    """Unauthenticated liveness/readiness probe for systemd or a load balancer."""
    from flask import jsonify

    @app.get("/healthz")
    def healthz():
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify(status="ok"), 200
        except Exception:  # pragma: no cover - only on a real DB outage
            db.session.rollback()
            return jsonify(status="error"), 503


def _ensure_sqlite_dir(app):
    """Create the parent directory for a SQLite database file if it is missing.

    Avoids a confusing 'unable to open database file' error on first run when
    the ``instance/`` directory hasn't been created yet.
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    prefix = "sqlite:///"
    if uri.startswith(prefix):
        db_path = uri[len(prefix):]
        # Skip the special in-memory database used by the test suite.
        if db_path and db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)


def _seed_areas():
    """Ensure the five shop areas exist. Only used by the TESTING bootstrap."""
    from app.models import ShopArea

    area_names = ["Sculpture", "Ceramics", "Metal Smithing", "DigiLab", "Woodworking"]
    for name in area_names:
        if not ShopArea.query.filter_by(name=name).first():
            db.session.add(ShopArea(name=name))
    db.session.commit()
