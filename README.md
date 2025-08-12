<h1 align="center">📅 YOUCHIN MeetUp Scheduler</h1>
<p align="center">
  <b>친구들이랑 약속 날짜 쉽게! 제출 현황 실시간! 호스트 관리까지!</b><br>
  <i>Streamlit 기반 가벼운 일정 조율 웹앱</i>
</p>

<p align="center">
  <a href="https://meetup-app-youchin.streamlit.app/">
    <img src="https://img.shields.io/badge/🚀%20Open%20the%20App-Streamlit-blueviolet?style=for-the-badge">
  </a>
</p>

---

## ✨ 주요 기능
#### 👥 회원 관리
회원가입 / 로그인: 이메일 + 닉네임 기반, 중복 가입 방지

비밀번호 찾기: 이메일 재설정 토큰 발송 (SMTP: .env 또는 Streamlit Secrets)

#### 📅 일정 조율
방 생성 / 참여: 기간, 최소 연속 일수, 쿼럼 충족치 설정 (AM=0.3, PM=0.1, EVE=0.5, FULL=1.0)

내 달력 입력: 날짜별 가능 시간 선택 (오전/오후/저녁/종일)
제출 현황 실시간 확인: 제출 완료 / 대기자 표시
추천 Top-3 일정: 연속 가능 일수 + 점수 기반 추천 + 쿼럼 충족 여부

#### 📍 계획 & 동선
날짜별 계획표 작성 (순서, 시간, 카테고리, 장소, 예산)
동선 지도 자동 표시

#### 💰 정산
날짜별 지출 내역 입력 (장소, 결제자, 금액, 메모)
총 지출 금액 및 1인당 금액 자동 계산
최소 이체 횟수를 고려한 이체 추천 목록 제공


## 🛠 Tech
- Streamlit, SQLite, pandas
- Auth: bcrypt + 토큰 기반 비번 재설정
- Email: SMTP (Streamlit Secrets / .env)

## ⚙️ 로컬 실행
```bash
pip install -r requirements.txt
# (옵션) .env 작성: SMTP_SERVER/PORT/USER/PASSWORD
streamlit run streamlit_app.py
