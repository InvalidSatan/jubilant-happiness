"""
Demo data seeder — layers realistic history on top of seed.py.

Run this before a walkthrough/demo so the dashboards and reports show real
looking data instead of empty tables. It is additive and idempotent-ish:
it skips work if the demo students already exist.

Usage:
    flask db upgrade
    python seed.py
    python seed_demo.py

Do NOT run this against a production database.
"""

import random
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import (
    Equipment,
    Monitor,
    MonitorSession,
    ShopArea,
    Student,
    StudentVisit,
    Warning,
)

CURRENT_SEMESTER = "Spring 2026"
PRIOR_SEMESTER = "Fall 2025"

# (banner_id, name, email) — layered on top of the three from seed.py
DEMO_STUDENTS = [
    ("900444444", "Riley Adams", "radams@appstate.edu"),
    ("900555555", "Morgan Patel", "mpatel@appstate.edu"),
    ("900666666", "Sam Okafor", "sokafor@appstate.edu"),
    ("900777777", "Devon Brooks", "dbrooks@appstate.edu"),
    ("900888888", "Avery Nguyen", "anguyen@appstate.edu"),
]

# banner_id -> [(area name, equipment name, semester), ...]
TRAINING = {
    "900111111": [
        ("Sculpture", "Basic Woodshop", PRIOR_SEMESTER),
        ("Sculpture", "Advanced Woodshop", CURRENT_SEMESTER),
        ("Sculpture", "Welding", CURRENT_SEMESTER),
    ],
    "900222222": [
        ("Sculpture", "Basic Woodshop", CURRENT_SEMESTER),
        ("DigiLab", "Laser", CURRENT_SEMESTER),
        ("DigiLab", "3D Printing", CURRENT_SEMESTER),
    ],
    "900333333": [
        ("Woodworking", "WW1", PRIOR_SEMESTER),
        ("Woodworking", "WW2", CURRENT_SEMESTER),
    ],
    "900444444": [
        ("Metal Smithing", "Torches (Annealing/Soldering Bench)", CURRENT_SEMESTER),
        ("Metal Smithing", "Casting Room", CURRENT_SEMESTER),
    ],
    "900555555": [
        ("DigiLab", "Laser", PRIOR_SEMESTER),
        ("DigiLab", "Shopbot", CURRENT_SEMESTER),
        ("DigiLab", "Vinyl Cutter", CURRENT_SEMESTER),
    ],
    "900666666": [
        ("Ceramics", "Kiln", CURRENT_SEMESTER),
        ("Ceramics", "Pottery Wheel", CURRENT_SEMESTER),
    ],
    # 900777777 (Devon Brooks) deliberately has NO training records and three
    # active warnings, so he demonstrates the hard ban. Note that a banned
    # student never reaches the certification table — to demo the "No Record"
    # badge use an unbanned student with no records in the area being entered,
    # e.g. Riley Adams (900444444) signing in to Sculpture.
    "900888888": [
        ("Sculpture", "Basic Woodshop", PRIOR_SEMESTER),
    ],
}

CARE_NOTES = {
    "900333333": "Hearing impaired — get their attention visually before starting loud equipment.",
    "900555555": "Recovering from a wrist injury. Cleared by health services, but check in.",
}

VISIT_NOTES = [
    "Cutting stock for final project",
    "Sanding and finishing",
    "Glue-up, no power tools",
    "Laser cutting acrylic templates",
    "Welding practice pieces",
    "Wheel throwing",
    "Cleaning up shared bench space",
    None,
    None,
]

# (banner_id, area, reason, resolved)
WARNINGS = [
    ("900777777", "Sculpture", "Operating the band saw without a completed WW1 certification.", False),
    ("900777777", "Sculpture", "Left the shop without cleaning the workstation after repeated reminders.", False),
    ("900777777", "Woodworking", "No safety glasses at the miter saw after a verbal correction.", False),
    ("900888888", "Sculpture", "Ran the dust collector improperly; left it off during routing.", False),
    ("900222222", "DigiLab", "Left the laser cutter running unattended.", True),
]


def main():
    app = create_app()
    with app.app_context():
        if Student.query.filter_by(student_id="900444444").first():
            print("Demo data already present — nothing to do.")
            return

        areas = {a.name: a for a in ShopArea.query.all()}
        monitors = {m.username: m for m in Monitor.query.all()}
        if not areas or "admin" not in monitors:
            print("Base data missing. Run `flask db upgrade && python seed.py` first.")
            return

        # --- Students ---
        for sid, name, email in DEMO_STUDENTS:
            if not Student.query.filter_by(student_id=sid).first():
                db.session.add(
                    Student(
                        student_id=sid,
                        display_name=name,
                        email=email,
                        enrollment_term=CURRENT_SEMESTER,
                    )
                )
        db.session.commit()

        students = {s.student_id: s for s in Student.query.all()}
        for s in students.values():
            if not s.enrollment_term:
                s.enrollment_term = CURRENT_SEMESTER

        # --- Care notes ---
        for sid, note in CARE_NOTES.items():
            if sid in students:
                students[sid].care_note = note

        # --- Training certifications ---
        granted = 0
        for sid, records in TRAINING.items():
            student = students.get(sid)
            if not student:
                continue
            for area_name, equip_name, semester in records:
                area = areas.get(area_name)
                if not area:
                    continue
                equip = Equipment.query.filter_by(
                    name=equip_name, area_id=area.id
                ).first()
                if not equip or equip in student.trained_equipment:
                    continue
                db.session.execute(
                    db.text(
                        "INSERT INTO student_training "
                        "(student_id, equipment_id, certified_date, certified_semester, source) "
                        "VALUES (:sid, :eid, :cdate, :sem, 'manual')"
                    ),
                    {
                        "sid": student.id,
                        "eid": equip.id,
                        "cdate": datetime.now(timezone.utc) - timedelta(days=60),
                        "sem": semester,
                    },
                )
                granted += 1
        db.session.commit()

        # --- Three weeks of monitor shifts and student visits ---
        rng = random.Random(20260810)
        shift_monitors = [
            ("mgarcia", "Sculpture"),
            ("mgarcia", "Ceramics"),
            ("jchen", "Metal Smithing"),
            ("asmith", "DigiLab"),
            ("bwilson", "Woodworking"),
        ]
        now = datetime.now(timezone.utc)
        sessions_made = 0
        visits_made = 0

        for days_ago in range(21, 0, -1):
            day = now - timedelta(days=days_ago)
            if day.weekday() >= 5:  # skip weekends
                continue
            for username, area_name in shift_monitors:
                if rng.random() < 0.45:
                    continue
                monitor = monitors.get(username)
                area = areas.get(area_name)
                if not monitor or not area:
                    continue

                start = day.replace(hour=rng.choice([10, 13, 17]), minute=0, second=0, microsecond=0)
                end = start + timedelta(hours=rng.choice([3, 4, 4, 5]))
                session = MonitorSession(
                    monitor_id=monitor.id,
                    area_id=area.id,
                    signed_in_at=start,
                    signed_out_at=end,
                )
                db.session.add(session)
                sessions_made += 1

                for _ in range(rng.randint(0, 4)):
                    student = rng.choice(list(students.values()))
                    v_start = start + timedelta(minutes=rng.randint(5, 120))
                    v_end = v_start + timedelta(minutes=rng.randint(30, 150))
                    if v_end > end:
                        v_end = end
                    db.session.add(
                        StudentVisit(
                            student_id=student.id,
                            area_id=area.id,
                            acknowledged_by_id=monitor.id,
                            signed_out_by_id=monitor.id,
                            signed_in_at=v_start,
                            signed_out_at=v_end,
                            note=rng.choice(VISIT_NOTES),
                        )
                    )
                    visits_made += 1
        db.session.commit()

        # --- Warnings (Devon Brooks ends up at 3 active = banned) ---
        warnings_made = 0
        admin = monitors["admin"]
        for sid, area_name, reason, resolved in WARNINGS:
            student = students.get(sid)
            area = areas.get(area_name)
            if not student or not area:
                continue
            issuer = monitors.get("mgarcia", admin)
            w = Warning(
                student_id=student.id,
                area_id=area.id,
                issued_by_id=issuer.id,
                reason=reason,
                created_at=now - timedelta(days=rng.randint(2, 18)),
                resolved=resolved,
            )
            if resolved:
                w.resolved_by_id = admin.id
                w.resolved_at = now - timedelta(days=1)
            db.session.add(w)
            warnings_made += 1
        db.session.commit()

        banned = [s.display_name for s in Student.query.all() if s.is_banned]
        print(f"Students added:        {len(DEMO_STUDENTS)}")
        print(f"Training records:      {granted}")
        print(f"Monitor shifts:        {sessions_made}")
        print(f"Student visits:        {visits_made}")
        print(f"Warnings:              {warnings_made}")
        print(f"Currently banned:      {', '.join(banned) if banned else 'none'}")
        print("\nDemo data ready.")


if __name__ == "__main__":
    main()
