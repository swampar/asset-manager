"""Quick checks: python tests.py"""
import os, tempfile
os.environ["ASSET_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import app as m

c = m.app.test_client()
assert c.get("/assets").status_code == 302                       # login required
assert c.post("/login", data={"username": "admin", "password": "bad"}).status_code == 200
assert c.post("/login", data={"username": "admin", "password": "admin123"}).status_code == 302
c.post("/staff/new", data={"name": "A", "email": "a@x.com", "department": "Maths"})
c.post("/staff/new", data={"name": "B", "email": "b@x.com", "department": "Science"})
c.post("/assets/new", data={"name": "Laptop", "type": "laptop", "asset_tag": "T1", "serial_number": "S1"})
dup = c.post("/assets/new", data={"name": "Dup", "type": "laptop", "asset_tag": "T1", "serial_number": "S2"})
assert b"already exists" in dup.data                              # unique tag enforced
st = lambda: m.connect().execute("SELECT status FROM assets WHERE id=1").fetchone()[0]
c.post("/assign", data={"action": "assign", "asset_id": 1, "staff_id": 1})
assert st() == "assigned"
c.post("/assign", data={"action": "assign", "asset_id": 1, "staff_id": 2})   # must be refused
assert m.connect().execute("SELECT COUNT(*) FROM assignments WHERE returned_at IS NULL").fetchone()[0] == 1
c.post("/assign", data={"action": "return", "asset_id": 1, "after": "available"})
assert st() == "available"
c.post("/assign", data={"action": "assign", "asset_id": 1, "staff_id": 2})   # assigned again
rows = m.connect().execute("SELECT staff_id, returned_at FROM assignments ORDER BY id").fetchall()
assert [r[0] for r in rows] == [1, 2] and rows[0][1] and rows[1][1] is None
assert b"A" in c.get("/assets/1").data and b"Still held" in c.get("/assets/1").data
assert c.get("/staff/2").status_code == 200
csv_ = c.get("/assets/export.csv")
assert csv_.mimetype == "text/csv" and b"T1" in csv_.data
assert b"T1" in c.get("/assets?status=assigned&type=laptop&q=T1").data
print("All checks passed.")
