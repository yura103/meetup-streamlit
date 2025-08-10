# db.py
import sqlite3, os, bcrypt, secrets, string, datetime as dt

DB_PATH = os.environ.get("PLANNER_DB", "planner.sqlite")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
      start TEXT NOT NULL,            -- YYYY-MM-DD
      end   TEXT NOT NULL,            -- YYYY-MM-DD
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
      role    TEXT NOT NULL,          -- 'owner' or 'member'
      submitted INTEGER NOT NULL DEFAULT 0,  -- 0/1
      UNIQUE(user_id, room_id),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(room_id) REFERENCES rooms(id)
    );

    CREATE TABLE IF NOT EXISTS availability(
      user_id INTEGER NOT NULL,
      room_id TEXT NOT NULL,
      day TEXT NOT NULL,              -- YYYY-MM-DD
      status TEXT NOT NULL,           -- off/am/pm/eve/full
      PRIMARY KEY(user_id, room_id, day),
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(room_id) REFERENCES rooms(id)
    );
    """)
    conn.commit()

    # --- 마이그레이션: users.nickname 컬럼 추가 & 기본 채우기 ---
    cur.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cur.fetchall()]
    if "nickname" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN nickname TEXT UNIQUE")
        conn.commit()
        cur.execute("UPDATE users SET nickname = name WHERE nickname IS NULL")
        conn.commit()

    conn.close()

# ---------- Auth ----------
def hash_pw(pw:str)->bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())

def check_pw(pw:str, pw_hash:bytes)->bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash)
    except Exception:
        return False

def create_user(email:str, name:str, nickname:str, pw:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO users(email,name,nickname,pw_hash,created_at) VALUES(?,?,?,?,?)",
                (email, name, nickname, hash_pw(pw), dt.datetime.utcnow().isoformat()))
    conn.commit(); uid = cur.lastrowid; conn.close(); return uid

def get_user_by_email(email:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone(); conn.close(); return row

def get_user_by_login(login:str):
    """login은 이메일 또는 닉네임."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (login,))
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT * FROM users WHERE nickname=?", (login,))
        row = cur.fetchone()
    conn.close(); return row

def get_user(user_id:int):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = cur.fetchone(); conn.close(); return row

# ---------- Rooms / Memberships ----------
def gen_room_id(n=6):
    alpha = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))

def create_room(owner_id:int, title:str, start:str, end:str, min_days:int, quorum:int,
                w_full=1.0, w_am=0.3, w_pm=0.1, w_eve=0.5):
    rid = gen_room_id()
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO rooms(id,title,owner_id,start,end,min_days,quorum,
                 w_full,w_am,w_pm,w_eve,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid,title,owner_id,start,end,min_days,quorum,
                 w_full,w_am,w_pm,w_eve,dt.datetime.utcnow().isoformat()))
    cur.execute("INSERT OR IGNORE INTO memberships(user_id,room_id,role,submitted) VALUES(?,?,?,0)",
                (owner_id,rid,"owner"))
    conn.commit(); conn.close(); return rid

def update_room(owner_id:int, room_id:str, **fields):
    if not fields: return False
    keys, vals = [], []
    for k,v in fields.items():
        if k in ("title","start","end","min_days","quorum","w_full","w_am","w_pm","w_eve"):
            keys.append(f"{k}=?"); vals.append(v)
    if not keys: return False
    vals += [owner_id, room_id]
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"UPDATE rooms SET {', '.join(keys)} WHERE owner_id=? AND id=?", vals)
    conn.commit(); ok = cur.rowcount>0; conn.close(); return ok

def delete_room(room_id:str, owner_id:int):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM rooms WHERE id=? AND owner_id=?", (room_id, owner_id))
    if cur.rowcount:
        cur.execute("DELETE FROM memberships WHERE room_id=?", (room_id,))
        cur.execute("DELETE FROM availability WHERE room_id=?", (room_id,))
    conn.commit(); conn.close(); return True

def list_my_rooms(user_id:int):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT r.*, m.role, m.submitted FROM rooms r
                   JOIN memberships m ON m.room_id=r.id
                   WHERE m.user_id=?
                   ORDER BY r.created_at DESC""", (user_id,))
    rows = cur.fetchall(); conn.close(); return rows

def get_room(room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
    room = cur.fetchone()
    cur.execute("""SELECT u.id,u.name,u.email,u.nickname,m.role,m.submitted
                   FROM memberships m JOIN users u ON u.id=m.user_id
                   WHERE m.room_id=? ORDER BY u.name""", (room_id,))
    members = cur.fetchall()
    conn.close(); return room, members

def invite_user_by_email(room_id:str, email:str):
    u = get_user_by_email(email)
    if not u: return False, "해당 이메일의 사용자가 아직 없어요."
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO memberships(user_id,room_id,role,submitted) VALUES(?,?,?,0)",
                (u["id"], room_id, "member"))
    conn.commit(); conn.close(); return True, "초대 완료"

def remove_member(room_id:str, user_id:int):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM availability WHERE user_id=? AND room_id=?", (user_id, room_id))
    cur.execute("DELETE FROM memberships WHERE user_id=? AND room_id=?", (user_id, room_id))
    conn.commit(); conn.close()

# ---------- Availability / Submission ----------
def get_weights(room):
    return dict(full=room["w_full"], am=room["w_am"], pm=room["w_pm"], eve=room["w_eve"], off=0.0)

def upsert_availability(user_id:int, room_id:str, items:dict):
    conn = get_conn(); cur = conn.cursor()
    for day, status in items.items():
        cur.execute("""INSERT INTO availability(user_id,room_id,day,status)
                       VALUES (?,?,?,?)
                       ON CONFLICT(user_id,room_id,day)
                       DO UPDATE SET status=excluded.status""",
                    (user_id,room_id,day,status))
    conn.commit(); conn.close()

def get_my_availability(user_id:int, room_id:str) -> dict:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT day,status FROM availability WHERE user_id=? AND room_id=?", (user_id,room_id))
    rows = cur.fetchall(); conn.close()
    return {r["day"]: r["status"] for r in rows}

def clear_my_availability(user_id:int, room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM availability WHERE user_id=? AND room_id=?", (user_id, room_id))
    conn.commit(); conn.close()

def set_submitted(user_id:int, room_id:str, submitted:bool):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE memberships SET submitted=? WHERE user_id=? AND room_id=?",
                (1 if submitted else 0, user_id, room_id))
    conn.commit(); conn.close()

def all_submitted(room_id:str) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM memberships WHERE room_id=?", (room_id,))
    total = cur.fetchone()["c"]
    if total == 0: conn.close(); return False
    cur.execute("SELECT COUNT(*) AS c FROM memberships WHERE room_id=? AND submitted=1", (room_id,))
    done = cur.fetchone()["c"]; conn.close()
    return (done >= total)
    
def day_aggregate(room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
    room = cur.fetchone()
    w = get_weights(room)

    import datetime as _dt
    d0 = _dt.date.fromisoformat(room["start"]); d1 = _dt.date.fromisoformat(room["end"])
    days = [(d0 + _dt.timedelta(days=i)).isoformat() for i in range((d1-d0).days+1)]

    cur.execute("SELECT user_id, day, status FROM availability WHERE room_id=?", (room_id,))
    rows = cur.fetchall(); conn.close()

    agg = {d: {"full":0,"am":0,"pm":0,"eve":0,"off":0,"score":0.0} for d in days}
    for r in rows:
        if r["day"] in agg:
            agg[r["day"]][r["status"]] += 1

    for d in days:
        a = agg[d]
        a["score"] = a["full"]*w["full"] + a["am"]*w["am"] + a["pm"]*w["pm"] + a["eve"]*w["eve"]

    return room, days, agg, w
