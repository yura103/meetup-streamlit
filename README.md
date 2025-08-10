<h1 align="center">📅 YOUCHIN MeetUp Scheduler</h1>
<p align="center">
  <b>친구들이랑 약속 날짜 쉽게! 제출 현황 실시간! 호스트 관리까지!</b><br>
  <i>Streamlit 기반 가벼운 일정 조율 웹앱</i>
</p>

<p align="center">
  <a href="https://meetup-app-nw8zmjuzw7sc88fh9sduxs.streamlit.app">
    <img src="https://img.shields.io/badge/🚀%20Open%20the%20App-Streamlit-blueviolet?style=for-the-badge">
  </a>
</p>

---

## ✨ 기능
- **회원가입/로그인**: 이메일+닉네임, 중복 가입 방지
- **비밀번호 찾기**: 이메일로 재설정 토큰 발송 (SMTP: Secrets 또는 .env)
- **방 생성/참여**: 기간·최소 연속일수·쿼럼·가중치(AM=0.3, PM=0.1, EVE=0.5, FULL=1.0)
- **제출 현황 실시간**: 호스트 멤버 관리(초대/삭제/설정 저장/방 삭제)
- **추천 Top-3**: 연속 min_days 창에서 가중치 합산 + 쿼럼 충족 여부

## 🛠 Tech
- Streamlit, SQLite, pandas
- Auth: bcrypt + 토큰 기반 비번 재설정
- Email: SMTP (Streamlit Secrets / .env)

## ⚙️ 로컬 실행
```bash
pip install -r requirements.txt
# (옵션) .env 작성: SMTP_SERVER/PORT/USER/PASSWORD
streamlit run streamlit_app.py