"""WSGI entry point for production deployment with gunicorn."""

import os

# Default to production config when run via gunicorn
os.environ.setdefault("FLASK_CONFIG", "production")

from app import create_app  # noqa: E402

config_name = os.getenv("FLASK_CONFIG", "production")

if config_name == "production":
    from config import ProductionConfig
    app = create_app(ProductionConfig)
else:
    from config import Config
    app = create_app(Config)
