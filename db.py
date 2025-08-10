# db.py
import sqlite3
import bcrypt
from datetime import datetime

DB_PATH = "planner.sqlite"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ===== User Management =====
def create_user(email, name, nickname, password):
    conn = get_conn(); cur = conn.cursor()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    cur.execute(
        "INSERT INTO users (email, name, nickname, pw_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (email, name, nickname, pw_hash, datetime.utcnow().isoformat())
    )
    conn.commit(); conn.close()

def get_user_by_email(email):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone(); conn.close()
    return row

def get_user_by_id(user_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone(); conn.close()
    return row

def verify_user(email, password):
    user = get_user_by_email(email)
    if not user: return None
    pw_hash = user[3]  # id=0, email=1, name=2, nickname=3?, pw_hash=4 (컬럼 순서 유의)
    if bcrypt.checkpw(password.encode(), pw_hash):
        return user
    return None

# ===== Room Management =====
def create_room(room_id, title, owner_id, start, end, min_days, quorum, w_full=1.0, w_am=0.3, w_pm=0.1, w_eve=0.5):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO rooms (id, title, owner_id, start, end, min_days, quorum, w_full, w_am, w_pm, w_eve, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (room_id, title, owner_id, start, end, min_days, quorum, w_full, w_am, w_pm, w_eve, datetime.utcnow().isoformat())
    )
    conn.commit(); conn.close()

def delete_room(room_id, owner_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM rooms WHERE id = ? AND owner_id = ?", (room_id, owner_id))
    conn.commit(); conn.close()

# ===== Membership =====
def join_room(user_id, room_id, role="member"):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO memberships (user_id, room_id, role) VALUES (?, ?, ?)", (user_id, room_id, role))
    conn.commit(); conn.close()

def get_rooms_for_user(user_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT r.* FROM rooms r
        JOIN memberships m ON r.id = m.room_id
        WHERE m.user_id = ?
    """, (user_id,))
    rows = cur.fetchall(); conn.close()
    return rows

# ===== Availability =====
def save_availability(user_id, room_id, day, status):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO availability (user_id, room_id, day, status)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, room_id, day) DO UPDATE SET status = excluded.status
    """, (user_id, room_id, day, status))
    conn.commit(); conn.close()

def get_availability(room_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT * FROM availability WHERE room_id = ?
    """, (room_id,))
    rows = conn.fetchall(); conn.close()
    return rows

# ===== Init DB =====
def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.executescript("""
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      name  TEXT NOT NULL,
      pw_hash BLOB NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS rooms(
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      owner_id INTEGER NOT NULL,
      start TEXT NOT NULL,
      end   TEXT NOT NULL,
      min_days INTEGER NOT NULL,
      quorum   INTEGER NOT NULL,
      w_full REAL NOT NULL DEFAULT 1.0,
      w_am   REAL NOT NULL DEFAULT 0.3,
      w_pm   REAL NOT NULL DEFAULT 0.1,
      w_eve  REAL NOT NULL DEFAULT 0.5,
      created_at TEXT NOT NULL,
      FOREIGN KEY(owner_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS memberships(
      user_id INTEGER NOT NULL,
      room_id TEXT NOT NULL,
      role    TEXT NOT NULL,
      submitted INTEGER NOT NULL DEFAULT 0,
      UNIQUE(user_id, room_id),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(room_id) REFERENCES rooms(id)
    );

    CREATE TABLE IF NOT EXISTS availability(
      user_id INTEGER NOT NULL,
      room_id TEXT NOT NULL,
      day TEXT NOT NULL,
      status TEXT NOT NULL,
      PRIMARY KEY(user_id, room_id, day),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(room_id) REFERENCES rooms(id)
    );
    """)
    conn.commit()

    # nickname 컬럼 조건부 추가
    cur.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cur.fetchall()]
    if "nickname" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
        conn.commit()
        cur.execute("UPDATE users SET nickname = name WHERE nickname IS NULL OR nickname = ''")
        conn.commit()

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_nickname_uq "
        "ON users(nickname) WHERE nickname IS NOT NULL"
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
