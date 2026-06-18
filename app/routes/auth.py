from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import Monitor
from app.routes import is_safe_redirect_url

auth_bp = Blueprint("auth", __name__)


def _home_for(user):
    """Return the correct landing page for an authenticated user."""
    if getattr(user, "user_type", None) == "faculty":
        return url_for("faculty.dashboard")
    return url_for("monitor.dashboard")


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        monitor = Monitor.query.filter_by(username=username).first()
        if monitor and monitor.check_password(password):
            login_user(monitor)
            next_page = request.args.get("next")
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for("monitor.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    # Auto sign-out of any active monitor sessions
    from app.models import MonitorSession
    from datetime import datetime, timezone

    active = MonitorSession.query.filter_by(
        monitor_id=current_user.id, signed_out_at=None
    ).all()
    for session in active:
        session.signed_out_at = datetime.now(timezone.utc)
    db.session.commit()

    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
