from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import (
    MonitorSession,
    ShopArea,
    StudentVisit,
    Student,
    Warning,
    student_training,
    Equipment,
)

monitor_bp = Blueprint("monitor", __name__)


@monitor_bp.route("/dashboard")
@login_required
def dashboard():
    """Main monitor dashboard showing their active area session and current visitors."""
    active_session = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()

    active_visitors = []
    if active_session:
        active_visitors = (
            StudentVisit.query.filter_by(
                area_id=active_session.area_id, signed_out_at=None
            )
            .order_by(StudentVisit.signed_in_at.desc())
            .all()
        )

    areas = ShopArea.query.order_by(ShopArea.name).all()
    return render_template(
        "monitor/dashboard.html",
        active_session=active_session,
        active_visitors=active_visitors,
        areas=areas,
    )


@monitor_bp.route("/sign-in", methods=["POST"])
@login_required
def sign_in():
    """Monitor signs in to oversee a specific area."""
    area_id = request.form.get("area_id", type=int)
    area = db.session.get(ShopArea, area_id)
    if not area:
        flash("Invalid shop area.", "danger")
        return redirect(url_for("monitor.dashboard"))

    # Check monitor is authorized for this area
    if area not in current_user.areas:
        flash("You are not authorized to monitor that area.", "danger")
        return redirect(url_for("monitor.dashboard"))

    # End any existing active session first
    existing = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).all()
    for s in existing:
        s.signed_out_at = datetime.now(timezone.utc)

    session = MonitorSession(
        monitor_id=current_user.id,
        area_id=area.id,
    )
    db.session.add(session)
    db.session.commit()
    flash(f"Signed in to {area.name}.", "success")
    return redirect(url_for("monitor.dashboard"))


@monitor_bp.route("/sign-out", methods=["POST"])
@login_required
def sign_out():
    """Monitor signs out of their current area session."""
    active = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()
    if active:
        active.signed_out_at = datetime.now(timezone.utc)

        # Also sign out any students still in that area
        open_visits = StudentVisit.query.filter_by(
            area_id=active.area_id, signed_out_at=None
        ).all()
        for v in open_visits:
            v.signed_out_at = datetime.now(timezone.utc)

        db.session.commit()
        flash("Signed out. All remaining students in the area have been signed out.", "info")
    else:
        flash("No active session to end.", "warning")
    return redirect(url_for("monitor.dashboard"))


@monitor_bp.route("/student/<int:student_id>")
@login_required
def student_detail(student_id):
    """View full details on a student (training, warnings, care notes)."""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("monitor.dashboard"))

    warnings = (
        Warning.query.filter_by(student_id=student.id)
        .order_by(Warning.created_at.desc())
        .all()
    )
    visits = (
        StudentVisit.query.filter_by(student_id=student.id)
        .order_by(StudentVisit.signed_in_at.desc())
        .limit(20)
        .all()
    )

    # Build training records with semester info
    training_records = (
        db.session.query(
            Equipment.name,
            Equipment.id,
            ShopArea.name.label("area_name"),
            student_training.c.certified_semester,
        )
        .join(Equipment, student_training.c.equipment_id == Equipment.id)
        .join(ShopArea, Equipment.area_id == ShopArea.id)
        .filter(student_training.c.student_id == student.id)
        .order_by(ShopArea.name, Equipment.name)
        .all()
    )

    return render_template(
        "monitor/student_detail.html",
        student=student,
        warnings=warnings,
        visits=visits,
        training_records=training_records,
    )


@monitor_bp.route("/student/<int:student_id>/care-note", methods=["POST"])
@login_required
def update_care_note(student_id):
    """Update the private care note for a student."""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("monitor.dashboard"))

    student.care_note = request.form.get("care_note", "").strip() or None
    db.session.commit()
    flash("Care note updated.", "success")
    return redirect(url_for("monitor.student_detail", student_id=student.id))


@monitor_bp.route("/history")
@login_required
def session_history():
    """View past monitor sessions."""
    sessions = (
        MonitorSession.query.filter_by(monitor_id=current_user.id)
        .order_by(MonitorSession.signed_in_at.desc())
        .limit(50)
        .all()
    )
    return render_template("monitor/history.html", sessions=sessions)
