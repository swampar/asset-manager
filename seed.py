"""Optional demo data: python seed.py"""
from app import connect, init_db

init_db()
c = connect()
if c.execute("SELECT 1 FROM staff").fetchone():
    print("Data already present - nothing added.")
else:
    c.executemany("INSERT INTO staff (name, email, department) VALUES (?,?,?)", [
        ("Anita Rao", "anita@school.example", "Administration"),
        ("Ravi Kumar", "ravi@school.example", "Mathematics"),
        ("Sneha Reddy", "sneha@school.example", "Science")])
    c.executemany("INSERT INTO assets (name, type, asset_tag, serial_number, status) VALUES (?,?,?,?,?)", [
        ("Dell Latitude 5420", "laptop", "HGS-0001", "DL5420-A1", "assigned"),
        ("HP Laptop 15", "laptop", "HGS-0002", "HP15-B2", "available"),
        ("Dell 24 Monitor", "monitor", "HGS-0003", "DM24-C3", "assigned"),
        ("Samsung Galaxy A54", "phone", "HGS-0004", "SGA54-D4", "available"),
        ("Epson Projector", "other", "HGS-0005", "EP-E5", "under repair")])
    # asset 1: assigned, returned, assigned again (shows history); asset 3: held now
    c.executemany("INSERT INTO assignments (asset_id, staff_id, assigned_at, returned_at, note) VALUES (?,?,?,?,?)", [
        (1, 1, "2026-08-01 10:00", "2026-09-15 16:30", "First issue"),
        (1, 2, "2026-09-20 09:15", None, "Re-assigned"),
        (3, 3, "2026-09-01 11:00", None, "")])
    c.commit()
    print("Demo data added. Login: admin / admin123")
c.close()
