"""Reporting routes — visit logs, monitor coverage, safety summaries with CSV export."""

import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    ShopArea,
    Student,
    StudentVisit,
    MonitorSession,
    Warning,
    Monitor,
)
from app.routes import bounce_faculty_to_dashboard
from app.utils import format_local

reports_bp = Blueprint("reports", __name__)
reports_bp.before_request(bounce_faculty_to_dashboard)


def admin_required(f):
    """Reusable admin guard (mirrors admin.py)."""
    from functools import wraps

    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            flash("Admin access required.", "danger")
            return redirect(url_for("monitor.dashboard"))
        return f(*args, **kwargs)

    return decorated


def _parse_dates(request):
    """Extract optional start/end dates from query string."""
    start_str = request.args.get("start", "").strip()
    end_str = request.args.get("end", "").strip()
    start = None
    end = None
    if start_str:
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if end_str:
        try:
            # End of the selected day
            end = datetime.strptime(end_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            pass
    return start, end


# ---------------------------------------------------------------------------
# Hub
# ---------------------------------------------------------------------------
@reports_bp.route("/")
@admin_required
def hub():
    return render_template("admin/reports/hub.html")


# ---------------------------------------------------------------------------
# Visit Log
# ---------------------------------------------------------------------------
@reports_bp.route("/visits")
@admin_required
def visits():
    areas = ShopArea.query.order_by(ShopArea.name).all()
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = StudentVisit.query.join(Student).join(ShopArea)
    if area_id:
        query = query.filter(StudentVisit.area_id == area_id)
    if start:
        query = query.filter(StudentVisit.signed_in_at >= start)
    if end:
        query = query.filter(StudentVisit.signed_in_at <= end)

    visits = query.order_by(StudentVisit.signed_in_at.desc()).limit(500).all()

    return render_template(
        "admin/reports/visits.html",
        visits=visits,
        areas=areas,
        selected_area=area_id,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
    )


@reports_bp.route("/visits/export")
@admin_required
def visits_export():
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = StudentVisit.query.join(Student).join(ShopArea)
    if area_id:
        query = query.filter(StudentVisit.area_id == area_id)
    if start:
        query = query.filter(StudentVisit.signed_in_at >= start)
    if end:
        query = query.filter(StudentVisit.signed_in_at <= end)

    visits = query.order_by(StudentVisit.signed_in_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Banner ID", "Area", "Signed In", "Signed Out",
                     "In By", "Out By", "Note"])
    for v in visits:
        writer.writerow([
            v.student.display_name,
            v.student.student_id,
            v.area.name,
            format_local(v.signed_in_at, "%Y-%m-%d %H:%M"),
            format_local(v.signed_out_at, "%Y-%m-%d %H:%M") if v.signed_out_at else "Active",
            v.acknowledged_by.display_name,
            v.signed_out_by.display_name if v.signed_out_by else "",
            v.note or "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=visit_log.csv"},
    )


# ---------------------------------------------------------------------------
# Monitor Coverage
# ---------------------------------------------------------------------------
@reports_bp.route("/coverage")
@admin_required
def coverage():
    areas = ShopArea.query.order_by(ShopArea.name).all()
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = MonitorSession.query.join(Monitor).join(ShopArea)
    if area_id:
        query = query.filter(MonitorSession.area_id == area_id)
    if start:
        query = query.filter(MonitorSession.signed_in_at >= start)
    if end:
        query = query.filter(MonitorSession.signed_in_at <= end)

    sessions = query.order_by(MonitorSession.signed_in_at.desc()).limit(500).all()

    # Summary: total hours per monitor
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor_hours = {}
    for s in sessions:
        end_time = s.signed_out_at or now_naive
        hours = (end_time - s.signed_in_at).total_seconds() / 3600
        name = s.monitor.display_name
        if name not in monitor_hours:
            monitor_hours[name] = 0.0
        monitor_hours[name] += hours
    # Sort by hours descending
    monitor_hours = dict(sorted(monitor_hours.items(), key=lambda x: x[1], reverse=True))

    return render_template(
        "admin/reports/coverage.html",
        sessions=sessions,
        areas=areas,
        selected_area=area_id,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        monitor_hours=monitor_hours,
    )


@reports_bp.route("/coverage/export")
@admin_required
def coverage_export():
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = MonitorSession.query.join(Monitor).join(ShopArea)
    if area_id:
        query = query.filter(MonitorSession.area_id == area_id)
    if start:
        query = query.filter(MonitorSession.signed_in_at >= start)
    if end:
        query = query.filter(MonitorSession.signed_in_at <= end)

    sessions = query.order_by(MonitorSession.signed_in_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    writer.writerow(["Monitor", "Area", "Signed In", "Signed Out", "Hours"])
    for s in sessions:
        end_time = s.signed_out_at or now_naive
        hours = (end_time - s.signed_in_at).total_seconds() / 3600
        writer.writerow([
            s.monitor.display_name,
            s.area.name,
            format_local(s.signed_in_at, "%Y-%m-%d %H:%M"),
            format_local(s.signed_out_at, "%Y-%m-%d %H:%M") if s.signed_out_at else "Active",
            f"{hours:.1f}",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=monitor_coverage.csv"},
    )


# ---------------------------------------------------------------------------
# Safety / Warnings
# ---------------------------------------------------------------------------
@reports_bp.route("/safety")
@admin_required
def safety():
    areas = ShopArea.query.order_by(ShopArea.name).all()
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = Warning.query.join(Student).join(ShopArea)
    if area_id:
        query = query.filter(Warning.area_id == area_id)
    if start:
        query = query.filter(Warning.created_at >= start)
    if end:
        query = query.filter(Warning.created_at <= end)

    warnings = query.order_by(Warning.created_at.desc()).limit(500).all()

    # Summary stats
    total = len(warnings)
    active = sum(1 for w in warnings if not w.resolved)
    resolved = total - active

    # Per-area breakdown
    area_counts = {}
    for w in warnings:
        name = w.area.name
        if name not in area_counts:
            area_counts[name] = {"active": 0, "resolved": 0}
        if w.resolved:
            area_counts[name]["resolved"] += 1
        else:
            area_counts[name]["active"] += 1

    # Currently banned students (3+ active warnings). Done as a single grouped
    # query rather than is_banned per student (which is one COUNT each — N+1).
    banned_students = (
        db.session.query(Student)
        .join(Warning, Warning.student_id == Student.id)
        .filter(Warning.resolved.is_(False))
        .group_by(Student.id)
        .having(func.count(Warning.id) >= 3)
        .order_by(Student.display_name)
        .all()
    )

    return render_template(
        "admin/reports/safety.html",
        warnings=warnings,
        areas=areas,
        selected_area=area_id,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        total=total,
        active=active,
        resolved=resolved,
        area_counts=area_counts,
        banned_students=banned_students,
    )


@reports_bp.route("/safety/export")
@admin_required
def safety_export():
    area_id = request.args.get("area_id", type=int)
    start, end = _parse_dates(request)

    query = Warning.query.join(Student).join(ShopArea)
    if area_id:
        query = query.filter(Warning.area_id == area_id)
    if start:
        query = query.filter(Warning.created_at >= start)
    if end:
        query = query.filter(Warning.created_at <= end)

    warnings = query.order_by(Warning.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Banner ID", "Area", "Reason", "Issued By",
                     "Date", "Status", "Resolved By", "Resolved Date"])
    for w in warnings:
        writer.writerow([
            w.student.display_name,
            w.student.student_id,
            w.area.name,
            w.reason,
            w.issued_by.display_name,
            format_local(w.created_at, "%Y-%m-%d %H:%M"),
            "Resolved" if w.resolved else "Active",
            w.resolved_by.display_name if w.resolved_by else "",
            format_local(w.resolved_at, "%Y-%m-%d %H:%M") if w.resolved_at else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=safety_report.csv"},
    )
