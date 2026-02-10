"""
Seed script to populate the database with sample data for development/testing.

Usage:
    python seed.py
"""

from app import create_app, db
from app.models import Monitor, ShopArea, Equipment, Student

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

    # --- Create sample equipment ---
    equipment_data = [
        ("Band Saw", sculpture, True),
        ("Table Saw", sculpture, True),
        ("Wood Lathe", sculpture, True),
        ("Hand Tools", sculpture, False),
        ("Kiln", ceramics, True),
        ("Pottery Wheel", ceramics, True),
        ("Glaze Station", ceramics, False),
        ("MIG Welder", metal, True),
        ("TIG Welder", metal, True),
        ("Plasma Cutter", metal, True),
        ("Anvil & Forge", metal, True),
        ("3D Printer", digilab, True),
        ("Laser Cutter", digilab, True),
        ("CNC Router", digilab, True),
        ("Vinyl Cutter", digilab, False),
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
