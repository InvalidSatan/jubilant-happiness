"""
Integration stubs for Banner SIS, ASULearn (Moodle), and Canvas LMS.

These provide the plumbing so that when API credentials are configured,
the system can pull training/certification data automatically.
"""

import json
import logging

import requests
from flask import Blueprint, current_app, flash, redirect, url_for, request
from flask_login import login_required

from app import db
from app.models import Student, Equipment, student_training
from app.routes import bounce_faculty_to_dashboard

integration_bp = Blueprint("integration", __name__)
integration_bp.before_request(bounce_faculty_to_dashboard)
log = logging.getLogger(__name__)


def integration_status() -> dict[str, bool]:
    """Return whether each external integration has the credentials it needs.

    Used by the admin dashboard so staff can confirm at a glance that, e.g.,
    Canvas is wired up before relying on the sync.
    """
    cfg = current_app.config
    return {
        "Banner SIS": bool(cfg.get("BANNER_API_URL") and cfg.get("BANNER_API_KEY")),
        "ASULearn (Moodle)": bool(
            cfg.get("ASULEARN_API_URL") and cfg.get("ASULEARN_API_TOKEN")
        ),
        "Canvas LMS": bool(cfg.get("CANVAS_API_URL") and cfg.get("CANVAS_API_TOKEN")),
    }


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
# Canvas LMS Integration
# ---------------------------------------------------------------------------
def _next_link(link_header: str) -> str | None:
    """Extract the rel="next" URL from a Canvas ``Link`` response header."""
    for part in link_header.split(","):
        segments = [s.strip() for s in part.split(";")]
        if len(segments) < 2:
            continue
        url_part = segments[0].strip("<>")
        if 'rel="next"' in segments[1:]:
            return url_part
    return None


def _canvas_get_paginated(url, headers, params, timeout=10) -> list:
    """GET a Canvas collection, following ``Link: rel="next"`` pagination.

    Canvas caps ``per_page`` (typically at 100) and exposes further pages via
    the Link header, so a single request can silently drop results.
    """
    results: list = []
    next_url, next_params = url, params
    while next_url:
        resp = requests.get(
            next_url, headers=headers, params=next_params, timeout=timeout
        )
        resp.raise_for_status()
        page = resp.json()
        if isinstance(page, list):
            results.extend(page)
        # Follow-up pages are fully-qualified URLs in the Link header; the
        # original query params are already baked in, so don't resend them.
        next_url = _next_link(resp.headers.get("Link", ""))
        next_params = None
    return results


def fetch_canvas_enrollments(canvas_user_id: str) -> list[dict]:
    """
    Query Canvas for the (active) courses a user is enrolled in.

    Returns a list of dicts shaped like the Canvas API
    `/users/:user_id/courses` response, minimally:
        [{"id": 12345, "course_code": "ART 2210", "sis_course_id": "...",
          "name": "Sculpture I"}, ...]
    """
    api_url = current_app.config.get("CANVAS_API_URL")
    token = current_app.config.get("CANVAS_API_TOKEN")

    if not api_url or not token:
        log.warning("Canvas integration not configured; skipping.")
        return []

    if not canvas_user_id:
        return []

    try:
        return _canvas_get_paginated(
            f"{api_url}/users/{canvas_user_id}/courses",
            headers={"Authorization": f"Bearer {token}"},
            params={"enrollment_state": "active", "per_page": 100},
        )
    except requests.RequestException as exc:
        log.error("Canvas API request failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Course → equipment mapping
# ---------------------------------------------------------------------------
# Default mapping from external course identifiers to equipment names. Edit
# here, or (preferably) supply COURSE_EQUIPMENT_MAP_JSON in the environment to
# override/extend without code changes. The same map is consulted for Banner
# course codes, ASULearn course names, and Canvas course_code / sis_course_id.
COURSE_EQUIPMENT_MAP: dict[str, str] = {
    # "ART 2210": "MIG Welder",
    # "ART 2220": "Kiln",
    # "SHOP_SAFETY_101": "Basic Woodshop",
}


def get_course_equipment_map() -> dict[str, str]:
    """Return the effective course→equipment map (defaults + env override)."""
    mapping = dict(COURSE_EQUIPMENT_MAP)
    raw = current_app.config.get("COURSE_EQUIPMENT_MAP_JSON")
    if raw:
        try:
            overrides = json.loads(raw)
            if isinstance(overrides, dict):
                mapping.update({str(k): str(v) for k, v in overrides.items()})
            else:
                log.error("COURSE_EQUIPMENT_MAP_JSON must be a JSON object; ignoring.")
        except (ValueError, TypeError):
            log.error("COURSE_EQUIPMENT_MAP_JSON is not valid JSON; ignoring.")
    return mapping


def sync_student_training(student: Student) -> list[str]:
    """Pull external completions for one student and grant matching training.

    Returns the list of newly granted equipment names. Records are tagged with
    the originating source ("banner"/"asulearn"/"canvas") rather than "manual",
    and the caller is responsible for committing the session.
    """
    course_map = get_course_equipment_map()
    if not course_map:
        return []

    # Track equipment the student already has (by id) so repeated matches across
    # sources/courses don't create duplicate rows or rely on a stale relationship.
    existing_ids = {eq.id for eq in student.trained_equipment}
    added: list[str] = []

    def grant(eq_name: str, source: str, semester: str | None = None):
        eq = Equipment.query.filter_by(name=eq_name).first()
        if not eq or eq.id in existing_ids:
            return
        db.session.execute(
            student_training.insert().values(
                student_id=student.id,
                equipment_id=eq.id,
                certified_semester=semester,
                source=source,
            )
        )
        existing_ids.add(eq.id)
        added.append(eq_name)

    # --- Banner ---
    for record in fetch_banner_completions(student.student_id):
        code = record.get("course_code", "")
        if record.get("completed") and code in course_map:
            grant(course_map[code], "banner", record.get("term"))

    # --- ASULearn ---
    if student.email:
        for record in fetch_asulearn_completions(student.email):
            cname = record.get("course_name", "")
            if record.get("completed") and cname in course_map:
                grant(course_map[cname], "asulearn")

    # --- Canvas ---
    if student.canvas_user_id:
        for record in fetch_canvas_enrollments(student.canvas_user_id):
            # The department may key the map by either the human course code or
            # the SIS id; accept whichever matches first.
            for key in (record.get("course_code"), record.get("sis_course_id")):
                if key and key in course_map:
                    grant(course_map[key], "canvas")
                    break

    return added


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------
@integration_bp.route("/sync-student/<int:student_id>", methods=["POST"])
@login_required
def sync_student(student_id):
    """Pull the latest training data from Banner/ASULearn/Canvas for one student."""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("monitor.dashboard"))

    added = sync_student_training(student)
    db.session.commit()

    if added:
        flash(f"Synced training: {', '.join(added)}", "success")
    elif not get_course_equipment_map():
        flash(
            "No course→equipment mapping configured yet "
            "(set COURSE_EQUIPMENT_MAP_JSON).",
            "info",
        )
    else:
        flash(
            "No new training data found (or integrations not yet configured).", "info"
        )

    return redirect(
        request.referrer or url_for("monitor.student_detail", student_id=student.id)
    )


@integration_bp.route("/sync-all", methods=["POST"])
@login_required
def sync_all():
    """Sync every student that has an external identifier (Canvas id or email).

    Run this after linking a Canvas class so the whole roster's certifications
    are pulled in one pass.
    """
    students = (
        Student.query.filter(
            db.or_(
                Student.canvas_user_id.isnot(None),
                Student.email.isnot(None),
            )
        )
        .order_by(Student.display_name)
        .all()
    )

    students_updated = 0
    total_added = 0
    for student in students:
        added = sync_student_training(student)
        if added:
            students_updated += 1
            total_added += len(added)

    db.session.commit()

    if total_added:
        flash(
            f"Sync complete: {total_added} new certification(s) across "
            f"{students_updated} student(s).",
            "success",
        )
    elif not get_course_equipment_map():
        flash(
            "No course→equipment mapping configured yet "
            "(set COURSE_EQUIPMENT_MAP_JSON).",
            "info",
        )
    else:
        flash(
            "Sync complete: no new training data found "
            "(or integrations not yet configured).",
            "info",
        )

    return redirect(request.referrer or url_for("admin.index"))
