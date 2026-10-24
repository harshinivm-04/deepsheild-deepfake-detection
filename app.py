import os
import io
import csv
import json
import uuid
import sqlite3
import threading
from datetime import datetime
from functools import wraps

from flask import (Flask, g, request, session, redirect, url_for, render_template,
                   jsonify, flash, send_from_directory, abort, Response)
from werkzeug.security import generate_password_hash, check_password_hash

import detector

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
DB = os.path.join(BASE, "deepshield.db")
os.makedirs(UPLOADS, exist_ok=True)

IMG_EXT = {"jpg", "jpeg", "png", "webp", "bmp"}
VID_EXT = {"mp4", "avi", "mov", "mkv", "webm"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

key_file = os.path.join(BASE, ".secret_key")
if not os.path.exists(key_file):
    with open(key_file, "wb") as f:
        f.write(os.urandom(32))
with open(key_file, "rb") as f:
    app.secret_key = f.read()


# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored TEXT NOT NULL,
            kind TEXT NOT NULL,
            verdict TEXT NOT NULL,
            fake_prob REAL NOT NULL,
            confidence REAL NOT NULL,
            details TEXT NOT NULL,
            ela TEXT,
            heat TEXT,
            thumb TEXT,
            created TEXT NOT NULL
        );
        """)
        try:  # upgrade older databases
            c.execute("ALTER TABLE scans ADD COLUMN heat TEXT")
        except sqlite3.OperationalError:
            pass


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------- auth ----------
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "uid" not in session:
            if request.path.startswith("/api") or request.path.startswith("/media"):
                return jsonify(error="Session expired. Please sign in again."), 401
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


@app.route("/")
def home():
    return redirect(url_for("dashboard" if "uid" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"], session["name"] = user["id"], user["name"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html", mode="login")


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    pw = request.form.get("password", "")
    if not name or "@" not in email:
        flash("Enter your name and a valid email.", "error")
    elif len(pw) < 6:
        flash("Password must be at least 6 characters.", "error")
    elif pw != request.form.get("confirm", ""):
        flash("Passwords do not match.", "error")
    elif db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        flash("That email is already registered. Sign in instead.", "error")
    else:
        cur = db().execute("INSERT INTO users(name,email,password_hash,created) VALUES(?,?,?,?)",
                           (name, email, generate_password_hash(pw), now()))
        db().commit()
        session.clear()
        session["uid"], session["name"] = cur.lastrowid, name
        return redirect(url_for("dashboard"))
    return render_template("login.html", mode="register")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", name=session["name"])


# ---------- API ----------
def serialize(r):
    d = json.loads(r["details"])
    return dict(
        id=r["id"], filename=r["filename"], kind=r["kind"], verdict=r["verdict"],
        fake_prob=r["fake_prob"], confidence=r["confidence"], created=r["created"],
        face_found=d.get("face_found", False), frames=d.get("frames", []),
        media_url=f"/media/{r['stored']}",
        ela_url=f"/media/{r['ela']}" if r["ela"] else None,
        heat_url=f"/media/{r['heat']}" if r["heat"] else None,
        thumb_url=f"/media/{r['thumb']}" if r["thumb"] else None,
    )


@app.post("/api/analyze")
@login_required
def analyze():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Choose an image or video first."), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    kind = "image" if ext in IMG_EXT else "video" if ext in VID_EXT else None
    if not kind:
        return jsonify(error="Unsupported file. Use JPG, PNG, WEBP, MP4, MOV, AVI or WEBM."), 400

    stem = uuid.uuid4().hex
    stored = f"{stem}.{ext}"
    path = os.path.join(UPLOADS, stored)
    f.save(path)
    try:
        fn = detector.analyze_image if kind == "image" else detector.analyze_video
        res = fn(path, stem, UPLOADS)
    except Exception as e:
        if os.path.exists(path):
            os.remove(path)
        return jsonify(error=f"Could not analyse this file: {e}"), 422

    p = res["fake_prob"]
    verdict = "Fake" if p >= 0.5 else "Real"
    conf = round(max(p, 1 - p) * 100, 2)
    cur = db().execute(
        "INSERT INTO scans(user_id,filename,stored,kind,verdict,fake_prob,confidence,details,ela,heat,thumb,created)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (session["uid"], f.filename, stored, kind, verdict, p, conf,
         json.dumps(dict(face_found=res["face_found"], frames=res["frames"])),
         res["ela"], res.get("heat"), res["thumb"], now()))
    db().commit()
    row = db().execute("SELECT * FROM scans WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(serialize(row))


@app.get("/api/history")
@login_required
def history():
    rows = db().execute("SELECT * FROM scans WHERE user_id=? ORDER BY id DESC", (session["uid"],)).fetchall()
    return jsonify([serialize(r) for r in rows])


@app.delete("/api/history/<int:sid>")
@login_required
def delete_scan(sid):
    r = db().execute("SELECT * FROM scans WHERE id=? AND user_id=?", (sid, session["uid"])).fetchone()
    if not r:
        return jsonify(error="Scan not found."), 404
    for name in (r["stored"], r["ela"], r["heat"], r["thumb"]):
        if name and os.path.exists(os.path.join(UPLOADS, name)):
            os.remove(os.path.join(UPLOADS, name))
    db().execute("DELETE FROM scans WHERE id=?", (sid,))
    db().commit()
    return jsonify(ok=True)


@app.get("/api/export.csv")
@login_required
def export_csv():
    rows = db().execute("SELECT * FROM scans WHERE user_id=? ORDER BY id DESC", (session["uid"],)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "filename", "type", "verdict", "confidence_%", "fake_probability", "scanned_at_utc"])
    for r in rows:
        w.writerow([r["id"], r["filename"], r["kind"], r["verdict"], r["confidence"],
                    round(r["fake_prob"], 4), r["created"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=deepshield_history.csv"})


@app.get("/media/<name>")
@login_required
def media(name):
    ok = db().execute("SELECT 1 FROM scans WHERE user_id=? AND (stored=? OR ela=? OR heat=? OR thumb=?)",
                      (session["uid"], name, name, name, name)).fetchone()
    if not ok:
        abort(404)
    return send_from_directory(UPLOADS, name)


@app.errorhandler(413)
def too_big(_):
    return jsonify(error="File is larger than 100 MB."), 413


if __name__ == "__main__":
    init_db()
    threading.Thread(target=detector.load_all, daemon=True).start()  # warm up model
    app.run(debug=True, use_reloader=False)