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
