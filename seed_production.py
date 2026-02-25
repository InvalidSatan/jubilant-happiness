"""
Production seed script — initializes the database with real accounts and
equipment data. Does NOT create sample students or test monitors.

Usage:
    python seed_production.py

You will be prompted to set the primary faculty admin password.
"""

import getpass
import sys

from app import create_app, db
from app.models import Monitor, ShopArea, Equipment, Faculty


def main():
    app = create_app()

    with app.app_context():
        # Areas are auto-seeded by create_app, fetch them
        sculpture = ShopArea.query.filter_by(name="Sculpture").first()
        ceramics = ShopArea.query.filter_by(name="Ceramics").first()
        metal = ShopArea.query.filter_by(name="Metal Smithing").first()
        digilab = ShopArea.query.filter_by(name="DigiLab").first()
        woodworking = ShopArea.query.filter_by(name="Woodworking").first()

        if not all([sculpture, ceramics, metal, digilab, woodworking]):
            print("ERROR: Shop areas not found. Check create_app().")
            sys.exit(1)

        # --- Equipment / training certifications ---
        equipment_data = [
            # Sculpture
            ("Basic Woodshop", sculpture, True),
            ("Advanced Woodshop", sculpture, True),
            ("Welding", sculpture, True),
            ("Casting", sculpture, True),
            ("Carving", sculpture, True),
            ("CNC Plasma", sculpture, True),
            # Ceramics (placeholders until confirmed)
            ("Kiln", ceramics, True),
            ("Pottery Wheel", ceramics, True),
            ("Glaze Station", ceramics, False),
            # Metal Smithing
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
        created_equipment = 0
        for name, area, req_training in equipment_data:
            if not Equipment.query.filter_by(name=name, area_id=area.id).first():
                db.session.add(
                    Equipment(name=name, area_id=area.id, requires_training=req_training)
                )
                created_equipment += 1
        print(f"Equipment: {created_equipment} new certifications created.")

        # --- Primary faculty admin ---
        if not Faculty.query.filter_by(is_primary_admin=True).first():
            print("\n--- Create Primary Faculty Admin ---")
            username = input("Username (e.g. your AppState username): ").strip()
            display_name = input("Display name (e.g. Dr. Jane Smith): ").strip()
            email = input("Email (e.g. smithj@appstate.edu): ").strip()

            while True:
                password = getpass.getpass("Password: ")
                confirm = getpass.getpass("Confirm password: ")
                if password == confirm and len(password) >= 8:
                    break
                if password != confirm:
                    print("Passwords do not match. Try again.")
                else:
                    print("Password must be at least 8 characters. Try again.")

            fac = Faculty(
                username=username,
                display_name=display_name,
                email=email,
                is_primary_admin=True,
            )
            fac.set_password(password)
            db.session.add(fac)
            print(f"Created primary faculty admin: {username}")
        else:
            print("Primary faculty admin already exists — skipping.")

        # --- Admin monitor account ---
        if not Monitor.query.filter_by(is_admin=True).first():
            print("\n--- Create Admin Monitor ---")
            username = input("Admin monitor username: ").strip()
            display_name = input("Display name: ").strip()

            while True:
                password = getpass.getpass("Password: ")
                confirm = getpass.getpass("Confirm password: ")
                if password == confirm and len(password) >= 8:
                    break
                if password != confirm:
                    print("Passwords do not match. Try again.")
                else:
                    print("Password must be at least 8 characters. Try again.")

            admin = Monitor(
                username=username, display_name=display_name, is_admin=True
            )
            admin.set_password(password)
            admin.areas = [sculpture, ceramics, metal, digilab, woodworking]
            db.session.add(admin)
            print(f"Created admin monitor: {username}")
        else:
            print("Admin monitor already exists — skipping.")

        db.session.commit()
        print("\nProduction seed complete.")
        print("Start the server with: ./start.sh")
        print("Additional monitors and faculty can be created through the web UI.")


if __name__ == "__main__":
    main()
