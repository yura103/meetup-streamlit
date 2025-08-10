import os, ssl, smtplib
from email.message import EmailMessage

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT   = os.getenv("SMTP_PORT")
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

try:
    import streamlit as st
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
    msg.set_content(f"""안녕하세요,

아래 토큰을 '비밀번호 재설정' 탭에 붙여넣고 새 비밀번호를 설정하세요.

토큰: {token}
(유효기간 30분)
""")
    try:
        port = int(SMTP_PORT)
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, port, context=context) as s:
                s.login(SMTP_USER, SMTP_PASSWORD); s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, port) as s:
                s.starttls(); s.login(SMTP_USER, SMTP_PASSWORD); s.send_message(msg)
        return True
    except Exception as e:
        print("SMTP 전송 실패:", e)
        return False