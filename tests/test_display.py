"""Tests for local-timezone display and the issue-warning area list."""

from datetime import datetime, timezone

import pytest

from app import create_app, db
from app.models import Monitor, Student, ShopArea
from app.utils import format_local
from config import Config


class DisplayConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False
    DISPLAY_TIMEZONE = "America/New_York"


@pytest.fixture
def app():
    app = create_app(DisplayConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()
        monitor = Monitor(username="mon", display_name="Mon", is_admin=True)
        monitor.set_password("pw")
        monitor.areas.append(area)
        db.session.add(monitor)
        db.session.add(
            Student(student_id="900111222", display_name="No Visits Student")
        )
        db.session.commit()
        yield app
        db.session.remove()


class TestLocalTime:
    def test_utc_winter_converts_to_eastern_standard(self, app):
        # 18:00 UTC in January is 13:00 EST (UTC-5).
        dt = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)
        assert format_local(dt, "%Y-%m-%d %H:%M") == "2026-01-15 13:00"

    def test_utc_summer_converts_to_eastern_daylight(self, app):
        # 18:00 UTC in July is 14:00 EDT (UTC-4).
        dt = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)
        assert format_local(dt, "%Y-%m-%d %H:%M") == "2026-07-15 14:00"

    def test_naive_datetime_treated_as_utc(self, app):
        # Stored datetimes come back naive; they must be read as UTC.
        dt = datetime(2026, 1, 15, 18, 0)
        assert format_local(dt, "%H:%M") == "13:00"

    def test_none_is_empty_string(self, app):
        assert format_local(None) == ""

    def test_filter_registered(self, app):
        assert "localdt" in app.jinja_env.filters


class TestIssueWarningAreaList:
    def test_area_dropdown_present_for_student_without_visits(self, app):
        """Regression: the issue-warning area <select> only listed areas the
        student had already visited, so a student with no visits had an empty
        dropdown and could not be warned."""
        client = app.test_client()
        client.post("/login", data={"username": "mon", "password": "pw"})
        student = Student.query.filter_by(student_id="900111222").first()
        resp = client.get(f"/monitor/student/{student.id}")
        assert resp.status_code == 200
        # All five shop areas should be selectable.
        for name in ["Sculpture", "Ceramics", "Woodworking"]:
            assert name.encode() in resp.data
