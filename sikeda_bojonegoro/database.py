import sqlite3
from datetime import datetime

DATABASE = "sikeda.db"


def get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(cursor, table, column, definition):
    columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            nama TEXT,
            no_hp TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pendonor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            jenis_kelamin TEXT,
            golongan TEXT,
            kecamatan TEXT,
            no_hp TEXT,
            total_donor INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Aktif',
            nik TEXT,
            tanggal_lahir TEXT,
            alamat TEXT,
            terakhir_donor TEXT,
            user_id INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stok_darah (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            golongan TEXT NOT NULL,
            komponen TEXT NOT NULL,
            jumlah INTEGER DEFAULT 0,
            fasilitas TEXT DEFAULT 'UDD PMI Bojonegoro',
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permintaan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_pasien TEXT NOT NULL,
            golongan TEXT,
            komponen TEXT,
            jumlah INTEGER,
            fasilitas TEXT,
            prioritas TEXT,
            status TEXT DEFAULT 'Menunggu',
            requester_username TEXT,
            tanggal_dibutuhkan TEXT,
            keperluan TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pasien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            nik TEXT,
            tanggal_lahir TEXT,
            jenis_kelamin TEXT,
            golongan TEXT,
            fasilitas TEXT,
            ruangan TEXT,
            dokter TEXT,
            komponen TEXT,
            jumlah INTEGER DEFAULT 1,
            tanggal_dibutuhkan TEXT,
            keperluan TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fasilitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            tipe TEXT,
            alamat TEXT,
            telepon TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jadwal_donor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lokasi TEXT NOT NULL,
            tanggal TEXT,
            jam TEXT,
            alamat TEXT,
            kuota INTEGER DEFAULT 30
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donasi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER,
            fasilitas TEXT,
            tanggal TEXT,
            golongan TEXT,
            volume INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Selesai'
        )
    """)

    # Upgrade database lama tanpa menghapus data pengguna.
    for table, column, definition in [
        ("users", "nama", "TEXT"), ("users", "no_hp", "TEXT"), ("users", "created_at", "TEXT"),
        ("pendonor", "nik", "TEXT"), ("pendonor", "tanggal_lahir", "TEXT"),
        ("pendonor", "alamat", "TEXT"), ("pendonor", "terakhir_donor", "TEXT"), ("pendonor", "user_id", "INTEGER"),
        ("permintaan", "requester_username", "TEXT"), ("permintaan", "tanggal_dibutuhkan", "TEXT"),
        ("permintaan", "keperluan", "TEXT"), ("permintaan", "created_at", "TEXT"),
        ("jadwal_donor", "kuota", "INTEGER DEFAULT 30"),
    ]:
        add_column_if_missing(cursor, table, column, definition)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    users = [
        ("admin", "admin123", "admin", "Administrator", "", now),
        ("petugas", "petugas123", "petugas", "Petugas SIKEDA", "", now),
    ]
    for user in users:
        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password, role, nama, no_hp, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, user)

    stok = [
        ("A", "WB", 29), ("B", "WB", 38), ("O", "WB", 29), ("AB", "WB", 16),
        ("A", "PRC", 332), ("B", "PRC", 283), ("O", "PRC", 241), ("AB", "PRC", 70),
        ("A", "TC", 6), ("B", "TC", 0), ("O", "TC", 19), ("AB", "TC", 0),
        ("A", "FFP", 8), ("B", "FFP", 18), ("O", "FFP", 21), ("AB", "FFP", 7),
    ]
    for golongan, komponen, jumlah in stok:
        cursor.execute("""
            INSERT INTO stok_darah (golongan, komponen, jumlah, updated_at)
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM stok_darah WHERE golongan = ? AND komponen = ?
            )
        """, (golongan, komponen, jumlah, now, golongan, komponen))

    fasilitas = [
        ("UDD PMI Kabupaten Bojonegoro", "PMI", "Bojonegoro", "-"),
        ("Puskesmas Bojonegoro", "Puskesmas", "Bojonegoro", "-"),
        ("RSUD Dr. R. Sosodoro Djatikoesoemo", "Rumah Sakit", "Bojonegoro", "-"),
        ("RS Aisyiyah Bojonegoro", "Rumah Sakit", "Bojonegoro", "-"),
        ("RS Bhayangkara Wahyu Tutuko", "Rumah Sakit", "Bojonegoro", "-"),
        ("RSUD Sumberrejo", "Rumah Sakit", "Sumberrejo", "-"),
        ("RS Ibnu Sina Bojonegoro", "Rumah Sakit", "Bojonegoro", "-"),
        ("RS Muhammadiyah Kalitidu", "Rumah Sakit", "Kalitidu", "-"),
    ]
    for f in fasilitas:
        cursor.execute("""
            INSERT INTO fasilitas (nama, tipe, alamat, telepon)
            SELECT ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM fasilitas WHERE nama = ?)
        """, (*f, f[0]))

    jadwal = [
        ("Badan Pertanahan Nasional Bojonegoro", "2026-09-25", "09:00", "Jl. Dr. Cipto - Bojonegoro", 30),
        ("Puskesmas Kecamatan Dander", "2026-09-25", "09:00", "Jl. Raya No. 8 Dander", 25),
        ("Alon-Alon Bojonegoro", "2026-09-26", "18:00", "Alon-Alon Bojonegoro", 50),
        ("Puskesmas Kecamatan Balen", "2026-09-26", "09:00", "Jl. Raya Balen - Bojonegoro", 25),
        ("TSPM Tapaksuci", "2026-09-26", "19:00", "Kanor", 30),
    ]
    for j in jadwal:
        cursor.execute("""
            INSERT INTO jadwal_donor (lokasi, tanggal, jam, alamat, kuota)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM jadwal_donor WHERE lokasi = ? AND tanggal = ?)
        """, (*j, j[0], j[1]))

    conn.commit()
    conn.close()
