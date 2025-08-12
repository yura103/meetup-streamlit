import os, sqlite3, database as DB

print('DB_PATH=', DB.DB_PATH, 'exists=', os.path.exists(DB.DB_PATH))
con = sqlite3.connect(DB.DB_PATH)
cur = con.cursor()
print('users_count=', cur.execute('SELECT COUNT(*) FROM users').fetchone()[0])
print('sample_users=', cur.execute('SELECT id,email,name,nickname FROM users LIMIT 5').fetchall())
print('has_site_admins_tbl=', cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="site_admins"').fetchone() is not None)

if cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="site_admins"').fetchone():
    print('site_admins=', cur.execute('SELECT * FROM site_admins').fetchall())
else:
    print('site_admins= N/A')

con.close()