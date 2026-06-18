"""Tests for the external (Banner/ASULearn/Canvas) training sync."""

import pytest
from sqlalchemy import select

from app import create_app, db
from app.models import Student, ShopArea, Equipment, Monitor, student_training
from app.routes import integration as integ
from config import Config


class IntegConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    app = create_app(IntegConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()
        db.session.add(Equipment(name="Welding", area_id=area.id, requires_training=True))
        db.session.add(
            Equipment(name="Basic Woodshop", area_id=area.id, requires_training=True)
        )
        admin = Monitor(username="admin", display_name="Admin", is_admin=True)
        admin.set_password("pw")
        admin.areas.append(area)
        db.session.add(admin)
        db.session.add(
            Student(
                student_id="900000001",
                display_name="Canvas Kid",
                email="ck@appstate.edu",
                canvas_user_id="555",
            )
        )
        db.session.commit()
        yield app
        db.session.remove()


def _student():
    return Student.query.filter_by(student_id="900000001").first()


def _training_rows(student_id):
    return db.session.execute(
        select(student_training).where(student_training.c.student_id == student_id)
    ).all()


class TestCourseMap:
    def test_env_override_merges(self, app):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = '{"ART 2210": "Welding"}'
        assert integ.get_course_equipment_map()["ART 2210"] == "Welding"

    def test_invalid_json_is_ignored(self, app):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = "{not valid json"
        # Should not raise; just falls back to defaults.
        assert isinstance(integ.get_course_equipment_map(), dict)


class TestCanvasSync:
    def test_grants_with_canvas_source(self, app, monkeypatch):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = '{"ART 2210": "Welding"}'
        monkeypatch.setattr(
            integ, "fetch_canvas_enrollments",
            lambda uid: [{"course_code": "ART 2210", "name": "Sculpture I"}],
        )
        student = _student()
        added = integ.sync_student_training(student)
        db.session.commit()
        assert added == ["Welding"]
        rows = _training_rows(student.id)
        assert len(rows) == 1
        assert rows[0].source == "canvas"

    def test_matches_sis_course_id(self, app, monkeypatch):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = '{"ART-2210-001": "Welding"}'
        monkeypatch.setattr(
            integ, "fetch_canvas_enrollments",
            lambda uid: [{"course_code": "OTHER", "sis_course_id": "ART-2210-001"}],
        )
        student = _student()
        added = integ.sync_student_training(student)
        db.session.commit()
        assert added == ["Welding"]

    def test_does_not_duplicate_existing_training(self, app, monkeypatch):
        student = _student()
        welding = Equipment.query.filter_by(name="Welding").first()
        db.session.execute(
            student_training.insert().values(
                student_id=student.id, equipment_id=welding.id, source="manual"
            )
        )
        db.session.commit()

        app.config["COURSE_EQUIPMENT_MAP_JSON"] = '{"ART 2210": "Welding"}'
        monkeypatch.setattr(
            integ, "fetch_canvas_enrollments",
            lambda uid: [{"course_code": "ART 2210"}],
        )
        added = integ.sync_student_training(_student())
        db.session.commit()
        assert added == []
        assert len(_training_rows(student.id)) == 1  # unchanged

    def test_no_map_grants_nothing(self, app, monkeypatch):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = ""
        monkeypatch.setattr(
            integ, "fetch_canvas_enrollments",
            lambda uid: [{"course_code": "ART 2210"}],
        )
        assert integ.sync_student_training(_student()) == []


class TestCanvasPagination:
    def test_follows_next_link(self, app, monkeypatch):
        app.config["CANVAS_API_URL"] = "https://canvas.test/api/v1"
        app.config["CANVAS_API_TOKEN"] = "tok"

        class FakeResp:
            def __init__(self, data, link=""):
                self._data = data
                self.headers = {"Link": link} if link else {}

            def raise_for_status(self):
                pass

            def json(self):
                return self._data

        def fake_get(url, headers=None, params=None, timeout=None):
            if "page=2" in url:
                return FakeResp([{"course_code": "B"}])
            return FakeResp(
                [{"course_code": "A"}],
                link='<https://canvas.test/api/v1/x?page=2>; rel="next"',
            )

        monkeypatch.setattr(integ.requests, "get", fake_get)
        courses = integ.fetch_canvas_enrollments("555")
        assert [c["course_code"] for c in courses] == ["A", "B"]


class TestSyncAllEndpoint:
    def test_sync_all_grants_across_students(self, app, monkeypatch):
        app.config["COURSE_EQUIPMENT_MAP_JSON"] = '{"ART 2210": "Welding"}'
        monkeypatch.setattr(
            integ, "fetch_canvas_enrollments",
            lambda uid: [{"course_code": "ART 2210"}],
        )
        client = app.test_client()
        client.post("/login", data={"username": "admin", "password": "pw"})
        resp = client.post("/integration/sync-all", follow_redirects=True)
        assert resp.status_code == 200
        assert b"new certification" in resp.data
        assert len(_training_rows(_student().id)) == 1
