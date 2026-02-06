from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import (
    Student,
    StudentVisit,
    MonitorSession,
    ShopArea,
    Equipment,
)

student_bp = Blueprint("student", __name__)


@student_bp.route("/lookup", methods=["GET", "POST"])
@login_required
def lookup():
    """Monitor looks up a student by ID to begin sign-in."""
    active_session = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()

    if not active_session:
        flash("You must be signed in to an area before signing students in.", "warning")
        return redirect(url_for("monitor.dashboard"))

    if request.method == "POST":
        student_id_input = request.form.get("student_id", "").strip()
        student = Student.query.filter_by(student_id=student_id_input).first()

        if not student:
            flash(
                f'No student found with ID "{student_id_input}". '
                "You may need to register them first.",
                "warning",
            )
            return redirect(
                url_for("student.register", prefill_id=student_id_input)
            )

        return redirect(
            url_for(
                "student.confirm_sign_in",
                student_id=student.id,
                area_id=active_session.area_id,
            )
        )

    return render_template("student/lookup.html", active_session=active_session)


@student_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    """Register a new student in the system."""
    if request.method == "POST":
        sid = request.form.get("student_id", "").strip()
        name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip() or None

        if not sid or not name:
            flash("Student ID and name are required.", "danger")
            return render_template("student/register.html", prefill_id=sid)

        if Student.query.filter_by(student_id=sid).first():
            flash("A student with that ID already exists.", "warning")
            return redirect(url_for("student.lookup"))

        student = Student(student_id=sid, display_name=name, email=email)
        db.session.add(student)
        db.session.commit()
        flash(f"Student {name} registered.", "success")
        return redirect(url_for("student.lookup"))

    prefill_id = request.args.get("prefill_id", "")
    return render_template("student/register.html", prefill_id=prefill_id)


@student_bp.route("/confirm-sign-in/<int:student_id>/<int:area_id>")
@login_required
def confirm_sign_in(student_id, area_id):
    """
    Monitor reviews student info before acknowledging sign-in.
    Shows training status, warnings, and care notes.
    """
    student = db.session.get(Student, student_id)
    area = db.session.get(ShopArea, area_id)
    if not student or not area:
        flash("Invalid student or area.", "danger")
        return redirect(url_for("student.lookup"))

    # Equipment in this area that requires training
    area_equipment = Equipment.query.filter_by(
        area_id=area.id, requires_training=True
    ).all()

    # Which of those the student is trained on
    trained_ids = {e.id for e in student.trained_equipment}
    equipment_status = [
        {"equipment": eq, "trained": eq.id in trained_ids} for eq in area_equipment
    ]

    return render_template(
        "student/confirm_sign_in.html",
        student=student,
        area=area,
        equipment_status=equipment_status,
    )


@student_bp.route("/sign-in", methods=["POST"])
@login_required
def sign_in():
    """
    Monitor acknowledges and signs a student in.
    Enforces: active monitor session, no ban (3 strikes), no duplicate active visit.
    """
    student_id = request.form.get("student_id", type=int)
    area_id = request.form.get("area_id", type=int)

    student = db.session.get(Student, student_id)
    area = db.session.get(ShopArea, area_id)
    if not student or not area:
        flash("Invalid student or area.", "danger")
        return redirect(url_for("student.lookup"))

    # Must have an active monitor session
    active_session = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()
    if not active_session or active_session.area_id != area.id:
        flash("You must be signed in to this area to admit students.", "danger")
        return redirect(url_for("monitor.dashboard"))

    # 3-strike ban check
    if student.is_banned:
        flash(
            f"{student.display_name} has 3 or more active warnings and cannot sign in.",
            "danger",
        )
        return redirect(url_for("monitor.dashboard"))

    # Already signed in?
    existing_visit = StudentVisit.query.filter_by(
        student_id=student.id, area_id=area.id, signed_out_at=None
    ).first()
    if existing_visit:
        flash(f"{student.display_name} is already signed in to {area.name}.", "warning")
        return redirect(url_for("monitor.dashboard"))

    visit = StudentVisit(
        student_id=student.id,
        area_id=area.id,
        acknowledged_by_id=current_user.id,
    )
    db.session.add(visit)
    db.session.commit()
    flash(f"{student.display_name} signed in to {area.name}.", "success")
    return redirect(url_for("monitor.dashboard"))


@student_bp.route("/sign-out/<int:visit_id>", methods=["POST"])
@login_required
def sign_out(visit_id):
    """Sign a student out of their current visit."""
    visit = db.session.get(StudentVisit, visit_id)
    if not visit or visit.signed_out_at is not None:
        flash("Invalid or already completed visit.", "warning")
        return redirect(url_for("monitor.dashboard"))

    visit.signed_out_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"{visit.student.display_name} signed out of {visit.area.name}.", "info")
    return redirect(url_for("monitor.dashboard"))
