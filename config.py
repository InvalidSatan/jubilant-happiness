import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'instance', 'woodshop.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Banner SIS integration
    BANNER_API_URL = os.environ.get("BANNER_API_URL", "")
    BANNER_API_KEY = os.environ.get("BANNER_API_KEY", "")

    # ASULearn / Moodle integration
    ASULEARN_API_URL = os.environ.get("ASULEARN_API_URL", "")
    ASULEARN_API_TOKEN = os.environ.get("ASULEARN_API_TOKEN", "")


class ProductionConfig(Config):
    """Production configuration for university network deployment."""

    DEBUG = False
    # In production the SECRET_KEY env var MUST be set
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Proxy support — trust X-Forwarded-* headers from reverse proxy
    PREFERRED_URL_SCHEME = "https"

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

        db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" in db_url:
            import warnings
            warnings.warn(
                "Production is using SQLite. Set DATABASE_URL to a PostgreSQL "
                "URI for reliable multi-user access.",
                stacklevel=2,
            )
