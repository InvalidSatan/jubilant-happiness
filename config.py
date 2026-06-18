import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'instance', 'woodshop.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Security: session cookies ---
    # HttpOnly stops JS from reading the session cookie; SameSite=Lax blocks the
    # cookie on cross-site POSTs (defense in depth alongside CSRF tokens).
    # SESSION_COOKIE_SECURE is enabled in ProductionConfig (requires HTTPS).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # --- CSRF (Flask-WTF) ---
    # Tokens are valid for the life of the session rather than expiring after an
    # hour. The kiosk and monitor dashboard are routinely left open all shift, so
    # a 1-hour token limit would cause spurious "CSRF token expired" failures.
    WTF_CSRF_TIME_LIMIT = None

    # Banner SIS integration
    BANNER_API_URL = os.environ.get("BANNER_API_URL", "")
    BANNER_API_KEY = os.environ.get("BANNER_API_KEY", "")

    # ASULearn / Moodle integration
    ASULEARN_API_URL = os.environ.get("ASULEARN_API_URL", "")
    ASULEARN_API_TOKEN = os.environ.get("ASULEARN_API_TOKEN", "")

    # Canvas LMS integration
    CANVAS_API_URL = os.environ.get("CANVAS_API_URL", "")
    CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")


class ProductionConfig(Config):
    """Production configuration for university network deployment."""

    DEBUG = False
    # In production the SECRET_KEY env var MUST be set
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Proxy support — trust X-Forwarded-* headers from reverse proxy
    PREFERRED_URL_SCHEME = "https"

    # Only send the session cookie over HTTPS. Safe because production runs
    # behind the TLS-terminating reverse proxy documented in DEPLOYMENT.md.
    SESSION_COOKIE_SECURE = True

    # PostgreSQL connection-pool tuning (via SQLAlchemy)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,
    }

    @staticmethod
    def init_app(app):
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError(
                "SECRET_KEY environment variable must be set for production."
            )

        # Trust the reverse proxy's X-Forwarded-* headers so url_for(_external),
        # request.is_secure, and Secure-cookie handling reflect the real HTTPS
        # request rather than the internal HTTP hop to gunicorn.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )

        db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" in db_url:
            import warnings
            warnings.warn(
                "Production is using SQLite. Set DATABASE_URL to a PostgreSQL "
                "URI for reliable multi-user access.",
                stacklevel=2,
            )
