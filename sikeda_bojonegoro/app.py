from functools import wraps
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db

app = Flask(__name__)
app.secret_key = "sikeda-secret-key-change-this"
DATABASE = "sikeda.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Anda tidak memiliki akses ke halaman tersebut.")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def today():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year}


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    conn = get_db()
    facilities = conn.execute("SELECT * FROM fasilitas ORDER BY id LIMIT 4").fetchall()
    stock = conn.execute("""
        SELECT golongan, SUM(jumlah) AS jumlah
        FROM stok_darah GROUP BY golongan ORDER BY CASE golongan WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'O' THEN 3 ELSE 4 END
    """).fetchall()
    conn.close()
    return render_template("home.html", facilities=facilities, stock=stock)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        conn.close()
        if user:
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["user_id"] = user["id"]
            session["nama"] = user["nama"] or user["username"]
            return redirect(url_for("dashboard"))
        flash("Username atau password salah.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        nama = request.form.get("nama", "").strip()
        no_hp = request.form.get("no_hp", "").strip()
        role = request.form.get("role", "masyarakat")
        if role not in {"masyarakat", "pendonor"}:
            role = "masyarakat"
        if not username or not password or not nama:
            flash("Nama, username, dan password wajib diisi.")
            return render_template("register.html")
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password, role, nama, no_hp, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (username, password, role, nama, no_hp, today()))
            if role == "pendonor":
                conn.execute("INSERT INTO pendonor (nama, no_hp, status, user_id) VALUES (?, ?, 'Aktif', last_insert_rowid())", (nama, no_hp))
            conn.commit()
            flash("Pendaftaran berhasil. Silakan login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username sudah digunakan. Silakan pilih username lain.")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    role = session.get("role")
    if role == "pendonor":
        donor = conn.execute("SELECT * FROM pendonor WHERE user_id = ? ORDER BY id DESC LIMIT 1", (session["user_id"],)).fetchone() if session.get("user_id") else None
        schedules = conn.execute("SELECT * FROM jadwal_donor WHERE tanggal >= date('now') ORDER BY tanggal, jam LIMIT 5").fetchall()
        history = []
        if donor:
            history = conn.execute("SELECT * FROM donasi WHERE donor_id = ? ORDER BY tanggal DESC", (donor["id"],)).fetchall()
        conn.close()
        return render_template("pendonor_dashboard.html", donor=donor, schedules=schedules, history=history)
    if role == "masyarakat":
        requests = conn.execute("SELECT * FROM permintaan WHERE requester_username = ? ORDER BY id DESC", (session["username"],)).fetchall()
        stock = conn.execute("SELECT golongan, SUM(jumlah) jumlah FROM stok_darah GROUP BY golongan ORDER BY golongan").fetchall()
        conn.close()
        return render_template("masyarakat_dashboard.html", requests=requests, stock=stock)

    totals = {
        "pendonor": conn.execute("SELECT COUNT(*) FROM pendonor").fetchone()[0],
        "permintaan": conn.execute("SELECT COUNT(*) FROM permintaan").fetchone()[0],
        "fasilitas": conn.execute("SELECT COUNT(*) FROM fasilitas").fetchone()[0],
        "stok": conn.execute("SELECT COALESCE(SUM(jumlah),0) FROM stok_darah").fetchone()[0],
        "pasien": conn.execute("SELECT COUNT(*) FROM pasien").fetchone()[0],
    }
    stock_chart = conn.execute("SELECT golongan, SUM(jumlah) jumlah FROM stok_darah GROUP BY golongan ORDER BY golongan").fetchall()
    request_chart = conn.execute("SELECT status, COUNT(*) jumlah FROM permintaan GROUP BY status").fetchall()
    donor_chart = conn.execute("SELECT substr(COALESCE(terakhir_donor,''),1,7) bulan, COUNT(*) jumlah FROM pendonor WHERE terakhir_donor IS NOT NULL AND terakhir_donor != '' GROUP BY bulan ORDER BY bulan DESC LIMIT 6").fetchall()
    latest_requests = conn.execute("SELECT * FROM permintaan ORDER BY id DESC LIMIT 6").fetchall()
    facilities = conn.execute("SELECT * FROM fasilitas ORDER BY id LIMIT 4").fetchall()
    conn.close()
    return render_template("dashboard.html", totals=totals, stock_chart=stock_chart, request_chart=request_chart, donor_chart=donor_chart, latest_requests=latest_requests, facilities=facilities)


@app.route("/stok", methods=["GET", "POST"])
@login_required
def stok():
    if request.method == "POST" and session.get("role") in {"admin", "petugas"}:
        stock_id = request.form.get("id")
        jumlah = max(0, int(request.form.get("jumlah", 0)))
        conn = get_db()
        conn.execute("UPDATE stok_darah SET jumlah = ?, updated_at = ? WHERE id = ?", (jumlah, today(), stock_id))
        conn.commit(); conn.close()
        flash("Stok berhasil diperbarui.")
        return redirect(url_for("stok"))
    conn = get_db()
    data = conn.execute("SELECT * FROM stok_darah ORDER BY CASE golongan WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'O' THEN 3 ELSE 4 END, komponen").fetchall()
    conn.close()
    return render_template("stok.html", data=data)


@app.route("/pendonor", methods=["GET", "POST"])
@roles_required("admin", "petugas")
def pendonor():
    if request.method == "POST":
        form = request.form
        conn = get_db()
        conn.execute("""INSERT INTO pendonor (nama, nik, tanggal_lahir, jenis_kelamin, golongan, kecamatan, no_hp, alamat, terakhir_donor, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (form.get("nama"), form.get("nik"), form.get("tanggal_lahir"), form.get("jenis_kelamin"), form.get("golongan"), form.get("kecamatan"), form.get("no_hp"), form.get("alamat"), form.get("terakhir_donor"), form.get("status", "Aktif")))
        conn.commit(); conn.close(); flash("Data pendonor berhasil ditambahkan.")
        return redirect(url_for("pendonor"))
    conn = get_db(); data = conn.execute("SELECT * FROM pendonor ORDER BY id DESC").fetchall(); conn.close()
    return render_template("pendonor.html", data=data)


@app.route("/pasien", methods=["GET", "POST"])
@roles_required("admin", "petugas")
def pasien():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        conn.execute("""INSERT INTO pasien (nama, nik, tanggal_lahir, jenis_kelamin, golongan, fasilitas, ruangan, dokter, komponen, jumlah, tanggal_dibutuhkan, keperluan, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (f.get("nama"), f.get("nik"), f.get("tanggal_lahir"), f.get("jenis_kelamin"), f.get("golongan"), f.get("fasilitas"), f.get("ruangan"), f.get("dokter"), f.get("komponen"), int(f.get("jumlah", 1)), f.get("tanggal_dibutuhkan"), f.get("keperluan"), today()))
        conn.commit(); flash("Data pasien berhasil ditambahkan.")
        conn.close(); return redirect(url_for("pasien"))
    data = conn.execute("SELECT * FROM pasien ORDER BY id DESC").fetchall()
    facilities = conn.execute("SELECT nama FROM fasilitas ORDER BY nama").fetchall()
    conn.close(); return render_template("pasien.html", data=data, facilities=facilities)


@app.route("/permintaan", methods=["GET", "POST"])
@login_required
def permintaan():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        conn.execute("""INSERT INTO permintaan (nama_pasien, golongan, komponen, jumlah, fasilitas, prioritas, status, requester_username, tanggal_dibutuhkan, keperluan, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'Menunggu', ?, ?, ?, ?)""",
                     (f.get("nama_pasien"), f.get("golongan"), f.get("komponen"), int(f.get("jumlah", 1)), f.get("fasilitas"), f.get("prioritas", "Normal"), session["username"], f.get("tanggal_dibutuhkan"), f.get("keperluan"), today()))
        conn.commit(); flash("Permintaan darah berhasil dikirim.")
        conn.close(); return redirect(url_for("permintaan"))
    if session.get("role") in {"admin", "petugas"}:
        data = conn.execute("SELECT * FROM permintaan ORDER BY id DESC").fetchall()
    else:
        data = conn.execute("SELECT * FROM permintaan WHERE requester_username = ? ORDER BY id DESC", (session["username"],)).fetchall()
    facilities = conn.execute("SELECT nama FROM fasilitas ORDER BY nama").fetchall()
    conn.close(); return render_template("permintaan.html", data=data, facilities=facilities)


@app.route("/permintaan/<int:request_id>/status", methods=["POST"])
@roles_required("admin", "petugas")
def update_request_status(request_id):
    status = request.form.get("status")
    allowed = {"Menunggu", "Diproses", "Disetujui", "Dipenuhi", "Ditolak"}
    if status not in allowed:
        flash("Status tidak valid.")
        return redirect(url_for("permintaan"))
    conn = get_db(); conn.execute("UPDATE permintaan SET status = ? WHERE id = ?", (status, request_id)); conn.commit(); conn.close()
    flash("Status permintaan diperbarui.")
    return redirect(url_for("permintaan"))


@app.route("/jadwal", methods=["GET", "POST"])
@login_required
def jadwal():
    conn = get_db()
    if request.method == "POST" and session.get("role") in {"admin", "petugas"}:
        f = request.form
        conn.execute("INSERT INTO jadwal_donor (lokasi, tanggal, jam, alamat, kuota) VALUES (?, ?, ?, ?, ?)", (f.get("lokasi"), f.get("tanggal"), f.get("jam"), f.get("alamat"), int(f.get("kuota", 30))))
        conn.commit(); flash("Jadwal donor berhasil ditambahkan.")
        conn.close(); return redirect(url_for("jadwal"))
    data = conn.execute("SELECT * FROM jadwal_donor ORDER BY tanggal, jam").fetchall(); conn.close()
    return render_template("jadwal.html", data=data)


@app.route("/fasilitas")
@login_required
def fasilitas():
    conn = get_db(); data = conn.execute("SELECT * FROM fasilitas ORDER BY id").fetchall(); conn.close()
    return render_template("fasilitas.html", data=data)


@app.route("/cari-darah")
def cari_darah():
    golongan = request.args.get("golongan", "").upper()
    conn = get_db()
    query = "SELECT golongan, SUM(jumlah) jumlah FROM stok_darah"
    params = []
    if golongan in {"A", "B", "O", "AB"}:
        query += " WHERE golongan = ?"; params.append(golongan)
    query += " GROUP BY golongan ORDER BY golongan"
    data = conn.execute(query, params).fetchall(); conn.close()
    return render_template("cari_darah.html", data=data, golongan=golongan)


@app.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    conn = get_db()
    if request.method == "POST":
        nama = request.form.get("nama", "").strip(); no_hp = request.form.get("no_hp", "").strip()
        conn.execute("UPDATE users SET nama = ?, no_hp = ? WHERE username = ?", (nama, no_hp, session["username"]))
        session["nama"] = nama
        if session.get("role") == "pendonor":
            conn.execute("UPDATE pendonor SET nama = ?, no_hp = ? WHERE user_id = (SELECT id FROM users WHERE username = ?)", (nama, no_hp, session["username"]))
        conn.commit(); flash("Profil berhasil diperbarui.")
    user = conn.execute("SELECT * FROM users WHERE username = ?", (session["username"],)).fetchone(); conn.close()
    return render_template("profil.html", user=user)


@app.route("/api/chart/stok")
@login_required
def chart_stok():
    conn = get_db(); rows = conn.execute("SELECT golongan, SUM(jumlah) jumlah FROM stok_darah GROUP BY golongan ORDER BY golongan").fetchall(); conn.close()
    return {"labels": [r["golongan"] for r in rows], "values": [r["jumlah"] for r in rows]}


import os

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
