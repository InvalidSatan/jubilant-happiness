"""
Seed script to populate the database with sample data for development/testing.

Usage:
    python seed.py
"""

from app import create_app, db
from app.models import Monitor, ShopArea, Equipment, Student, Faculty

app = create_app()

with app.app_context():
    # Areas are auto-seeded by create_app, fetch them
    sculpture = ShopArea.query.filter_by(name="Sculpture").first()
    ceramics = ShopArea.query.filter_by(name="Ceramics").first()
    metal = ShopArea.query.filter_by(name="Metal Smithing").first()
    digilab = ShopArea.query.filter_by(name="DigiLab").first()
    woodworking = ShopArea.query.filter_by(name="Woodworking").first()

    # --- Create an admin monitor ---
    if not Monitor.query.filter_by(username="admin").first():
        admin = Monitor(
            username="admin", display_name="Shop Admin", is_admin=True
        )
        admin.set_password("admin")
        admin.areas = [sculpture, ceramics, metal, digilab, woodworking]
        db.session.add(admin)
        print("Created admin monitor (username: admin, password: admin)")

    # --- Create sample monitors ---
    monitors_data = [
        ("mgarcia", "Maria Garcia", [sculpture, ceramics]),
        ("jchen", "James Chen", [metal]),
        ("asmith", "Alex Smith", [digilab]),
        ("bwilson", "Blake Wilson", [woodworking]),
    ]
    for uname, dname, areas in monitors_data:
        if not Monitor.query.filter_by(username=uname).first():
            m = Monitor(username=uname, display_name=dname)
            m.set_password("password")
            m.areas = areas
            db.session.add(m)
            print(f"Created monitor: {uname} (password: password)")

    # --- Create equipment / training certifications ---
    # These match the actual certification categories used in the shop spreadsheets.
    # Ceramics certifications are placeholders until details are confirmed.
    equipment_data = [
        # Sculpture
        ("Basic Woodshop", sculpture, True),
        ("Advanced Woodshop", sculpture, True),
        ("Welding", sculpture, True),
        ("Casting", sculpture, True),
        ("Carving", sculpture, True),
        ("CNC Plasma", sculpture, True),
        # Ceramics (TBD — placeholders)
        ("Kiln", ceramics, True),
        ("Pottery Wheel", ceramics, True),
        ("Glaze Station", ceramics, False),
        # Metals
        ("Torches (Annealing/Soldering Bench)", metal, True),
        ("Machine Room (Buffer/Grinder)", metal, True),
        ("Casting Room", metal, True),
        ("CNC Milling Machine", metal, True),
        ("Annodizing", metal, True),
        # DigiLab
        ("Laser", digilab, True),
        ("3D Printing", digilab, True),
        ("Resin Printing", digilab, True),
        ("Shopbot", digilab, True),
        ("Vinyl Cutter", digilab, True),
        # Woodworking
        ("WW1", woodworking, True),
        ("WW2", woodworking, True),
        ("Welding", woodworking, True),
        ("Casting", woodworking, True),
        ("Carving", woodworking, True),
    ]
    for name, area, req_training in equipment_data:
        if not Equipment.query.filter_by(name=name, area_id=area.id).first():
            db.session.add(
                Equipment(name=name, area_id=area.id, requires_training=req_training)
            )

    # --- Create faculty accounts ---
    if not Faculty.query.filter_by(username="faculty").first():
        fac = Faculty(
            username="faculty",
            display_name="Dr. Faculty Admin",
            email="faculty@appstate.edu",
            is_primary_admin=True,
        )
        fac.set_password("faculty")
        db.session.add(fac)
        print("Created primary faculty admin (username: faculty, password: faculty)")

    if not Faculty.query.filter_by(username="instructor").first():
        fac2 = Faculty(
            username="instructor",
            display_name="Prof. Instructor",
            email="instructor@appstate.edu",
            is_primary_admin=False,
        )
        fac2.set_password("password")
        db.session.add(fac2)
        print("Created faculty member (username: instructor, password: password)")

    # --- Create sample students ---
    students_data = [
        ("900111111", "Taylor Johnson", "tjohnson@appstate.edu"),
        ("900222222", "Jordan Lee", "jlee@appstate.edu"),
        ("900333333", "Casey Rivera", "crivera@appstate.edu"),
    ]
    for sid, name, email in students_data:
        if not Student.query.filter_by(student_id=sid).first():
            db.session.add(Student(student_id=sid, display_name=name, email=email))
            print(f"Created student: {name} ({sid})")

    db.session.commit()
    print("\nSeed complete. Run with: flask run  (or python run.py)")
