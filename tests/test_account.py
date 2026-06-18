"""Tests for self-service password changes (monitor + faculty)."""

import pytest

from app import create_app, db
from app.models import Monitor, Faculty, ShopArea
from config import Config


class AccountConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    app = create_app(AccountConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()
        monitor = Monitor(username="mon", display_name="Mon")
        monitor.set_password("oldpass1")
        monitor.areas.append(area)
        db.session.add(monitor)
        faculty = Faculty(username="fac", display_name="Doc", is_primary_admin=True)
        faculty.set_password("oldpass1")
        db.session.add(faculty)
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


class TestMonitorPasswordChange:
    def test_link_shown_in_navbar(self, client):
        client.post("/login", data={"username": "mon", "password": "oldpass1"})
        resp = client.get("/monitor/dashboard")
        assert b"Account" in resp.data
        assert b"/change-password" in resp.data

    def test_wrong_current_rejected(self, client):
        client.post("/login", data={"username": "mon", "password": "oldpass1"})
        resp = client.post(
            "/change-password",
            data={
                "current_password": "WRONG",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
            follow_redirects=True,
        )
        assert b"Current password is incorrect" in resp.data

    def test_short_password_rejected(self, client):
        client.post("/login", data={"username": "mon", "password": "oldpass1"})
        resp = client.post(
            "/change-password",
            data={
                "current_password": "oldpass1",
                "new_password": "short",
                "confirm_password": "short",
            },
            follow_redirects=True,
        )
        assert b"at least 8 characters" in resp.data

    def test_mismatch_rejected(self, client):
        client.post("/login", data={"username": "mon", "password": "oldpass1"})
        resp = client.post(
            "/change-password",
            data={
                "current_password": "oldpass1",
                "new_password": "newpass12",
                "confirm_password": "different12",
            },
            follow_redirects=True,
        )
        assert b"do not match" in resp.data

    def test_successful_change_and_relogin(self, client, app):
        client.post("/login", data={"username": "mon", "password": "oldpass1"})
        resp = client.post(
            "/change-password",
            data={
                "current_password": "oldpass1",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
            follow_redirects=True,
        )
        assert b"password has been updated" in resp.data
        client.get("/logout")
        # Old password no longer works; new one does.
        bad = client.post(
            "/login", data={"username": "mon", "password": "oldpass1"}, follow_redirects=True
        )
        assert b"Invalid username or password" in bad.data
        good = client.post(
            "/login", data={"username": "mon", "password": "newpass12"}, follow_redirects=True
        )
        assert b"Dashboard" in good.data


class TestFacultyPasswordChange:
    def test_successful_change(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "oldpass1"})
        resp = client.post(
            "/faculty/change-password",
            data={
                "current_password": "oldpass1",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
            follow_redirects=True,
        )
        assert b"password has been updated" in resp.data
        client.get("/faculty/logout")
        good = client.post(
            "/faculty/login",
            data={"username": "fac", "password": "newpass12"},
            follow_redirects=True,
        )
        assert b"Faculty Dashboard" in good.data

    def test_monitor_route_redirects_faculty(self, client):
        """A faculty user hitting the monitor change-password route is sent to
        the faculty equivalent rather than operating on the wrong model."""
        client.post("/faculty/login", data={"username": "fac", "password": "oldpass1"})
        resp = client.get("/change-password")
        assert resp.status_code == 302
        assert "/faculty/change-password" in resp.headers["Location"]
