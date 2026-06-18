"""Security & cross-role regression tests.

Covers fixes for:
  * CSRF protection being wired up (Flask-WTF CSRFProtect).
  * The ``?next=`` login parameter no longer enabling open redirects.
  * Faculty users no longer hitting HTTP 500s (or the wrong dashboard) on the
    monitor/admin blueprints.
  * Banner ID validation in the faculty add-student and CSV-upload flows.
  * CSV upload no longer discarding the whole batch on an in-file duplicate.
"""

import io
import re

import pytest

from app import create_app, db
from app.models import Monitor, Faculty, Student, ShopArea
from config import Config


# ---------------------------------------------------------------------------
# CSRF tests — run with CSRF ENABLED (unlike the rest of the suite) so we
# verify the protection is actually active in a production-like config.
# ---------------------------------------------------------------------------
class CsrfConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_app():
    app = create_app(CsrfConfig)
    with app.app_context():
        monitor = Monitor(username="mon", display_name="Mon", is_admin=True)
        monitor.set_password("pw")
        db.session.add(monitor)
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _token(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


class TestCsrf:
    def test_login_form_renders_csrf_token(self, csrf_client):
        resp = csrf_client.get("/login")
        assert _token(resp.get_data(as_text=True)) is not None

    def test_post_without_token_is_rejected(self, csrf_client):
        # A missing token is rejected (the request is NOT processed) and the
        # user gets a friendly redirect rather than a bare 400.
        resp = csrf_client.post("/login", data={"username": "mon", "password": "pw"})
        assert resp.status_code == 302
        followed = csrf_client.post(
            "/login",
            data={"username": "mon", "password": "pw"},
            follow_redirects=True,
        )
        assert b"session expired or the form was invalid" in followed.data
        assert b"Dashboard" not in followed.data  # not logged in

    def test_post_with_token_succeeds(self, csrf_client):
        token = _token(csrf_client.get("/login").get_data(as_text=True))
        resp = csrf_client.post(
            "/login",
            data={"username": "mon", "password": "pw", "csrf_token": token},
        )
        assert resp.status_code == 302
        assert "/monitor/dashboard" in resp.headers["Location"]

    def test_open_redirect_is_blocked(self, csrf_client):
        token = _token(csrf_client.get("/login").get_data(as_text=True))
        resp = csrf_client.post(
            "/login?next=https://evil.example.com/phish",
            data={"username": "mon", "password": "pw", "csrf_token": token},
        )
        # Falls back to the local dashboard instead of the external URL.
        assert resp.headers["Location"].endswith("/monitor/dashboard")

    def test_safe_relative_next_is_honored(self, csrf_client):
        token = _token(csrf_client.get("/login").get_data(as_text=True))
        resp = csrf_client.post(
            "/login?next=/admin/",
            data={"username": "mon", "password": "pw", "csrf_token": token},
        )
        assert resp.headers["Location"].endswith("/admin/")


# ---------------------------------------------------------------------------
# Cross-role access tests (CSRF disabled, like the main suite).
# ---------------------------------------------------------------------------
class RoleConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def role_app():
    app = create_app(RoleConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()
        faculty = Faculty(username="fac", display_name="Doc", is_primary_admin=True)
        faculty.set_password("pw")
        db.session.add(faculty)
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def role_client(role_app):
    return role_app.test_client()


class TestFacultyCannotReachMonitorPages:
    def _login_faculty(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})

    def test_admin_index_does_not_500(self, role_client):
        """Regression: admin_required used current_user.is_admin which Faculty
        lacks, raising AttributeError (HTTP 500)."""
        self._login_faculty(role_client)
        resp = role_client.get("/admin/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/faculty/")

    def test_brand_link_routes_faculty_to_faculty_dashboard(self, role_client):
        self._login_faculty(role_client)
        resp = role_client.get("/")
        assert resp.headers["Location"].endswith("/faculty/")

    def test_monitor_dashboard_redirects_faculty(self, role_client):
        self._login_faculty(role_client)
        resp = role_client.get("/monitor/dashboard")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/faculty/")

    def test_reports_redirect_faculty(self, role_client):
        self._login_faculty(role_client)
        resp = role_client.get("/admin/reports/")
        assert resp.headers["Location"].endswith("/faculty/")


class TestUnauthenticatedLoginRouting:
    """Anonymous users are sent to the login page matching the area they
    requested, so faculty aren't bounced through the monitor login."""

    def test_faculty_page_redirects_to_faculty_login(self, role_client):
        resp = role_client.get("/faculty/students")
        assert resp.status_code == 302
        assert "/faculty/login" in resp.headers["Location"]

    def test_monitor_page_redirects_to_monitor_login(self, role_client):
        resp = role_client.get("/monitor/dashboard")
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/login" in location and "/faculty/login" not in location


# ---------------------------------------------------------------------------
# Banner ID validation + CSV robustness (faculty flows).
# ---------------------------------------------------------------------------
class TestFacultyBannerIdValidation:
    def _login(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})

    def test_add_student_rejects_short_banner_id(self, role_client):
        self._login(role_client)
        resp = role_client.post(
            "/faculty/students/add",
            data={"student_id": "12345", "display_name": "Bad"},
            follow_redirects=True,
        )
        assert b"must be exactly 9 digits" in resp.data
        assert Student.query.filter_by(student_id="12345").first() is None

    def test_csv_in_file_duplicate_does_not_lose_batch(self, role_client):
        """Regression: a duplicate Banner ID within one CSV used to raise an
        IntegrityError on commit and roll back the entire upload."""
        self._login(role_client)
        csv_content = (
            "banner_id,name\n"
            "900100100,First\n"
            "900100100,Dup\n"
            "900200200,Second\n"
        )
        resp = role_client.post(
            "/faculty/students/upload",
            data={"csv_file": (io.BytesIO(csv_content.encode()), "s.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"2 student(s) added" in resp.data
        assert Student.query.filter_by(student_id="900100100").count() == 1
        assert Student.query.filter_by(student_id="900200200").count() == 1

    def test_csv_invalid_banner_id_reported_as_row_error(self, role_client):
        self._login(role_client)
        csv_content = "banner_id,name\n55,Too Short\n900300300,Valid\n"
        resp = role_client.post(
            "/faculty/students/upload",
            data={"csv_file": (io.BytesIO(csv_content.encode()), "s.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 student(s) added" in resp.data
        assert b"must be exactly 9 digits" in resp.data
        assert Student.query.filter_by(student_id="55").first() is None
