"""Shared helpers for route blueprints."""

from urllib.parse import urljoin, urlparse

from flask import redirect, request, url_for
from flask_login import current_user


def is_safe_redirect_url(target: str) -> bool:
    """Return True only when ``target`` points back at this same host.

    Used to sanitize the ``?next=`` login parameter so it can't be abused as an
    open redirect to an attacker-controlled site.
    """
    if not target:
        return False
    host_url = request.host_url
    test = urlparse(urljoin(host_url, target))
    return test.scheme in ("http", "https") and urlparse(host_url).netloc == test.netloc


def get_live_shop_state():
    """Return per-area live occupancy: monitors on duty and students signed in.

    Shared by the admin and faculty "who's in the shop right now" views.
    """
    from app.models import ShopArea, MonitorSession, StudentVisit

    areas = ShopArea.query.order_by(ShopArea.name).all()
    state = {a.id: {"area": a, "monitors": [], "visits": []} for a in areas}

    for s in MonitorSession.query.filter_by(signed_out_at=None).all():
        if s.area_id in state:
            state[s.area_id]["monitors"].append(s)

    for v in (
        StudentVisit.query.filter_by(signed_out_at=None)
        .order_by(StudentVisit.signed_in_at)
        .all()
    ):
        if v.area_id in state:
            state[v.area_id]["visits"].append(v)

    return [state[a.id] for a in areas]


def bounce_faculty_to_dashboard():
    """Blueprint ``before_request`` guard for the monitor-facing blueprints.

    Faculty accounts are a different user model with no ``areas``/``is_admin``
    attributes, so letting them reach monitor/admin views renders the wrong
    dashboard or raises ``AttributeError`` (HTTP 500). Authenticated faculty are
    redirected to their own dashboard; anonymous users fall through to the
    view's ``@login_required`` handling.
    """
    if current_user.is_authenticated and getattr(
        current_user, "user_type", None
    ) == "faculty":
        return redirect(url_for("faculty.dashboard"))
