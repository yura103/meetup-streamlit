import database as DB
DB.init_db()
ok = DB.grant_admin_by_email("yura4007@naver.com")
print("granted:", ok)