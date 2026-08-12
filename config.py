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

    # Canvas LMS integration
    CANVAS_API_URL = os.environ.get("CANVAS_API_URL", "")
    CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")

    # Google Calendar integration (monitor shift schedules)
    GOOGLE_CALENDAR_API_URL = os.environ.get(
        "GOOGLE_CALENDAR_API_URL", "https://www.googleapis.com/calendar/v3"
    )
    GOOGLE_CALENDAR_API_KEY = os.environ.get("GOOGLE_CALENDAR_API_KEY", "")

    # Per-area calendar ids are NOT configured here — faculty own those
    # calendars and set each one from the faculty portal, so they live on
    # ShopArea.calendar_id in the database. Only the credential is deployment
    # config.

    # How many area cards to show on the faculty dashboard. Three areas are
    # scheduled through Google Calendar so far; raise this as more move over.
    GOOGLE_CALENDAR_CARD_COUNT = int(
        os.environ.get("GOOGLE_CALENDAR_CARD_COUNT", "3")
    )


class ProductionConfig(Config):
    """Production configuration for university network deployment."""

    DEBUG = False
    # In production the SECRET_KEY env var MUST be set
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Proxy support — trust X-Forwarded-* headers from reverse proxy.
    # PREFERRED_URL_SCHEME only covers URLs built outside a request; the
    # headers themselves are applied by ProxyFix in init_app below.
    PREFERRED_URL_SCHEME = "https"

    # How many reverse proxies sit in front of the app. The Nginx setup in
    # DEPLOYMENT.md is a single hop, so 1 is right there; container hosting
    # that adds a load balancer in front of the proxy needs 2. Counting too
    # high lets a client forge its own address by sending X-Forwarded-For,
    # since ProxyFix would read a hop the proxy never wrote.
    PROXY_HOPS = int(os.environ.get("PROXY_HOPS", "1"))

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

        # Without this the app sees every request as coming from the proxy
        # over plain HTTP: request.remote_addr is the proxy's address and
        # external URLs are built as http://, even though the client spoke
        # HTTPS to Nginx. Only applied in production, where a proxy is always
        # in front — trusting these headers when the app is directly reachable
        # would let any client claim any address or scheme it liked.
        from werkzeug.middleware.proxy_fix import ProxyFix

        hops = app.config.get("PROXY_HOPS", 1)
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops
        )

        db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" in db_url:
            import warnings
            warnings.warn(
                "Production is using SQLite. Set DATABASE_URL to a PostgreSQL "
                "URI for reliable multi-user access.",
                stacklevel=2,
            )
