from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user

from app import db
from app.models import (
    Student,
    StudentVisit,
    MonitorSession,
)
from app.utils import is_valid_banner_id

kiosk_bp = Blueprint("kiosk", __name__)


@kiosk_bp.route("/")
@login_required
def index():
    """Kiosk home screen — large Banner ID input for self-service sign-in/out."""
    active_session = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()
    if not active_session:
        return redirect(url_for("monitor.dashboard"))

    visitor_count = StudentVisit.query.filter_by(
        area_id=active_session.area_id, signed_out_at=None
    ).count()

    return render_template(
        "kiosk/index.html",
        area=active_session.area,
        result=None,
        visitor_count=visitor_count,
    )


@kiosk_bp.route("/scan", methods=["POST"])
@login_required
def scan():
    """Process a Banner ID scan — auto sign-in or sign-out."""
    active_session = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).first()
    if not active_session:
        return redirect(url_for("monitor.dashboard"))

    area = active_session.area
    banner_id = request.form.get("banner_id", "").strip()

    if not banner_id:
        return render_template(
            "kiosk/index.html",
            area=area,
            result={"type": "error", "message": "Please enter a Banner ID."},
            visitor_count=_visitor_count(area.id),
        )

    if not is_valid_banner_id(banner_id):
        return render_template(
            "kiosk/index.html",
            area=area,
            result={"type": "error", "message": "Banner ID must be exactly 9 digits."},
            visitor_count=_visitor_count(area.id),
        )

    student = Student.query.filter_by(student_id=banner_id).first()
    if not student:
        return render_template(
            "kiosk/index.html",
            area=area,
            result={
                "type": "error",
                "message": f'ID "{banner_id}" not found. Please see the monitor.',
            },
            visitor_count=_visitor_count(area.id),
        )

    # Check for active visit — if exists, sign out; otherwise sign in
    active_visit = StudentVisit.query.filter_by(
        student_id=student.id, area_id=area.id, signed_out_at=None
    ).first()

    if active_visit:
        # Sign out
        active_visit.signed_out_at = datetime.now(timezone.utc)
        active_visit.signed_out_by_id = current_user.id
        db.session.commit()
        return render_template(
            "kiosk/index.html",
            area=area,
            result={
                "type": "out",
                "message": f"{student.display_name} signed out.",
                "student_name": student.display_name,
            },
            visitor_count=_visitor_count(area.id),
        )

    # Ban check
    if student.is_banned:
        return render_template(
            "kiosk/index.html",
            area=area,
            result={
                "type": "banned",
                "message": f"{student.display_name} is currently banned. Please see the monitor.",
                "student_name": student.display_name,
            },
            visitor_count=_visitor_count(area.id),
        )

    # Sign in
    visit = StudentVisit(
        student_id=student.id,
        area_id=area.id,
        acknowledged_by_id=current_user.id,
    )
    db.session.add(visit)
    db.session.commit()

    wcount = student.active_warnings_count
    return render_template(
        "kiosk/index.html",
        area=area,
        result={
            "type": "in",
            "message": f"{student.display_name} signed in.",
            "student_name": student.display_name,
            "warnings": wcount,
        },
        visitor_count=_visitor_count(area.id),
    )


def _visitor_count(area_id):
    return StudentVisit.query.filter_by(
        area_id=area_id, signed_out_at=None
    ).count()
