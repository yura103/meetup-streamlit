# email_utils.py
"""
비밀번호 재설정 토큰을 이메일로 보내는 모듈.
우선순위:
1) Streamlit Cloud Secrets (단일 키 방식)
2) .env/OS 환경변수
둘 다 없으면 False 반환 (데모 모드: 토큰을 UI에 바로 표시)
"""
import os, ssl, smtplib
from email.message import EmailMessage

# .env 지원
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Streamlit Secrets 시도
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT   = os.getenv("SMTP_PORT")
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

try:
    import streamlit as st
    # st.secrets가 있으면 덮어쓰기
    if hasattr(st, "secrets"):
        SMTP_SERVER = st.secrets.get("SMTP_SERVER", SMTP_SERVER)
        SMTP_PORT   = st.secrets.get("SMTP_PORT", SMTP_PORT)
        SMTP_USER   = st.secrets.get("SMTP_USER", SMTP_USER)
        SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", SMTP_PASSWORD)
except Exception:
    pass

def send_reset_email(to_email: str, token: str) -> bool:
    if not (SMTP_SERVER and SMTP_PORT and SMTP_USER and SMTP_PASSWORD):
        return False
    msg = EmailMessage()
    msg["Subject"] = "비밀번호 재설정 안내"
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg.set_content(f"""
안녕하세요,

아래 토큰을 앱의 '비밀번호 재설정' 탭에 붙여넣고 새 비밀번호를 설정하세요.

토큰: {token}
(유효기간 30분)

감사합니다.
""")
    try:
        port = int(SMTP_PORT)
        # 587 → STARTTLS / 465 → SSL
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, port, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, port) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        print("SMTP 전송 실패:", e)
        return False