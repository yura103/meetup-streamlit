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
    # --- itinerary (계획/동선) ---
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS itinerary_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_id TEXT NOT NULL,
      day TEXT NOT NULL,                 -- YYYY-MM-DD
      position INTEGER NOT NULL,         -- 동선 순서 (1..n)
      name TEXT NOT NULL,
      category TEXT NOT NULL,            -- 식사/숙소/놀기/기타...
      lat REAL, lon REAL,
      budget REAL NOT NULL DEFAULT 0,
      start_time TEXT,                   -- "10:00" (선택)
      end_time   TEXT,                   -- "12:30" (선택)
      is_anchor INTEGER NOT NULL DEFAULT 0,  -- 숙소 등 고정점
      notes TEXT,
      created_by INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(room_id) REFERENCES rooms(id),
      FOREIGN KEY(created_by) REFERENCES users(id)
    );
    """)
    conn.commit()

    # --- expenses (지출/정산) ---
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS expenses(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_id TEXT NOT NULL,
      day TEXT,
      place TEXT,                -- 선택: 장소명
      payer_id INTEGER NOT NULL, -- 결제자
      amount REAL NOT NULL,
      memo TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(room_id) REFERENCES rooms(id),
      FOREIGN KEY(payer_id) REFERENCES users(id)
    );
    """)
    conn.commit()

    # nickname 안전 추가
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

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS reset_tokens(
      token TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      expires_at TEXT NOT NULL,
      used INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    conn.commit(); conn.close()

# ---- Auth primitives ----
def hash_pw(pw:str)->bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())

def check_pw(pw:str, pw_hash:bytes)->bool:
    try: return bcrypt.checkpw(pw.encode("utf-8"), pw_hash)
    except Exception: return False

def email_exists(email:str)->bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE email=?", (email,))
    row = cur.fetchone(); conn.close(); return bool(row)

def nickname_exists(nick:str)->bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE nickname=?", (nick,))
    row = cur.fetchone(); conn.close(); return bool(row)

def create_user(email:str, name:str, nickname:str, pw:str):
    if email_exists(email): raise ValueError("email_taken")
    if nickname and nickname_exists(nickname): raise ValueError("nickname_taken")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO users(email,name,nickname,pw_hash,created_at) VALUES(?,?,?,?,?)",
                (email, name, nickname, hash_pw(pw), dt.datetime.utcnow().isoformat()))
    conn.commit(); uid = cur.lastrowid; conn.close(); return uid

def get_user_by_email(email:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone(); conn.close(); return row

def get_user_by_login(login:str):
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

def update_password(user_id:int, new_pw:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new_pw), user_id))
    conn.commit(); conn.close()

# reset token
def create_reset_token(email:str, ttl_minutes:int=30):
    user = get_user_by_email(email)
    if not user: return None, "no_user"
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.utcnow() + dt.timedelta(minutes=ttl_minutes)).isoformat()
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO reset_tokens(token,user_id,expires_at,used,created_at) VALUES(?,?,?,?,?)",
                (token, user["id"], expires, 0, dt.datetime.utcnow().isoformat()))
    conn.commit(); conn.close(); return token, "ok"

def verify_reset_token(token:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM reset_tokens WHERE token=?", (token,))
    row = cur.fetchone(); conn.close()
    if not row: return None, "not_found"
    if row["used"]: return None, "used"
    if dt.datetime.fromisoformat(row["expires_at"]) < dt.datetime.utcnow():
        return None, "expired"
    return row, "ok"

def consume_reset_token(token:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE reset_tokens SET used=1 WHERE token=?", (token,))
    conn.commit(); conn.close()

# ---- Rooms / Members ----
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

# ---- Availability / Submission ----
def get_weights(room):
    return {
        "full": 1.0,   # 하루종일
        "am": 0.7,     # 7시간 이상
        "pm": 0.5,     # 5시간 이상
        "eve": 0.4,    # 3시간 이상 (잘 모르겠다)
        "off": 0.0     # 불가
    }

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

def availability_names_by_day(room_id: str):
    """
    날짜별로 상태(off/eve/pm/am/full) → 닉네임(or 이름) 목록
    return: { 'YYYY-MM-DD': {'full':[...],'am':[...],'pm':[...],'eve':[...],'off':[...]} }
    """
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT a.day, a.status, COALESCE(u.nickname, u.name) AS nick
        FROM availability a
        JOIN users u ON u.id = a.user_id
        WHERE a.room_id = ?
    """, (room_id,))
    rows = cur.fetchall(); conn.close()

    out = {}
    for r in rows:
        d = r["day"]; s = r["status"]; n = r["nick"]
        if d not in out:
            out[d] = {k: [] for k in ("full","am","pm","eve","off")}
        if s in out[d]:
            out[d][s].append(n)

    # 보기 좋게 정렬
    for d in out:
        for k in out[d]:
            out[d][k] = sorted(out[d][k])
    return out

# ---------- Itinerary CRUD ----------
def list_items(room_id:str, day:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT * FROM itinerary_items
                   WHERE room_id=? AND day=? ORDER BY position ASC""",
                (room_id, day))
    rows = cur.fetchall(); conn.close(); return rows

def add_item(room_id:str, day:str, name:str, category:str,
             lat=None, lon=None, budget:float=0.0,
             start_time:str=None, end_time:str=None,
             is_anchor:bool=False, notes:str=None, created_by:int=None):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(position),0)+1 FROM itinerary_items WHERE room_id=? AND day=?", (room_id, day))
    pos = cur.fetchone()[0]
    cur.execute("""INSERT INTO itinerary_items
        (room_id, day, position, name, category, lat, lon, budget, start_time, end_time, is_anchor, notes, created_by, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (room_id, day, pos, name, category, lat, lon, budget, start_time, end_time, 1 if is_anchor else 0, notes, created_by, dt.datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def bulk_save_positions(room_id:str, day:str, items:list[dict]):
    """items: [{'id':..,'position':..,'budget':..,'start_time':..,'end_time':..,'category':..,'name':..}]"""
    conn = get_conn(); cur = conn.cursor()
    for it in items:
        cur.execute("""UPDATE itinerary_items
            SET position=?, budget=?, start_time=?, end_time=?, category=?, name=?
            WHERE id=? AND room_id=? AND day=?""",
            (int(it["position"]), float(it.get("budget",0)), it.get("start_time"), it.get("end_time"),
             it.get("category","기타"), it.get("name"), int(it["id"]), room_id, day))
    conn.commit(); conn.close()

def delete_item(item_id:int, room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM itinerary_items WHERE id=? AND room_id=?", (item_id, room_id))
    conn.commit(); conn.close()

# ---------- Expenses ----------
def add_expense(room_id:str, day:str, place:str, payer_id:int, amount:float, memo:str=None):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO expenses(room_id,day,place,payer_id,amount,memo,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (room_id, day, place, payer_id, amount, memo, dt.datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def list_expenses(room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT e.*, u.name AS payer_name, u.nickname AS payer_nick
                   FROM expenses e JOIN users u ON u.id=e.payer_id
                   WHERE e.room_id=? ORDER BY e.created_at DESC""", (room_id,))
    rows = cur.fetchall(); conn.close(); return rows

def delete_expense(expense_id:int, room_id:str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=? AND room_id=?", (expense_id, room_id))
    conn.commit(); conn.close()

def settle_transfers(room_id:str):
    """최소 이체 횟수 정산(균등 분배). 결과: [{'from':..,'to':..,'amount':..}]"""
    exps = list_expenses(room_id)
    if not exps: return [], 0.0
    # 멤버
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT u.id,u.name,u.nickname FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.room_id=?", (room_id,))
    members = cur.fetchall(); conn.close()
    ids = [m["id"] for m in members]
    n = len(ids)
    total = sum(e["amount"] for e in exps)
    share = total / max(n,1)

    bal = {uid: -share for uid in ids}  # 각자 내야 할 금액(음수)
    for e in exps:
        bal[e["payer_id"]] += e["amount"]

    debtors  = [[uid, -amt] for uid,amt in bal.items() if amt < -1e-9]
    creditors= [[uid,  amt] for uid,amt in bal.items() if amt >  1e-9]
    debtors.sort(key=lambda x:x[1], reverse=True)
    creditors.sort(key=lambda x:x[1], reverse=True)

    transfers=[]
    i=j=0
    while i<len(debtors) and j<len(creditors):
        duid, d = debtors[i]; cuid, c = creditors[j]
        x = min(d,c)
        transfers.append({"from":duid, "to":cuid, "amount":round(x,0)})
        d -= x; c -= x
        if d<=1e-9: i+=1
        else: debtors[i][1]=d
        if c<=1e-9: j+=1
        else: creditors[j][1]=c
    return transfers, total