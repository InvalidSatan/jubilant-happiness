"""Basic smoke tests for the Octagon Woodshop Log application."""

import pytest

from app import create_app, db
from app.models import Monitor, Student, ShopArea, MonitorSession, StudentVisit, Warning, Faculty, Equipment
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


    def test_lookup_rejects_invalid_banner_id(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.post(
            "/student/lookup",
            data={"student_id": "abc123"},
            follow_redirects=True,
        )
        assert b"Banner ID must be exactly 9 digits" in resp.data

    def test_register_rejects_invalid_banner_id(self, client, seed):
        login(client, "testmon", "pass")
        resp = client.post(
            "/student/register",
            data={"student_id": "12345", "display_name": "New Student", "email": "n@appstate.edu"},
            follow_redirects=True,
        )
        assert b"Banner ID must be exactly 9 digits" in resp.data

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


    def test_kiosk_rejects_invalid_banner_id(self, client, seed):
        login(client, "testmon", "pass")
        client.post("/monitor/sign-in", data={"area_id": seed["area_id"]})

        resp = client.post("/kiosk/scan", data={"banner_id": "12ab"})
        assert b"Banner ID must be exactly 9 digits" in resp.data

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

    def test_safety_report_banned_students_count(self, client, seed):
        """Only students with 3+ active warnings are counted as banned."""
        login(client, "testadmin", "pass")
        # Control student with 2 active warnings — must NOT be counted.
        control = Student(student_id="900000222", display_name="TwoStrikes")
        db.session.add(control)
        db.session.commit()
        for i in range(2):
            db.session.add(
                Warning(
                    student_id=control.id,
                    area_id=seed["area_id"],
                    issued_by_id=seed["monitor_id"],
                    reason=f"c{i}",
                )
            )
        # Seed student gets 3 active warnings → banned.
        for i in range(3):
            db.session.add(
                Warning(
                    student_id=seed["student_id"],
                    area_id=seed["area_id"],
                    issued_by_id=seed["monitor_id"],
                    reason=f"s{i}",
                )
            )
        db.session.commit()

        resp = client.get("/admin/reports/safety")
        assert resp.status_code == 200
        assert b"Currently Banned Students" in resp.data
        # Exactly one banned student despite the 2-warning control existing.
        assert b'<h3 class="text-danger">1</h3>' in resp.data

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


# ---------------------------------------------------------------------------
# Faculty tests
# ---------------------------------------------------------------------------
@pytest.fixture
def faculty_seed(app):
    """Create faculty test data."""
    area = ShopArea.query.filter_by(name="Sculpture").first()

    faculty_admin = Faculty(
        username="testfaculty",
        display_name="Test Faculty",
        email="faculty@appstate.edu",
        is_primary_admin=True,
    )
    faculty_admin.set_password("pass")
    db.session.add(faculty_admin)

    faculty_member = Faculty(
        username="testinstructor",
        display_name="Test Instructor",
        email="instructor@appstate.edu",
        is_primary_admin=False,
    )
    faculty_member.set_password("pass")
    db.session.add(faculty_member)

    student = Student(
        student_id="900888888", display_name="Faculty Test Student", email="ftest@appstate.edu"
    )
    db.session.add(student)

    monitor = Monitor(username="facmon", display_name="Faculty Monitor")
    monitor.set_password("pass")
    monitor.areas.append(area)
    db.session.add(monitor)

    # Add equipment for training tests
    eq = Equipment.query.filter_by(area_id=area.id).first()
    if not eq:
        eq = Equipment(name="Test Equip", area_id=area.id, requires_training=True)
        db.session.add(eq)

    db.session.commit()

    return {
        "faculty_admin_id": faculty_admin.id,
        "faculty_member_id": faculty_member.id,
        "student_id": student.id,
        "student_banner_id": student.student_id,
        "area_id": area.id,
        "monitor_id": monitor.id,
        "equipment_id": eq.id,
    }


def faculty_login(client, username, password):
    return client.post(
        "/faculty/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


class TestFacultyAuth:
    def test_faculty_login_page_loads(self, client):
        resp = client.get("/faculty/login")
        assert resp.status_code == 200
        assert b"Faculty Sign In" in resp.data

    def test_faculty_login_success(self, client, faculty_seed):
        resp = faculty_login(client, "testfaculty", "pass")
        assert resp.status_code == 200
        assert b"Faculty Dashboard" in resp.data

    def test_faculty_login_failure(self, client, faculty_seed):
        resp = faculty_login(client, "testfaculty", "wrong")
        assert b"Invalid username or password" in resp.data

    def test_faculty_logout(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/logout", follow_redirects=True)
        assert b"Faculty Sign In" in resp.data

    def test_monitor_cannot_access_faculty_routes(self, client, faculty_seed):
        login(client, "facmon", "pass")
        resp = client.get("/faculty/", follow_redirects=True)
        assert b"Faculty access required" in resp.data

    def test_faculty_dashboard_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/")
        assert resp.status_code == 200
        assert b"Faculty Dashboard" in resp.data


class TestFacultyStudentManagement:
    def test_students_list_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/students")
        assert resp.status_code == 200
        assert b"Faculty Test Student" in resp.data

    def test_students_search(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/students?search=900888888")
        assert b"Faculty Test Student" in resp.data

    def test_add_student_page_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/students/add")
        assert resp.status_code == 200
        assert b"Add Student" in resp.data

    def test_add_student(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            "/faculty/students/add",
            data={
                "student_id": "900777777",
                "display_name": "New Student",
                "email": "new@appstate.edu",
            },
            follow_redirects=True,
        )
        assert b"New Student" in resp.data
        assert Student.query.filter_by(student_id="900777777").first() is not None

    def test_add_duplicate_student(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            "/faculty/students/add",
            data={
                "student_id": "900888888",
                "display_name": "Duplicate",
            },
            follow_redirects=True,
        )
        assert b"already exists" in resp.data

    def test_student_detail_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get(f"/faculty/students/{faculty_seed['student_id']}")
        assert resp.status_code == 200
        assert b"Faculty Test Student" in resp.data

    def test_edit_student(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            f"/faculty/students/{faculty_seed['student_id']}/edit",
            data={
                "display_name": "Updated Name",
                "email": "updated@appstate.edu",
            },
            follow_redirects=True,
        )
        assert b"Student information updated" in resp.data
        s = db.session.get(Student, faculty_seed["student_id"])
        assert s.display_name == "Updated Name"

    def test_add_student_with_canvas_user_id(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        client.post(
            "/faculty/students/add",
            data={
                "student_id": "900777000",
                "display_name": "Canvas Linked",
                "email": "cl@appstate.edu",
                "canvas_user_id": "123456",
            },
            follow_redirects=True,
        )
        s = Student.query.filter_by(student_id="900777000").first()
        assert s is not None
        assert s.canvas_user_id == "123456"

    def test_add_student_blank_canvas_id_stored_as_null(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        client.post(
            "/faculty/students/add",
            data={
                "student_id": "900777001",
                "display_name": "No Canvas",
                "canvas_user_id": "",
            },
            follow_redirects=True,
        )
        s = Student.query.filter_by(student_id="900777001").first()
        assert s is not None
        assert s.canvas_user_id is None

    def test_edit_student_sets_canvas_user_id(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        client.post(
            f"/faculty/students/{faculty_seed['student_id']}/edit",
            data={
                "display_name": "Faculty Test Student",
                "email": "ftest@appstate.edu",
                "canvas_user_id": "987654",
            },
            follow_redirects=True,
        )
        s = db.session.get(Student, faculty_seed["student_id"])
        assert s.canvas_user_id == "987654"

    def test_edit_student_clears_canvas_user_id(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        # First set it
        s = db.session.get(Student, faculty_seed["student_id"])
        s.canvas_user_id = "555555"
        db.session.commit()
        # Then clear it via the form
        client.post(
            f"/faculty/students/{faculty_seed['student_id']}/edit",
            data={
                "display_name": "Faculty Test Student",
                "email": "ftest@appstate.edu",
                "canvas_user_id": "",
            },
            follow_redirects=True,
        )
        s = db.session.get(Student, faculty_seed["student_id"])
        assert s.canvas_user_id is None

    def test_student_detail_shows_canvas_user_id(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        s = db.session.get(Student, faculty_seed["student_id"])
        s.canvas_user_id = "424242"
        db.session.commit()
        resp = client.get(f"/faculty/students/{faculty_seed['student_id']}")
        assert resp.status_code == 200
        assert b"424242" in resp.data
        assert b"Canvas User ID" in resp.data


class TestFacultyCSVUpload:
    def test_upload_page_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/students/upload")
        assert resp.status_code == 200
        assert b"Upload Students" in resp.data

    def test_csv_upload_success(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        csv_content = "banner_id,name,email\n900666666,CSV Student,csv@appstate.edu\n900555555,Another Student,another@appstate.edu"
        import io
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "students.csv"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"2 student(s) added" in resp.data
        assert Student.query.filter_by(student_id="900666666").first() is not None
        assert Student.query.filter_by(student_id="900555555").first() is not None

    def test_csv_upload_with_duplicates(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        csv_content = "banner_id,name,email\n900888888,Duplicate,dup@appstate.edu\n900444444,New One,new@appstate.edu"
        import io
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "students.csv"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 student(s) added" in resp.data
        assert b"1 skipped" in resp.data

    def test_csv_upload_alt_columns(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        csv_content = "student_id,display_name,email\n900333444,Alt Student,alt@appstate.edu"
        import io
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "students.csv"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 student(s) added" in resp.data

    def test_csv_upload_with_canvas_user_id(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        csv_content = (
            "banner_id,name,email,canvas_user_id\n"
            "900222111,Canvas CSV,cc@appstate.edu,111222\n"
            "900222112,No Canvas,nc@appstate.edu,\n"
        )
        import io
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "students.csv"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"2 student(s) added" in resp.data
        linked = Student.query.filter_by(student_id="900222111").first()
        unlinked = Student.query.filter_by(student_id="900222112").first()
        assert linked.canvas_user_id == "111222"
        assert unlinked.canvas_user_id is None

    def test_csv_upload_canvas_id_alias(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        csv_content = "banner_id,name,canvas_id\n900222113,Alias Student,999888\n"
        import io
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "students.csv"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 student(s) added" in resp.data
        s = Student.query.filter_by(student_id="900222113").first()
        assert s.canvas_user_id == "999888"

    def test_csv_upload_rejects_non_csv(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        import io
        data = {
            "csv_file": (io.BytesIO(b"not a csv"), "students.txt"),
        }
        resp = client.post(
            "/faculty/students/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"must be a CSV" in resp.data


class TestFacultyTraining:
    def test_training_page_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/training")
        assert resp.status_code == 200
        assert b"Training Certifications" in resp.data

    def test_grant_training(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            "/faculty/training/grant",
            data={
                "student_id": faculty_seed["student_id"],
                "equipment_id": faculty_seed["equipment_id"],
                "certified_semester": "Fall 2025",
            },
            follow_redirects=True,
        )
        assert b"granted" in resp.data

    def test_update_training(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        # First grant
        client.post(
            "/faculty/training/grant",
            data={
                "student_id": faculty_seed["student_id"],
                "equipment_id": faculty_seed["equipment_id"],
                "certified_semester": "Fall 2025",
            },
        )
        # Then update
        resp = client.post(
            "/faculty/training/update",
            data={
                "student_id": faculty_seed["student_id"],
                "equipment_id": faculty_seed["equipment_id"],
                "certified_semester": "Spring 2026",
            },
            follow_redirects=True,
        )
        assert b"updated" in resp.data

    def test_revoke_training(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        # Grant first
        client.post(
            "/faculty/training/grant",
            data={
                "student_id": faculty_seed["student_id"],
                "equipment_id": faculty_seed["equipment_id"],
            },
        )
        # Revoke
        resp = client.post(
            "/faculty/training/revoke",
            data={
                "student_id": faculty_seed["student_id"],
                "equipment_id": faculty_seed["equipment_id"],
            },
            follow_redirects=True,
        )
        assert b"revoked" in resp.data

    def test_training_filter_by_area(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get(f"/faculty/training?area_id={faculty_seed['area_id']}")
        assert resp.status_code == 200


class TestFacultyMonitorManagement:
    def test_monitors_page_requires_primary_admin(self, client, faculty_seed):
        faculty_login(client, "testinstructor", "pass")
        resp = client.get("/faculty/monitors", follow_redirects=True)
        assert b"Primary admin access required" in resp.data

    def test_monitors_page_loads_for_primary_admin(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/monitors")
        assert resp.status_code == 200
        assert b"Monitor Management" in resp.data

    def test_add_monitor(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            "/faculty/monitors/add",
            data={
                "username": "newmon",
                "display_name": "New Monitor",
                "password": "testpass",
                "area_ids": [faculty_seed["area_id"]],
            },
            follow_redirects=True,
        )
        assert b"New Monitor" in resp.data
        assert Monitor.query.filter_by(username="newmon").first() is not None

    def test_edit_monitor(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            f"/faculty/monitors/{faculty_seed['monitor_id']}/edit",
            data={
                "display_name": "Updated Monitor",
                "area_ids": [faculty_seed["area_id"]],
            },
            follow_redirects=True,
        )
        assert b"Monitor updated" in resp.data

    def test_faculty_accounts_page_loads(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.get("/faculty/faculty-accounts")
        assert resp.status_code == 200
        assert b"Faculty Accounts" in resp.data

    def test_add_faculty_account(self, client, faculty_seed):
        faculty_login(client, "testfaculty", "pass")
        resp = client.post(
            "/faculty/faculty-accounts/add",
            data={
                "username": "newfac",
                "display_name": "New Faculty",
                "email": "newfac@appstate.edu",
                "password": "testpass",
            },
            follow_redirects=True,
        )
        assert b"New Faculty" in resp.data
        assert Faculty.query.filter_by(username="newfac").first() is not None
