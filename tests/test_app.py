"""Basic smoke tests for the Octagon Woodshop Log application."""

import pytest

from app import create_app, db
from app.models import Monitor, Student, ShopArea, MonitorSession, StudentVisit, Warning
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed(app):
    """Create basic test data and return plain-dict IDs to avoid detached instances."""
    area = ShopArea.query.filter_by(name="Sculpture").first()

    monitor = Monitor(username="testmon", display_name="Test Monitor")
    monitor.set_password("pass")
    monitor.areas.append(area)
    db.session.add(monitor)

    admin = Monitor(username="testadmin", display_name="Test Admin", is_admin=True)
    admin.set_password("pass")
    admin.areas.append(area)
    db.session.add(admin)

    student = Student(
        student_id="900999999", display_name="Test Student", email="test@appstate.edu"
    )
    db.session.add(student)

    db.session.commit()

    # Return plain IDs so we never hit detached-instance errors
    return {
        "monitor_id": monitor.id,
        "admin_id": admin.id,
        "student_id": student.id,
        "student_banner_id": student.student_id,
        "area_id": area.id,
    }


def login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=True
    )


class TestAuth:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Monitor Sign In" in resp.data

    def test_login_success(self, client, seed):
        resp = login(client, "testmon", "pass")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_login_failure(self, client, seed):
        resp = login(client, "testmon", "wrong")
        assert b"Invalid username or password" in resp.data

    def test_redirect_when_not_logged_in(self, client):
        resp = client.get("/monitor/dashboard")
        assert resp.status_code == 302


class TestMonitorSession:
    def test_sign_in_to_area(self, client, seed):
        login(client, "testmon", "pass")
        resp = client.post(
            "/monitor/sign-in", data={"area_id": seed["area_id"]}, follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"Signed in to Sculpture" in resp.data

    def test_sign_out_of_area(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})
        resp = client.post("/monitor/sign-out", follow_redirects=True)
        assert b"Signed out" in resp.data


class TestStudentSignIn:
    def test_student_sign_in_requires_monitor_session(self, client, seed):
        login(client, "testmon", "pass")
        resp = client.get("/student/lookup", follow_redirects=True)
        assert b"must be signed in to an area" in resp.data

    def test_student_sign_in_flow(self, client, seed):
        login(client, "testmon", "pass")
        area_id = seed["area_id"]
        student_id = seed["student_id"]
        banner_id = seed["student_banner_id"]

        # Monitor signs into area
        client.post("/monitor/sign-in", data={"area_id": area_id})

        # Look up student
        resp = client.post(
            "/student/lookup",
            data={"student_id": banner_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Confirm sign-in
        resp = client.post(
            "/student/sign-in",
            data={"student_id": student_id, "area_id": area_id},
            follow_redirects=True,
        )
        assert b"signed in to Sculpture" in resp.data

    def test_banned_student_cannot_sign_in(self, client, seed):
        login(client, "testmon", "pass")
        area_id = seed["area_id"]
        student_id = seed["student_id"]
        monitor_id = seed["monitor_id"]

        client.post("/monitor/sign-in", data={"area_id": area_id})

        # Issue 3 warnings
        for i in range(3):
            w = Warning(
                student_id=student_id,
                area_id=area_id,
                issued_by_id=monitor_id,
                reason=f"Strike {i + 1}",
            )
            db.session.add(w)
        db.session.commit()

        resp = client.post(
            "/student/sign-in",
            data={"student_id": student_id, "area_id": area_id},
            follow_redirects=True,
        )
        assert b"cannot sign in" in resp.data


class TestWarnings:
    def test_issue_warning(self, client, seed):
        login(client, "testmon", "pass")
        student_id = seed["student_id"]
        area_id = seed["area_id"]

        resp = client.post(
            "/admin/warnings/issue",
            data={
                "student_id": student_id,
                "area_id": area_id,
                "reason": "Unsafe behavior near band saw",
            },
            follow_redirects=True,
        )
        assert b"Warning issued" in resp.data

        s = db.session.get(Student, student_id)
        assert s.active_warnings_count == 1

    def test_three_strikes_bans_student(self, client, seed):
        login(client, "testmon", "pass")
        student_id = seed["student_id"]
        area_id = seed["area_id"]

        for i in range(3):
            client.post(
                "/admin/warnings/issue",
                data={
                    "student_id": student_id,
                    "area_id": area_id,
                    "reason": f"Strike {i + 1}",
                },
            )

        s = db.session.get(Student, student_id)
        assert s.is_banned is True


class TestKiosk:
    def test_kiosk_requires_active_session(self, client, seed):
        login(client, "testmon", "pass")
        resp = client.get("/kiosk/", follow_redirects=True)
        # Should redirect to dashboard since no active session
        assert b"Dashboard" in resp.data

    def test_kiosk_sign_in_via_scan(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.post(
            "/kiosk/scan",
            data={"banner_id": seed["student_banner_id"]},
        )
        assert resp.status_code == 200
        assert b"signed in" in resp.data

    def test_kiosk_auto_sign_out(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        # First scan — sign in
        client.post("/kiosk/scan", data={"banner_id": seed["student_banner_id"]})
        # Second scan — should auto sign out
        resp = client.post(
            "/kiosk/scan",
            data={"banner_id": seed["student_banner_id"]},
        )
        assert b"signed out" in resp.data

    def test_kiosk_unknown_student(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.post("/kiosk/scan", data={"banner_id": "999999999"})
        assert b"not found" in resp.data

    def test_kiosk_banned_student(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        # Issue 3 warnings
        for i in range(3):
            w = Warning(
                student_id=seed["student_id"],
                area_id=seed["area_id"],
                issued_by_id=seed["monitor_id"],
                reason=f"Strike {i + 1}",
            )
            db.session.add(w)
        db.session.commit()

        resp = client.post(
            "/kiosk/scan",
            data={"banner_id": seed["student_banner_id"]},
        )
        assert b"banned" in resp.data


class TestReports:
    def test_reports_hub_requires_admin(self, client, seed):
        login(client, "testmon", "pass")
        resp = client.get("/admin/reports/", follow_redirects=True)
        assert b"Admin access required" in resp.data

    def test_reports_hub_loads_for_admin(self, client, seed):
        login(client, "testadmin", "pass")
        resp = client.get("/admin/reports/")
        assert resp.status_code == 200
        assert b"Reports" in resp.data
        assert b"Visit Log" in resp.data

    def test_visit_report_loads(self, client, seed):
        login(client, "testadmin", "pass")
        resp = client.get("/admin/reports/visits")
        assert resp.status_code == 200
        assert b"Visit Log" in resp.data

    def test_visit_report_with_data(self, client, seed):
        login(client, "testadmin", "pass")
        # Create a visit via kiosk
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})
        client.post("/kiosk/scan", data={"banner_id": seed["student_banner_id"]})

        resp = client.get("/admin/reports/visits")
        assert b"Test Student" in resp.data
        assert b"1 visit" in resp.data

    def test_visit_csv_export(self, client, seed):
        login(client, "testadmin", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})
        client.post("/kiosk/scan", data={"banner_id": seed["student_banner_id"]})

        resp = client.get("/admin/reports/visits/export")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Test Student" in resp.data
        assert b"900999999" in resp.data

    def test_coverage_report_loads(self, client, seed):
        login(client, "testadmin", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.get("/admin/reports/coverage")
        assert resp.status_code == 200
        assert b"Monitor Coverage" in resp.data
        assert b"Test Admin" in resp.data

    def test_coverage_csv_export(self, client, seed):
        login(client, "testadmin", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.get("/admin/reports/coverage/export")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Test Admin" in resp.data

    def test_safety_report_loads(self, client, seed):
        login(client, "testadmin", "pass")
        resp = client.get("/admin/reports/safety")
        assert resp.status_code == 200
        assert b"Safety" in resp.data

    def test_safety_report_with_warnings(self, client, seed):
        login(client, "testadmin", "pass")
        # Issue a warning
        client.post(
            "/admin/warnings/issue",
            data={
                "student_id": seed["student_id"],
                "area_id": seed["area_id"],
                "reason": "Test warning for report",
            },
        )

        resp = client.get("/admin/reports/safety")
        assert b"1" in resp.data  # total count
        assert b"Test warning for report" in resp.data

    def test_safety_csv_export(self, client, seed):
        login(client, "testadmin", "pass")
        client.post(
            "/admin/warnings/issue",
            data={
                "student_id": seed["student_id"],
                "area_id": seed["area_id"],
                "reason": "Export test warning",
            },
        )

        resp = client.get("/admin/reports/safety/export")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Export test warning" in resp.data

    def test_report_area_filter(self, client, seed):
        login(client, "testadmin", "pass")
        resp = client.get(f"/admin/reports/visits?area_id={seed['area_id']}")
        assert resp.status_code == 200
        assert b"Visit Log" in resp.data
