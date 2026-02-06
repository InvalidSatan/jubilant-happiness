"""
Integration stubs for Banner SIS and ASULearn (Moodle).

These provide the plumbing so that when API credentials are configured,
the system can pull training/certification data automatically.
"""

import logging

import requests
from flask import Blueprint, current_app, flash, redirect, url_for, request
from flask_login import login_required

from app import db
from app.models import Student, Equipment

integration_bp = Blueprint("integration", __name__)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Banner SIS Integration
# ---------------------------------------------------------------------------
def fetch_banner_completions(student_banner_id: str) -> list[dict]:
    """
    Query Banner for course completions relevant to shop training.

    Expected to return a list of dicts like:
        [{"course_code": "ART 2210", "completed": True, "term": "202510"}, ...]

    This is a STUB.  Replace the implementation once Banner API access is
    provisioned and the endpoint / schema are finalized.
    """
    api_url = current_app.config.get("BANNER_API_URL")
    api_key = current_app.config.get("BANNER_API_KEY")

    if not api_url or not api_key:
        log.warning("Banner integration not configured; skipping.")
        return []

    try:
        resp = requests.get(
            f"{api_url}/students/{student_banner_id}/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.error("Banner API request failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# ASULearn / Moodle Integration
# ---------------------------------------------------------------------------
def fetch_asulearn_completions(student_email: str) -> list[dict]:
    """
    Query ASULearn (Moodle) for relevant course/module completions.

    Expected to return a list of dicts like:
        [{"course_name": "Shop Safety 101", "completed": True}, ...]

    This is a STUB.  Replace once the Moodle Web Services token and
    function names are confirmed with IT.
    """
    api_url = current_app.config.get("ASULEARN_API_URL")
    token = current_app.config.get("ASULEARN_API_TOKEN")

    if not api_url or not token:
        log.warning("ASULearn integration not configured; skipping.")
        return []

    try:
        resp = requests.get(
            api_url,
            params={
                "wstoken": token,
                "wsfunction": "core_completion_get_activities_completion_status",
                "moodlewsrestformat": "json",
                "username": student_email,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("statuses", [])
    except requests.RequestException as exc:
        log.error("ASULearn API request failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Manual sync endpoint (admin-triggered)
# ---------------------------------------------------------------------------
# Mapping from external course identifiers to equipment names.
# Customize this as the department finalizes which courses map to which
# pieces of equipment.
COURSE_EQUIPMENT_MAP: dict[str, str] = {
    # "ART 2210": "MIG Welder",
    # "ART 2220": "Kiln",
    # "SHOP_SAFETY_101": "All General Equipment",
}


@integration_bp.route("/sync-student/<int:student_id>", methods=["POST"])
@login_required
def sync_student(student_id):
    """
    Pull the latest training data from Banner and ASULearn for one student
    and update their local certifications.
    """
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("monitor.dashboard"))

    added = []

    # --- Banner ---
    banner_data = fetch_banner_completions(student.student_id)
    for record in banner_data:
        code = record.get("course_code", "")
        if record.get("completed") and code in COURSE_EQUIPMENT_MAP:
            eq_name = COURSE_EQUIPMENT_MAP[code]
            eq = Equipment.query.filter_by(name=eq_name).first()
            if eq and eq not in student.trained_equipment:
                student.trained_equipment.append(eq)
                added.append(eq_name)

    # --- ASULearn ---
    if student.email:
        asulearn_data = fetch_asulearn_completions(student.email)
        for record in asulearn_data:
            cname = record.get("course_name", "")
            if record.get("completed") and cname in COURSE_EQUIPMENT_MAP:
                eq_name = COURSE_EQUIPMENT_MAP[cname]
                eq = Equipment.query.filter_by(name=eq_name).first()
                if eq and eq not in student.trained_equipment:
                    student.trained_equipment.append(eq)
                    added.append(eq_name)

    db.session.commit()

    if added:
        flash(f"Synced training: {', '.join(added)}", "success")
    else:
        flash(
            "No new training data found (or integrations not yet configured).", "info"
        )

    return redirect(
        request.referrer or url_for("monitor.student_detail", student_id=student.id)
    )
