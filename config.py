import os

basedir = os.path.abspath(os.path.dirname(__file__))


def normalize_database_url(url):
    """Make a hand-written DATABASE_URL safe to hand to SQLAlchemy.

    Deployment sets DATABASE_URL to a plain `mysql://` URI. SQLAlchemy reads
    that scheme as "use the MySQLdb driver", which is a C extension we do not
    install, so it would fail at startup with a ModuleNotFoundError. Rewrite
    the scheme to name the driver we actually ship (PyMySQL).

    Also default the charset to utf8mb4. MySQL's older `utf8` is a three-byte
    encoding that cannot store emoji or many non-Latin names, and student
    names and care notes are free text.
    """
    if not url:
        return url

    scheme, sep, rest = url.partition("://")
    if not sep:
        return url

    if scheme == "mysql":
        scheme = "mysql+pymysql"

    if scheme.startswith("mysql") and "charset=" not in rest:
        rest += "&charset=utf8mb4" if "?" in rest else "?charset=utf8mb4"

    return f"{scheme}://{rest}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")

    # Production points this at the MySQL Galera cluster. The SQLite default
    # is for local development and the test suite only.
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.getenv(
            "DATABASE_URL",
            f"sqlite:///{os.path.join(basedir, 'instance', 'woodshop.db')}",
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Banner SIS integration
    BANNER_API_URL = os.getenv("BANNER_API_URL", "")
    BANNER_API_KEY = os.getenv("BANNER_API_KEY", "")

    # ASULearn / Moodle integration
    ASULEARN_API_URL = os.getenv("ASULEARN_API_URL", "")
    ASULEARN_API_TOKEN = os.getenv("ASULEARN_API_TOKEN", "")

    # Canvas LMS integration
    CANVAS_API_URL = os.getenv("CANVAS_API_URL", "")
    CANVAS_API_TOKEN = os.getenv("CANVAS_API_TOKEN", "")

    # Google Calendar integration (monitor shift schedules)
    GOOGLE_CALENDAR_API_URL = os.getenv(
        "GOOGLE_CALENDAR_API_URL", "https://www.googleapis.com/calendar/v3"
    )
    GOOGLE_CALENDAR_API_KEY = os.getenv("GOOGLE_CALENDAR_API_KEY", "")

    # Per-area calendar ids are NOT configured here — faculty own those
    # calendars and set each one from the faculty portal, so they live on
    # ShopArea.calendar_id in the database. Only the credential is deployment
    # config.

    # How many area cards to show on the faculty dashboard. Three areas are
    # scheduled through Google Calendar so far; raise this as more move over.
    GOOGLE_CALENDAR_CARD_COUNT = int(os.getenv("GOOGLE_CALENDAR_CARD_COUNT", "3"))


class ProductionConfig(Config):
    """Production configuration for university network deployment."""

    DEBUG = False
    # In production the SECRET_KEY env var MUST be set
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Proxy support — trust X-Forwarded-* headers from reverse proxy.
    # PREFERRED_URL_SCHEME only covers URLs built outside a request; the
    # headers themselves are applied by ProxyFix in init_app below.
    PREFERRED_URL_SCHEME = "https"

    # Authentication is session-cookie based. Production is always served
    # through HTTPS, so prevent browsers from sending that cookie over plain
    # HTTP, exposing it to JavaScript, or attaching it to most cross-site
    # requests.
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # How many reverse proxies sit in front of the app. Must be read here
    # rather than in init_app: Flask only loads uppercase attributes off the
    # config class, so a value looked up straight from app.config would never
    # see the environment and would silently stay at 1.
    #
    # Setting this higher than the number of proxies actually deployed lets a
    # client forge its own address by sending X-Forwarded-For itself.
    PROXY_HOPS = int(os.getenv("PROXY_HOPS", "1"))

    # MySQL connection-pool tuning (via SQLAlchemy).
    #
    # pool_recycle matters more against Galera than it did against a single
    # PostgreSQL server: connections reach the cluster through a load
    # balancer, and both it and MySQL's own wait_timeout will silently drop
    # an idle connection. Recycling below those timeouts, plus pool_pre_ping,
    # keeps a checked-out connection from being a already-closed one.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
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
                "Production is using SQLite. Set DATABASE_URL to a MySQL "
                "URI for reliable multi-user access.",
                stacklevel=2,
            )
