"""Tests for the live shop roster view and faculty CSV exports."""

import pytest

from app import create_app, db
from app.models import (
    Monitor,
    Faculty,
    Student,
    ShopArea,
    Equipment,
    MonitorSession,
    StudentVisit,
    student_training,
)
from config import Config


class ViewConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    app = create_app(ViewConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()

        admin = Monitor(username="admin", display_name="Admin", is_admin=True)
        admin.set_password("pw")
        admin.areas.append(area)
        db.session.add(admin)

        monitor = Monitor(username="mon", display_name="Mon")
        monitor.set_password("pw")
        monitor.areas.append(area)
        db.session.add(monitor)

        faculty = Faculty(username="fac", display_name="Doc", is_primary_admin=True)
        faculty.set_password("pw")
        db.session.add(faculty)

        student = Student(
            student_id="900555555", display_name="Roster Kid", email="rk@appstate.edu"
        )
        db.session.add(student)
        eq = Equipment(name="Welding", area_id=area.id, requires_training=True)
        db.session.add(eq)
        db.session.commit()

        # Monitor on duty + student signed in (active visit).
        db.session.add(MonitorSession(monitor_id=monitor.id, area_id=area.id))
        db.session.add(
            StudentVisit(
                student_id=student.id, area_id=area.id, acknowledged_by_id=monitor.id
            )
        )
        # One training record for the export.
        db.session.execute(
            student_training.insert().values(
                student_id=student.id,
                equipment_id=eq.id,
                certified_semester="Fall 2025",
                source="manual",
            )
        )
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


class TestLiveShop:
    def test_admin_live_view(self, client):
        client.post("/login", data={"username": "admin", "password": "pw"})
        resp = client.get("/admin/live")
        assert resp.status_code == 200
        assert b"Currently in the Shop" in resp.data
        assert b"Roster Kid" in resp.data       # signed-in student
        assert b"Mon" in resp.data              # monitor on duty
        assert b"Ceramics" in resp.data         # all areas shown

    def test_faculty_live_view(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})
        resp = client.get("/faculty/live")
        assert resp.status_code == 200
        assert b"Roster Kid" in resp.data

    def test_live_view_requires_admin_for_monitor(self, client):
        client.post("/login", data={"username": "mon", "password": "pw"})
        resp = client.get("/admin/live", follow_redirects=True)
        assert b"Admin access required" in resp.data


class TestFacultyExports:
    def test_export_students_csv(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})
        resp = client.get("/faculty/students/export")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Banner ID" in resp.data
        assert b"900555555" in resp.data
        assert b"Roster Kid" in resp.data

    def test_export_students_respects_search(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})
        resp = client.get("/faculty/students/export?search=nomatch")
        assert resp.status_code == 200
        assert b"900555555" not in resp.data

    def test_export_training_csv(self, client):
        client.post("/faculty/login", data={"username": "fac", "password": "pw"})
        resp = client.get("/faculty/training/export")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Welding" in resp.data
        assert b"Fall 2025" in resp.data
        assert b"Roster Kid" in resp.data

    def test_exports_require_faculty(self, client):
        # A monitor (non-faculty) cannot reach the faculty exports.
        client.post("/login", data={"username": "mon", "password": "pw"})
        resp = client.get("/faculty/students/export", follow_redirects=True)
        assert b"Faculty access required" in resp.data
