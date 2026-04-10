from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


# ---------------------------------------------------------------------------
# Association table: which areas a monitor is authorized to oversee
# ---------------------------------------------------------------------------
monitor_areas = db.Table(
    "monitor_areas",
    db.Column("monitor_id", db.Integer, db.ForeignKey("monitor.id"), primary_key=True),
    db.Column("area_id", db.Integer, db.ForeignKey("shop_area.id"), primary_key=True),
)

# ---------------------------------------------------------------------------
# Association table: which equipment a student is trained on
# ---------------------------------------------------------------------------
student_training = db.Table(
    "student_training",
    db.Column("student_id", db.Integer, db.ForeignKey("student.id"), primary_key=True),
    db.Column(
        "equipment_id", db.Integer, db.ForeignKey("equipment.id"), primary_key=True
    ),
    db.Column("certified_date", db.DateTime, default=lambda: datetime.now(timezone.utc)),
    db.Column("certified_semester", db.String(32), nullable=True),  # e.g. "Fall 2024"
    db.Column("source", db.String(50), default="manual"),  # manual | banner | asulearn
)


class ShopArea(db.Model):
    """One of the four main shop areas (Sculpture, Ceramics, etc.)."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    equipment = db.relationship("Equipment", backref="area", lazy="dynamic")

    def __repr__(self):
        return f"<ShopArea {self.name}>"


class Equipment(db.Model):
    """A specific piece of equipment within a shop area."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("shop_area.id"), nullable=False)
    requires_training = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Equipment {self.name}>"


class Monitor(UserMixin, db.Model):
    """A student employee who oversees a shop area."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    # Areas this monitor is authorized to oversee
    areas = db.relationship(
        "ShopArea", secondary=monitor_areas, backref="monitors", lazy="select"
    )

    @property
    def user_type(self):
        return "monitor"

    def get_id(self):
        return f"monitor:{self.id}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Monitor {self.username}>"


class Faculty(UserMixin, db.Model):
    """A faculty member who manages students and training certifications."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_primary_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def user_type(self):
        return "faculty"

    def get_id(self):
        return f"faculty:{self.id}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Faculty {self.username}>"


class Student(db.Model):
    """A student who uses the shop."""

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(32), unique=True, nullable=False)  # Banner ID
    display_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=True)

    # Current enrollment term, e.g. "Fall 2026". Populated by the Banner sync
    # job; used to decide whether a student is currently enrolled before
    # honoring cached training records.
    enrollment_term = db.Column(db.String(32), nullable=True)

    # Canvas LMS user id (numeric string). Populated by Canvas sync; used to
    # correlate Canvas course enrollments back to local students.
    canvas_user_id = db.Column(db.String(32), nullable=True, index=True)

    # Private note only monitors see
    care_note = db.Column(db.Text, nullable=True)

    # Training / certifications
    trained_equipment = db.relationship(
        "Equipment", secondary=student_training, backref="trained_students", lazy="select"
    )

    @property
    def active_warnings_count(self):
        return Warning.query.filter_by(student_id=self.id, resolved=False).count()

    @property
    def is_banned(self):
        return self.active_warnings_count >= 3

    def __repr__(self):
        return f"<Student {self.student_id}>"


class Warning(db.Model):
    """A warning / strike issued to a student. 3 active = banned."""

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("shop_area.id"), nullable=False)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("monitor.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved = db.Column(db.Boolean, default=False)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("monitor.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", backref="warnings")
    area = db.relationship("ShopArea")
    issued_by = db.relationship("Monitor", foreign_keys=[issued_by_id])
    resolved_by = db.relationship("Monitor", foreign_keys=[resolved_by_id])

    def __repr__(self):
        return f"<Warning student={self.student_id} area={self.area_id}>"


class MonitorSession(db.Model):
    """Tracks when a monitor is on duty in a specific area."""

    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey("monitor.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("shop_area.id"), nullable=False)
    signed_in_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    signed_out_at = db.Column(db.DateTime, nullable=True)

    monitor = db.relationship("Monitor", backref="sessions")
    area = db.relationship("ShopArea")

    @property
    def is_active(self):
        return self.signed_out_at is None

    def __repr__(self):
        return f"<MonitorSession monitor={self.monitor_id} area={self.area_id}>"


class StudentVisit(db.Model):
    """Tracks a student's sign-in/out for a shop area, acknowledged by a monitor."""

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("shop_area.id"), nullable=False)
    acknowledged_by_id = db.Column(
        db.Integer, db.ForeignKey("monitor.id"), nullable=False
    )
    signed_in_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    signed_out_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text, nullable=True)  # per-visit monitor note
    signed_out_by_id = db.Column(
        db.Integer, db.ForeignKey("monitor.id"), nullable=True
    )

    student = db.relationship("Student", backref="visits")
    area = db.relationship("ShopArea")
    acknowledged_by = db.relationship("Monitor", foreign_keys=[acknowledged_by_id])
    signed_out_by = db.relationship("Monitor", foreign_keys=[signed_out_by_id])

    @property
    def is_active(self):
        return self.signed_out_at is None

    def __repr__(self):
        return f"<StudentVisit student={self.student_id} area={self.area_id}>"
