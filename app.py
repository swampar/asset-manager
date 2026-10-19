"""IT Asset Management System - Flask + SQLite (no ORM, plain SQL)."""
import csv
import io
import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ASSET_DB", os.path.join(BASE, "assets.db"))
TYPES = ["laptop", "monitor", "phone", "other"]
STATUSES = ["available", "assigned", "under repair"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL, department TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('laptop','monitor','phone','other')),
    asset_tag TEXT UNIQUE NOT NULL, serial_number TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('available','assigned','under repair')));
-- One row per time an asset is handed out. returned_at stays NULL while it is held.
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    assigned_at TEXT NOT NULL, returned_at TEXT, note TEXT);
-- Database-level guarantee: an asset can have at most ONE open assignment.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_assignment
    ON assignments(asset_id) WHERE returned_at IS NULL;
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM users").fetchone():
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     ("admin", generate_password_hash("admin123")))
    conn.commit()
    conn.close()


def db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------- login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = db().execute("SELECT * FROM users WHERE username = ?",
                            (request.form["username"].strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session["user"] = user["username"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("assets"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- assets ----------
def asset_rows(q="", status="", type_=""):
    sql = """SELECT a.*, s.name AS holder, s.id AS holder_id FROM assets a
             LEFT JOIN assignments x ON x.asset_id = a.id AND x.returned_at IS NULL
             LEFT JOIN staff s ON s.id = x.staff_id WHERE 1=1"""
    args = []
    if q:
        sql += " AND (a.name LIKE ? OR a.asset_tag LIKE ? OR a.serial_number LIKE ?)"
        args += [f"%{q}%"] * 3
    if status in STATUSES:
        sql += " AND a.status = ?"
        args.append(status)
    if type_ in TYPES:
        sql += " AND a.type = ?"
        args.append(type_)
    return db().execute(sql + " ORDER BY a.asset_tag", args).fetchall()


@app.route("/")
@app.route("/assets")
@login_required
def assets():
    q, status, type_ = (request.args.get(k, "").strip() for k in ("q", "status", "type"))
    return render_template("assets.html", rows=asset_rows(q, status, type_), q=q,
                           status=status, type_=type_, TYPES=TYPES, STATUSES=STATUSES)


@app.route("/assets/export.csv")
@login_required
def export_csv():
    q, status, type_ = (request.args.get(k, "").strip() for k in ("q", "status", "type"))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Type", "Asset tag", "Serial number", "Status", "Held by"])
    for r in asset_rows(q, status, type_):
        w.writerow([r["name"], r["type"], r["asset_tag"], r["serial_number"], r["status"], r["holder"] or ""])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=assets.csv"})


def read_asset_form():
    f = request.form
    return {k: f.get(k, "").strip() for k in ("name", "type", "asset_tag", "serial_number", "status")}


def asset_error(d):
    if not (d["name"] and d["asset_tag"] and d["serial_number"]):
        return "Name, asset tag and serial number are required."
    if d["type"] not in TYPES:
        return "Choose a valid type."
    return None


@app.route("/assets/new", methods=["GET", "POST"])
@login_required
def asset_new():
    d = {"name": "", "type": "laptop", "asset_tag": "", "serial_number": "", "status": "available"}
    if request.method == "POST":
        d = read_asset_form()
        err = asset_error(d)
        if not err:
            try:
                status = "under repair" if d["status"] == "under repair" else "available"
                db().execute("INSERT INTO assets (name, type, asset_tag, serial_number, status) VALUES (?,?,?,?,?)",
                             (d["name"], d["type"], d["asset_tag"], d["serial_number"], status))
                db().commit()
                flash("Asset added.", "ok")
                return redirect(url_for("assets"))
            except sqlite3.IntegrityError:
                err = "That asset tag or serial number already exists."
        flash(err, "error")
    return render_template("asset_form.html", a=d, TYPES=TYPES, editing=False, locked=False)


@app.route("/assets/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
def asset_edit(asset_id):
    a = db().execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if a is None:
        return "Asset not found", 404
    locked = a["status"] == "assigned"  # status of a held asset changes only via Return
    if request.method == "POST":
        d = read_asset_form()
        err = asset_error(d)
        if not err:
            status = a["status"] if locked else ("under repair" if d["status"] == "under repair" else "available")
            try:
                db().execute("UPDATE assets SET name=?, type=?, asset_tag=?, serial_number=?, status=? WHERE id=?",
                             (d["name"], d["type"], d["asset_tag"], d["serial_number"], status, asset_id))
                db().commit()
                flash("Asset updated.", "ok")
                return redirect(url_for("asset_detail", asset_id=asset_id))
            except sqlite3.IntegrityError:
                err = "That asset tag or serial number already exists."
        flash(err, "error")
        a = {**d, "id": asset_id}
    return render_template("asset_form.html", a=a, TYPES=TYPES, editing=True, locked=locked)


@app.route("/assets/<int:asset_id>")
@login_required
def asset_detail(asset_id):
    a = db().execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if a is None:
        return "Asset not found", 404
    history = db().execute("""SELECT x.*, s.name AS staff_name FROM assignments x
                              JOIN staff s ON s.id = x.staff_id
                              WHERE x.asset_id = ? ORDER BY x.assigned_at DESC, x.id DESC""", (asset_id,)).fetchall()
    return render_template("asset_detail.html", a=a, history=history)


# ---------- staff ----------
@app.route("/staff")
@login_required
def staff_list():
    rows = db().execute("""SELECT s.*, COUNT(x.id) AS held FROM staff s
                           LEFT JOIN assignments x ON x.staff_id = s.id AND x.returned_at IS NULL
                           GROUP BY s.id ORDER BY s.name""").fetchall()
    return render_template("staff.html", rows=rows)


@app.route("/staff/new", methods=["GET", "POST"])
@login_required
def staff_new():
    d = {"name": "", "email": "", "department": ""}
    if request.method == "POST":
        d = {k: request.form.get(k, "").strip() for k in d}
        if not all(d.values()):
            flash("Name, email and department are required.", "error")
        elif "@" not in d["email"]:
            flash("Enter a valid email address.", "error")
        else:
            try:
                db().execute("INSERT INTO staff (name, email, department) VALUES (?,?,?)",
                             (d["name"], d["email"], d["department"]))
                db().commit()
                flash("Staff member added.", "ok")
                return redirect(url_for("staff_list"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("staff_form.html", s=d)


@app.route("/staff/<int:staff_id>")
@login_required
def staff_detail(staff_id):
    s = db().execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
    if s is None:
        return "Staff member not found", 404
    held = db().execute("""SELECT a.*, x.assigned_at FROM assignments x JOIN assets a ON a.id = x.asset_id
                           WHERE x.staff_id = ? AND x.returned_at IS NULL ORDER BY a.asset_tag""", (staff_id,)).fetchall()
    past = db().execute("""SELECT a.*, x.assigned_at, x.returned_at FROM assignments x JOIN assets a ON a.id = x.asset_id
                           WHERE x.staff_id = ? AND x.returned_at IS NOT NULL ORDER BY x.returned_at DESC""", (staff_id,)).fetchall()
    return render_template("staff_detail.html", s=s, held=held, past=past)


# ---------- assign / return ----------
@app.route("/assign", methods=["GET", "POST"])
@login_required
def assign():
    conn = db()
    if request.method == "POST":
        action = request.form.get("action")
        asset_id = request.form.get("asset_id", type=int)
        try:
            with conn:  # one transaction: both writes succeed or neither does
                if action == "assign":
                    staff_id = request.form.get("staff_id", type=int)
                    ok = conn.execute("UPDATE assets SET status='assigned' WHERE id=? AND status='available'",
                                      (asset_id,)).rowcount
                    if not ok or not staff_id:
                        raise ValueError("That asset is not available, or no staff member was chosen.")
                    conn.execute("INSERT INTO assignments (asset_id, staff_id, assigned_at, note) VALUES (?,?,?,?)",
                                 (asset_id, staff_id, now(), request.form.get("note", "").strip()))
                    flash("Asset assigned.", "ok")
                elif action == "return":
                    after = "under repair" if request.form.get("after") == "under repair" else "available"
                    closed = conn.execute("UPDATE assignments SET returned_at=? WHERE asset_id=? AND returned_at IS NULL",
                                          (now(), asset_id)).rowcount
                    if not closed:
                        raise ValueError("That asset is not currently assigned.")
                    conn.execute("UPDATE assets SET status=? WHERE id=?", (after, asset_id))
                    flash("Asset returned.", "ok")
        except (ValueError, sqlite3.IntegrityError) as e:
            flash(str(e) if isinstance(e, ValueError) else "Could not save that change.", "error")
        return redirect(url_for("assign"))
    available = conn.execute("SELECT * FROM assets WHERE status='available' ORDER BY asset_tag").fetchall()
    out = conn.execute("""SELECT a.*, s.name AS holder FROM assets a
                          JOIN assignments x ON x.asset_id=a.id AND x.returned_at IS NULL
                          JOIN staff s ON s.id=x.staff_id ORDER BY a.asset_tag""").fetchall()
    staff = conn.execute("SELECT * FROM staff ORDER BY name").fetchall()
    return render_template("assign.html", available=available, out=out, staff=staff)


init_db()

if __name__ == "__main__":
    app.run(debug=True)
