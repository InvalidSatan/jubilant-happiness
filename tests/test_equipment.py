"""Tests for admin equipment edit/delete."""

import pytest

from app import create_app, db
from app.models import Monitor, Student, ShopArea, Equipment, student_training
from config import Config


class EquipConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    app = create_app(EquipConfig)
    with app.app_context():
        area = ShopArea.query.filter_by(name="Sculpture").first()
        other = ShopArea.query.filter_by(name="Woodworking").first()
        admin = Monitor(username="admin", display_name="Admin", is_admin=True)
        admin.set_password("pw")
        admin.areas.append(area)
        db.session.add(admin)
        db.session.add(Equipment(name="Annodizing", area_id=area.id, requires_training=True))
        db.session.add(Equipment(name="In Use", area_id=other.id, requires_training=True))
        db.session.add(Student(student_id="900123123", display_name="Trainee"))
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    c = app.test_client()
    c.post("/login", data={"username": "admin", "password": "pw"})
    return c


def _eq(name):
    return Equipment.query.filter_by(name=name).first()


class TestEditEquipment:
    def test_edit_page_loads(self, client, app):
        eq = _eq("Annodizing")
        resp = client.get(f"/admin/equipment/{eq.id}/edit")
        assert resp.status_code == 200
        assert b"Annodizing" in resp.data

    def test_rename_equipment(self, client, app):
        eq = _eq("Annodizing")
        resp = client.post(
            f"/admin/equipment/{eq.id}/edit",
            data={"name": "Anodizing", "area_id": eq.area_id, "requires_training": "on"},
            follow_redirects=True,
        )
        assert b"updated" in resp.data
        assert _eq("Anodizing") is not None
        assert _eq("Annodizing") is None

    def test_edit_can_clear_requires_training(self, client, app):
        eq = _eq("Annodizing")
        client.post(
            f"/admin/equipment/{eq.id}/edit",
            data={"name": "Annodizing", "area_id": eq.area_id},  # checkbox omitted
            follow_redirects=True,
        )
        assert _eq("Annodizing").requires_training is False

    def test_edit_requires_name(self, client, app):
        eq = _eq("Annodizing")
        resp = client.post(
            f"/admin/equipment/{eq.id}/edit",
            data={"name": "", "area_id": eq.area_id},
            follow_redirects=True,
        )
        assert b"required" in resp.data


class TestDeleteEquipment:
    def test_delete_unreferenced_equipment(self, client, app):
        eq = _eq("Annodizing")
        resp = client.post(
            f"/admin/equipment/{eq.id}/delete", follow_redirects=True
        )
        assert b"deleted" in resp.data
        assert _eq("Annodizing") is None

    def test_delete_blocked_when_training_records_exist(self, client, app):
        eq = _eq("In Use")
        student = Student.query.filter_by(student_id="900123123").first()
        db.session.execute(
            student_training.insert().values(
                student_id=student.id, equipment_id=eq.id, source="manual"
            )
        )
        db.session.commit()

        resp = client.post(
            f"/admin/equipment/{eq.id}/delete", follow_redirects=True
        )
        assert b"Cannot delete" in resp.data
        assert _eq("In Use") is not None  # still there
