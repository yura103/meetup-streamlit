# auth.py
"""
인증 로직 레이어:
- 회원가입(중복 방지)
- 로그인(이메일 또는 닉네임)
- 비밀번호 재설정 토큰 발급/검증
"""
import database as DB

def register_user(email: str, name: str, nickname: str, password: str):
    if DB.email_exists(email):
        return False, "이미 가입된 이메일입니다."
    if nickname and DB.nickname_exists(nickname):
        return False, "이미 사용 중인 닉네임입니다."
    try:
        DB.create_user(email, name, nickname, password)
        return True, "가입 완료! 로그인해주세요."
    except ValueError as e:
        if str(e) == "email_taken":
            return False, "이미 가입된 이메일입니다."
        if str(e) == "nickname_taken":
            return False, "이미 사용 중인 닉네임입니다."
        return False, "회원가입 중 알 수 없는 오류가 발생했습니다."

def login_user(login_id: str, password: str):
    row = DB.get_user_by_login(login_id)
    if not row:
        return None, "존재하지 않는 계정입니다."
    if not DB.check_pw(password, row["pw_hash"]):
        return None, "비밀번호가 올바르지 않습니다."
    return dict(id=row["id"], name=row["name"], email=row["email"], nickname=row["nickname"]), "ok"

def issue_reset_token(email: str):
    token, status = DB.create_reset_token(email)
    if status == "no_user":
        return None, "해당 이메일의 사용자가 없습니다."
    return token, "ok"

def reset_password_with_token(token: str, new_password: str):
    row, status = DB.verify_reset_token(token)
    if status != "ok":
        return None, status
    DB.update_password(row["user_id"], new_password)
    DB.consume_reset_token(token)
    return True, "ok"