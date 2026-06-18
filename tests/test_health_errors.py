"""Tests for the health check and custom error pages."""

import pytest

from app import create_app, db
from config import Config


class HealthConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def client():
    app = create_app(HealthConfig)
    with app.app_context():
        yield app.test_client()
        db.session.remove()


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_404_uses_styled_page(client):
    resp = client.get("/no/such/page")
    assert resp.status_code == 404
    assert b"404" in resp.data
    # Rendered through base.html (app chrome), not the default Werkzeug page.
    assert b"Octagon Woodshop Log" in resp.data
