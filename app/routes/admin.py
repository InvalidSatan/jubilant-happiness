from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import (
    Monitor,
    ShopArea,
    Equipment,
    Student,
    Warning,
    MonitorSession,
    StudentVisit,
    monitor_areas,
    student_training,
)
from app.routes import bounce_faculty_to_dashboard

admin_bp = Blueprint("admin", __name__)
admin_bp.before_request(bounce_faculty_to_dashboard)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        # getattr guards against non-Monitor users (e.g. Faculty) that lack the
        # is_admin attribute; the blueprint guard already redirects faculty, so
        # this is belt-and-suspenders.
        if not getattr(current_user, "is_admin", False):
            flash("Admin access required.", "danger")
            return redirect(url_for("monitor.dashboard"))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/")
@admin_required
def index():
    from app.routes.integration import integration_status

    monitors = Monitor.query.order_by(Monitor.display_name).all()
    areas = ShopArea.query.order_by(ShopArea.name).all()
    students_count = Student.query.count()
    active_monitor_sessions = MonitorSession.query.filter_by(signed_out_at=None).count()
    active_student_visits = StudentVisit.query.filter_by(signed_out_at=None).count()
    return render_template(
        "admin/index.html",
        monitors=monitors,
        areas=areas,
        students_count=students_count,
        active_monitor_sessions=active_monitor_sessions,
        active_student_visits=active_student_visits,
        integrations=integration_status(),
    )


# ---------------------------------------------------------------------------
# Monitor management
# ---------------------------------------------------------------------------
@admin_bp.route("/monitors/add", methods=["GET", "POST"])
@admin_required
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
            return render_template("admin/add_monitor.html", areas=areas)

        if Monitor.query.filter_by(username=username).first():
            flash("Username already taken.", "warning")
            return render_template("admin/add_monitor.html", areas=areas)

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
        return redirect(url_for("admin.index"))

    return render_template("admin/add_monitor.html", areas=areas)


@admin_bp.route("/monitors/<int:monitor_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_monitor(monitor_id):
    monitor = db.session.get(Monitor, monitor_id)
    if not monitor:
        flash("Monitor not found.", "danger")
        return redirect(url_for("admin.index"))

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
        return redirect(url_for("admin.index"))

    return render_template("admin/edit_monitor.html", monitor=monitor, areas=areas)


# ---------------------------------------------------------------------------
# Equipment management
# ---------------------------------------------------------------------------
@admin_bp.route("/equipment", methods=["GET", "POST"])
@admin_required
def equipment():
    areas = ShopArea.query.order_by(ShopArea.name).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        area_id = request.form.get("area_id", type=int)
        requires_training = request.form.get("requires_training") == "on"

        if not name or not area_id:
            flash("Name and area are required.", "danger")
        else:
            eq = Equipment(
                name=name, area_id=area_id, requires_training=requires_training
            )
            db.session.add(eq)
            db.session.commit()
            flash(f"Equipment '{name}' added.", "success")

        return redirect(url_for("admin.equipment"))

    all_equipment = Equipment.query.order_by(Equipment.area_id, Equipment.name).all()
    return render_template(
        "admin/equipment.html", areas=areas, all_equipment=all_equipment
    )


# ---------------------------------------------------------------------------
# Training / certification management
# ---------------------------------------------------------------------------
@admin_bp.route("/training/grant", methods=["POST"])
@admin_required
def grant_training():
    student_id = request.form.get("student_id", type=int)
    equipment_id = request.form.get("equipment_id", type=int)
    certified_semester = request.form.get("certified_semester", "").strip() or None

    student = db.session.get(Student, student_id)
    eq = db.session.get(Equipment, equipment_id)
    if not student or not eq:
        flash("Invalid student or equipment.", "danger")
        return redirect(request.referrer or url_for("admin.index"))

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

    return redirect(request.referrer or url_for("admin.index"))


@admin_bp.route("/training/revoke", methods=["POST"])
@admin_required
def revoke_training():
    student_id = request.form.get("student_id", type=int)
    equipment_id = request.form.get("equipment_id", type=int)

    student = db.session.get(Student, student_id)
    eq = db.session.get(Equipment, equipment_id)
    if not student or not eq:
        flash("Invalid student or equipment.", "danger")
        return redirect(request.referrer or url_for("admin.index"))

    if eq in student.trained_equipment:
        student.trained_equipment.remove(eq)
        db.session.commit()
        flash(f"Training on '{eq.name}' revoked.", "info")

    return redirect(request.referrer or url_for("admin.index"))


# ---------------------------------------------------------------------------
# Warning / strike management
# ---------------------------------------------------------------------------
@admin_bp.route("/warnings")
@admin_required
def warnings():
    all_warnings = (
        Warning.query.order_by(Warning.created_at.desc()).limit(100).all()
    )
    return render_template("admin/warnings.html", warnings=all_warnings)


@admin_bp.route("/warnings/issue", methods=["POST"])
@login_required
def issue_warning():
    """Any monitor can issue a warning (not just admin)."""
    student_id = request.form.get("student_id", type=int)
    area_id = request.form.get("area_id", type=int)
    reason = request.form.get("reason", "").strip()

    if not student_id or not area_id or not reason:
        flash("Student, area, and reason are required.", "danger")
        return redirect(request.referrer or url_for("monitor.dashboard"))

    warning = Warning(
        student_id=student_id,
        area_id=area_id,
        issued_by_id=current_user.id,
        reason=reason,
    )
    db.session.add(warning)
    db.session.commit()

    student = db.session.get(Student, student_id)
    count = student.active_warnings_count if student else 0
    flash(
        f"Warning issued. {student.display_name} now has {count} active warning(s).",
        "warning",
    )
    if count >= 3:
        flash(
            f"{student.display_name} has reached 3 strikes and is now banned from signing in.",
            "danger",
        )

    return redirect(request.referrer or url_for("monitor.dashboard"))


@admin_bp.route("/warnings/<int:warning_id>/resolve", methods=["POST"])
@admin_required
def resolve_warning(warning_id):
    warning = db.session.get(Warning, warning_id)
    if not warning:
        flash("Warning not found.", "danger")
        return redirect(url_for("admin.warnings"))

    warning.resolved = True
    warning.resolved_by_id = current_user.id
    warning.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("Warning resolved.", "success")
    return redirect(url_for("admin.warnings"))
