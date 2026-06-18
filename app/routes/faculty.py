import csv
import io
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    Response,
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    Faculty,
    Monitor,
    Student,
    ShopArea,
    Equipment,
    Warning,
    student_training,
    monitor_areas,
)
from app.routes import is_safe_redirect_url, get_live_shop_state
from app.utils import is_valid_banner_id

faculty_bp = Blueprint("faculty", __name__)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
def faculty_required(f):
    """Ensure the current user is an authenticated Faculty member."""

    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not hasattr(current_user, "user_type") or current_user.user_type != "faculty":
            flash("Faculty access required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def primary_admin_required(f):
    """Ensure the current user is the primary faculty admin."""

    @wraps(f)
    @faculty_required
    def decorated(*args, **kwargs):
        if not current_user.is_primary_admin:
            flash("Primary admin access required.", "danger")
            return redirect(url_for("faculty.dashboard"))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@faculty_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if hasattr(current_user, "user_type") and current_user.user_type == "faculty":
            return redirect(url_for("faculty.dashboard"))
        return redirect(url_for("monitor.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        faculty = Faculty.query.filter_by(username=username).first()
        if faculty and faculty.check_password(password):
            login_user(faculty)
            next_page = request.args.get("next")
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for("faculty.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("faculty/login.html")


@faculty_bp.route("/change-password", methods=["GET", "POST"])
@faculty_required
def change_password():
    """Let a faculty member change their own password."""
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current_user.check_password(current):
            flash("Current password is incorrect.", "danger")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "danger")
        elif new != confirm:
            flash("New passwords do not match.", "danger")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Your password has been updated.", "success")
            return redirect(url_for("faculty.dashboard"))

    return render_template("auth/change_password.html")


@faculty_bp.route("/logout")
@faculty_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("faculty.login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@faculty_bp.route("/")
@faculty_required
def dashboard():
    students_count = Student.query.count()
    monitors_count = Monitor.query.count()
    areas = ShopArea.query.order_by(ShopArea.name).all()

    # Count students with at least one training record
    trained_count = (
        db.session.query(student_training.c.student_id)
        .distinct()
        .count()
    )

    return render_template(
        "faculty/dashboard.html",
        students_count=students_count,
        monitors_count=monitors_count,
        areas=areas,
        trained_count=trained_count,
    )


@faculty_bp.route("/live")
@faculty_required
def live():
    """Department-wide view of who is currently in each shop area."""
    shop_state = get_live_shop_state()
    total_students = sum(len(a["visits"]) for a in shop_state)
    total_monitors = sum(len(a["monitors"]) for a in shop_state)
    return render_template(
        "live_shop.html",
        shop_state=shop_state,
        total_students=total_students,
        total_monitors=total_monitors,
    )


# ---------------------------------------------------------------------------
# Student management
# ---------------------------------------------------------------------------
@faculty_bp.route("/students")
@faculty_required
def students():
    search = request.args.get("search", "").strip()
    if search:
        students_list = Student.query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.display_name.ilike(f"%{search}%"),
                Student.email.ilike(f"%{search}%"),
            )
        ).order_by(Student.display_name).all()
    else:
        students_list = Student.query.order_by(Student.display_name).all()

    return render_template(
        "faculty/students.html",
        students=students_list,
        search=search,
    )


@faculty_bp.route("/students/export")
@faculty_required
def export_students():
    """Export the (optionally filtered) student roster as CSV."""
    search = request.args.get("search", "").strip()
    query = Student.query
    if search:
        query = query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.display_name.ilike(f"%{search}%"),
                Student.email.ilike(f"%{search}%"),
            )
        )
    students_list = query.order_by(Student.display_name).all()

    # Active-warning counts in a single grouped query (avoid N+1 per student).
    warn_counts = dict(
        db.session.query(Warning.student_id, func.count(Warning.id))
        .filter(Warning.resolved.is_(False))
        .group_by(Warning.student_id)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Banner ID", "Name", "Email", "Canvas User ID", "Enrollment Term",
         "Active Warnings", "Banned"]
    )
    for s in students_list:
        cnt = warn_counts.get(s.id, 0)
        writer.writerow([
            s.student_id,
            s.display_name,
            s.email or "",
            s.canvas_user_id or "",
            s.enrollment_term or "",
            cnt,
            "Yes" if cnt >= 3 else "No",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"},
    )


@faculty_bp.route("/students/add", methods=["GET", "POST"])
@faculty_required
def add_student():
    if request.method == "POST":
        banner_id = request.form.get("student_id", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip() or None
        canvas_user_id = request.form.get("canvas_user_id", "").strip() or None

        if not banner_id or not display_name:
            flash("Banner ID and name are required.", "danger")
            return render_template("faculty/add_student.html")

        if not is_valid_banner_id(banner_id):
            flash("Banner ID must be exactly 9 digits.", "danger")
            return render_template("faculty/add_student.html")

        if Student.query.filter_by(student_id=banner_id).first():
            flash(f"A student with Banner ID {banner_id} already exists.", "warning")
            return render_template("faculty/add_student.html")

        student = Student(
            student_id=banner_id,
            display_name=display_name,
            email=email,
            canvas_user_id=canvas_user_id,
        )
        db.session.add(student)
        db.session.commit()
        flash(f"Student {display_name} ({banner_id}) added.", "success")
        return redirect(url_for("faculty.students"))

    return render_template("faculty/add_student.html")


@faculty_bp.route("/students/upload", methods=["GET", "POST"])
@faculty_required
def upload_students():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename:
            flash("Please select a CSV file.", "danger")
            return render_template("faculty/upload_students.html")

        if not file.filename.lower().endswith(".csv"):
            flash("File must be a CSV.", "danger")
            return render_template("faculty/upload_students.html")

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
            reader = csv.DictReader(stream)

            # Normalize column headers (strip whitespace, lowercase)
            if reader.fieldnames is None:
                flash("CSV file appears to be empty.", "danger")
                return render_template("faculty/upload_students.html")

            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

            # Validate required columns
            required_cols = {"banner_id", "name"}
            # Also accept alternative column names
            alt_mappings = {
                "student_id": "banner_id",
                "id": "banner_id",
                "display_name": "name",
                "full_name": "name",
                "student_name": "name",
                "canvas_id": "canvas_user_id",
                "canvas": "canvas_user_id",
            }

            available = set(reader.fieldnames)
            # Apply alternative mappings
            col_map = {}
            for col in reader.fieldnames:
                if col in alt_mappings:
                    col_map[alt_mappings[col]] = col
                else:
                    col_map[col] = col

            if "banner_id" not in col_map and "name" not in col_map:
                flash(
                    "CSV must have columns: banner_id (or student_id), name (or display_name). "
                    f"Found: {', '.join(reader.fieldnames)}",
                    "danger",
                )
                return render_template("faculty/upload_students.html")

            banner_col = col_map.get("banner_id")
            name_col = col_map.get("name")
            email_col = col_map.get("email")
            canvas_col = col_map.get("canvas_user_id")

            if not banner_col or not name_col:
                flash(
                    "CSV must have columns: banner_id (or student_id), name (or display_name). "
                    f"Found: {', '.join(reader.fieldnames)}",
                    "danger",
                )
                return render_template("faculty/upload_students.html")

            added = 0
            skipped = 0
            errors = []
            seen_ids = set()  # Banner IDs already handled in THIS file

            for row_num, row in enumerate(reader, start=2):
                banner_id = (row.get(banner_col) or "").strip()
                name = (row.get(name_col) or "").strip()
                email = (row.get(email_col) or "").strip() if email_col else None
                canvas_user_id = (
                    (row.get(canvas_col) or "").strip() if canvas_col else None
                )

                if not banner_id or not name:
                    errors.append(f"Row {row_num}: missing banner_id or name")
                    continue

                if not is_valid_banner_id(banner_id):
                    errors.append(
                        f"Row {row_num}: Banner ID '{banner_id}' must be exactly 9 digits"
                    )
                    continue

                # Skip duplicates within the same file as well as against the DB.
                # Without the in-batch check, two identical IDs both pass the DB
                # lookup (neither is committed yet) and the final commit fails
                # with an IntegrityError, discarding the entire upload.
                if banner_id in seen_ids:
                    skipped += 1
                    continue

                if Student.query.filter_by(student_id=banner_id).first():
                    skipped += 1
                    seen_ids.add(banner_id)
                    continue

                student = Student(
                    student_id=banner_id,
                    display_name=name,
                    email=email or None,
                    canvas_user_id=canvas_user_id or None,
                )
                db.session.add(student)
                seen_ids.add(banner_id)
                added += 1

            db.session.commit()

            msg = f"Upload complete: {added} student(s) added"
            if skipped:
                msg += f", {skipped} skipped (already exist)"
            if errors:
                msg += f", {len(errors)} error(s)"
            flash(msg, "success" if added > 0 else "info")

            if errors:
                for err in errors[:10]:
                    flash(err, "warning")
                if len(errors) > 10:
                    flash(f"... and {len(errors) - 10} more errors.", "warning")

        except Exception as e:
            db.session.rollback()
            flash(f"Error processing CSV: {str(e)}", "danger")

        return redirect(url_for("faculty.upload_students"))

    return render_template("faculty/upload_students.html")


@faculty_bp.route("/students/<int:student_id>")
@faculty_required
def student_detail(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("faculty.students"))

    # Get all training records with equipment and area info
    training_rows = (
        db.session.query(
            Equipment.name,
            Equipment.id.label("equipment_id"),
            ShopArea.name.label("area_name"),
            student_training.c.certified_semester,
            student_training.c.source,
        )
        .select_from(student_training)
        .join(Equipment, Equipment.id == student_training.c.equipment_id)
        .join(ShopArea, ShopArea.id == Equipment.area_id)
        .filter(student_training.c.student_id == student.id)
        .order_by(ShopArea.name, Equipment.name)
        .all()
    )

    areas = ShopArea.query.order_by(ShopArea.name).all()
    all_equipment = Equipment.query.filter_by(requires_training=True).order_by(
        Equipment.area_id, Equipment.name
    ).all()

    return render_template(
        "faculty/student_detail.html",
        student=student,
        training_records=training_rows,
        areas=areas,
        all_equipment=all_equipment,
    )


@faculty_bp.route("/students/<int:student_id>/edit", methods=["POST"])
@faculty_required
def edit_student(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("faculty.students"))

    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip() or None
    canvas_user_id = request.form.get("canvas_user_id", "").strip() or None

    if not display_name:
        flash("Display name is required.", "danger")
        return redirect(url_for("faculty.student_detail", student_id=student_id))

    student.display_name = display_name
    student.email = email
    student.canvas_user_id = canvas_user_id
    db.session.commit()
    flash("Student information updated.", "success")
    return redirect(url_for("faculty.student_detail", student_id=student_id))


# ---------------------------------------------------------------------------
# Training / certification management
# ---------------------------------------------------------------------------
@faculty_bp.route("/training")
@faculty_required
def training():
    """Overview of all training certifications, filterable by area."""
    area_id = request.args.get("area_id", type=int)
    search = request.args.get("search", "").strip()

    areas = ShopArea.query.order_by(ShopArea.name).all()

    query = (
        db.session.query(
            Student.id.label("student_id"),
            Student.student_id.label("banner_id"),
            Student.display_name,
            Equipment.name.label("equipment_name"),
            ShopArea.name.label("area_name"),
            student_training.c.certified_semester,
            student_training.c.source,
        )
        .select_from(student_training)
        .join(Student, Student.id == student_training.c.student_id)
        .join(Equipment, Equipment.id == student_training.c.equipment_id)
        .join(ShopArea, ShopArea.id == Equipment.area_id)
    )

    if area_id:
        query = query.filter(Equipment.area_id == area_id)
    if search:
        query = query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.display_name.ilike(f"%{search}%"),
            )
        )

    records = query.order_by(Student.display_name, ShopArea.name, Equipment.name).all()

    return render_template(
        "faculty/training.html",
        records=records,
        areas=areas,
        selected_area_id=area_id,
        search=search,
    )


@faculty_bp.route("/training/export")
@faculty_required
def export_training():
    """Export the (optionally filtered) training matrix as CSV."""
    area_id = request.args.get("area_id", type=int)
    search = request.args.get("search", "").strip()

    query = (
        db.session.query(
            Student.student_id.label("banner_id"),
            Student.display_name,
            Equipment.name.label("equipment_name"),
            ShopArea.name.label("area_name"),
            student_training.c.certified_semester,
            student_training.c.source,
        )
        .select_from(student_training)
        .join(Student, Student.id == student_training.c.student_id)
        .join(Equipment, Equipment.id == student_training.c.equipment_id)
        .join(ShopArea, ShopArea.id == Equipment.area_id)
    )
    if area_id:
        query = query.filter(Equipment.area_id == area_id)
    if search:
        query = query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.display_name.ilike(f"%{search}%"),
            )
        )
    records = query.order_by(
        Student.display_name, ShopArea.name, Equipment.name
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Banner ID", "Name", "Certification", "Area", "Semester", "Source"]
    )
    for r in records:
        writer.writerow([
            r.banner_id,
            r.display_name,
            r.equipment_name,
            r.area_name,
            r.certified_semester or "",
            r.source or "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=training_records.csv"},
    )


@faculty_bp.route("/training/grant", methods=["POST"])
@faculty_required
def grant_training():
    student_id = request.form.get("student_id", type=int)
    equipment_id = request.form.get("equipment_id", type=int)
    certified_semester = request.form.get("certified_semester", "").strip() or None

    student = db.session.get(Student, student_id)
    eq = db.session.get(Equipment, equipment_id)
    if not student or not eq:
        flash("Invalid student or equipment.", "danger")
        return redirect(request.referrer or url_for("faculty.training"))

    if eq not in student.trained_equipment:
        db.session.execute(
            student_training.insert().values(
                student_id=student.id,
                equipment_id=eq.id,
                certified_semester=certified_semester,
                source="manual",
            )
        )
        db.session.commit()
        label = certified_semester or "no semester specified"
        flash(
            f"Training on '{eq.name}' granted to {student.display_name} ({label}).",
            "success",
        )
    else:
        flash("Student already has this training.", "info")

    return redirect(request.referrer or url_for("faculty.training"))


@faculty_bp.route("/training/update", methods=["POST"])
@faculty_required
def update_training():
    """Update the semester for an existing training certification."""
    student_id = request.form.get("student_id", type=int)
    equipment_id = request.form.get("equipment_id", type=int)
    certified_semester = request.form.get("certified_semester", "").strip() or None

    student = db.session.get(Student, student_id)
    eq = db.session.get(Equipment, equipment_id)
    if not student or not eq:
        flash("Invalid student or equipment.", "danger")
        return redirect(request.referrer or url_for("faculty.training"))

    if eq in student.trained_equipment:
        db.session.execute(
            student_training.update()
            .where(
                db.and_(
                    student_training.c.student_id == student.id,
                    student_training.c.equipment_id == eq.id,
                )
            )
            .values(certified_semester=certified_semester)
        )
        db.session.commit()
        flash(f"Training record for '{eq.name}' updated.", "success")
    else:
        flash("No existing training record found to update.", "warning")

    return redirect(request.referrer or url_for("faculty.training"))


@faculty_bp.route("/training/revoke", methods=["POST"])
@faculty_required
def revoke_training():
    student_id = request.form.get("student_id", type=int)
    equipment_id = request.form.get("equipment_id", type=int)

    student = db.session.get(Student, student_id)
    eq = db.session.get(Equipment, equipment_id)
    if not student or not eq:
        flash("Invalid student or equipment.", "danger")
        return redirect(request.referrer or url_for("faculty.training"))

    if eq in student.trained_equipment:
        student.trained_equipment.remove(eq)
        db.session.commit()
        flash(f"Training on '{eq.name}' revoked for {student.display_name}.", "info")

    return redirect(request.referrer or url_for("faculty.training"))


# ---------------------------------------------------------------------------
# Monitor management (primary admin only)
# ---------------------------------------------------------------------------
@faculty_bp.route("/monitors")
@primary_admin_required
def monitors():
    monitors_list = Monitor.query.order_by(Monitor.display_name).all()
    areas = ShopArea.query.order_by(ShopArea.name).all()
    return render_template(
        "faculty/monitors.html",
        monitors=monitors_list,
        areas=areas,
    )


@faculty_bp.route("/monitors/add", methods=["GET", "POST"])
@primary_admin_required
def add_monitor():
    areas = ShopArea.query.order_by(ShopArea.name).all()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        is_admin = request.form.get("is_admin") == "on"
        area_ids = request.form.getlist("area_ids", type=int)

        if not username or not display_name or not password:
            flash("All fields are required.", "danger")
            return render_template("faculty/add_monitor.html", areas=areas)

        if Monitor.query.filter_by(username=username).first():
            flash("Username already taken.", "warning")
            return render_template("faculty/add_monitor.html", areas=areas)

        monitor = Monitor(
            username=username, display_name=display_name, is_admin=is_admin
        )
        monitor.set_password(password)
        for aid in area_ids:
            area = db.session.get(ShopArea, aid)
            if area:
                monitor.areas.append(area)

        db.session.add(monitor)
        db.session.commit()
        flash(f"Monitor {display_name} created.", "success")
        return redirect(url_for("faculty.monitors"))

    return render_template("faculty/add_monitor.html", areas=areas)


@faculty_bp.route("/monitors/<int:monitor_id>/edit", methods=["GET", "POST"])
@primary_admin_required
def edit_monitor(monitor_id):
    monitor = db.session.get(Monitor, monitor_id)
    if not monitor:
        flash("Monitor not found.", "danger")
        return redirect(url_for("faculty.monitors"))

    areas = ShopArea.query.order_by(ShopArea.name).all()

    if request.method == "POST":
        monitor.display_name = request.form.get("display_name", "").strip()
        monitor.is_admin = request.form.get("is_admin") == "on"
        new_password = request.form.get("password", "").strip()
        if new_password:
            monitor.set_password(new_password)

        area_ids = request.form.getlist("area_ids", type=int)
        monitor.areas = [
            db.session.get(ShopArea, aid)
            for aid in area_ids
            if db.session.get(ShopArea, aid)
        ]
        db.session.commit()
        flash("Monitor updated.", "success")
        return redirect(url_for("faculty.monitors"))

    return render_template(
        "faculty/edit_monitor.html", monitor=monitor, areas=areas
    )


@faculty_bp.route("/faculty-accounts")
@primary_admin_required
def faculty_accounts():
    """View and manage other faculty accounts (primary admin only)."""
    faculty_list = Faculty.query.order_by(Faculty.display_name).all()
    return render_template("faculty/faculty_accounts.html", faculty_list=faculty_list)


@faculty_bp.route("/faculty-accounts/add", methods=["GET", "POST"])
@primary_admin_required
def add_faculty():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        is_primary = request.form.get("is_primary_admin") == "on"

        if not username or not display_name or not password:
            flash("Username, display name, and password are required.", "danger")
            return render_template("faculty/add_faculty.html")

        if Faculty.query.filter_by(username=username).first():
            flash("Username already taken.", "warning")
            return render_template("faculty/add_faculty.html")

        faculty = Faculty(
            username=username,
            display_name=display_name,
            email=email,
            is_primary_admin=is_primary,
        )
        faculty.set_password(password)
        db.session.add(faculty)
        db.session.commit()
        flash(f"Faculty account {display_name} created.", "success")
        return redirect(url_for("faculty.faculty_accounts"))

    return render_template("faculty/add_faculty.html")
