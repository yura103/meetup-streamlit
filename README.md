<h1 align="center">📅 YOUCHIN MeetUp Scheduler</h1>
<p align="center">
  <b>친구들과 일정 맞추기, 제출 현황 실시간 확인, 회원가입/로그인 지원</b><br>
  <i>Streamlit 기반 간편 일정 관리 웹앱</i>
</p>

<p align="center">
  <a href="https://meetup-app-nw8zmjuzw7sc88fh9sduxs.streamlit.app/">
    <img src="https://img.shields.io/badge/🚀%20Streamlit%20App-Go%20Now-blueviolet?style=for-the-badge">
  </a>
  <a href="https://github.com/yura103/meetup-streamlit">
    <img src="https://img.shields.io/github/stars/yura103/meetup-streamlit?style=for-the-badge&color=yellow">
  </a>
  <img src="https://img.shields.io/github/license/yura103/meetup-streamlit?style=for-the-badge&color=orange">
</p>

---

## ✨ 주요 기능
- **회원가입 / 로그인**
  - 이메일 + 닉네임 기반 계정 생성
  - 로그인 시 본인 방/초대받은 방 목록 확인
- **방 생성 / 참여**
  - 시작일, 종료일, 최소 연속일수, 최소 인원 설정
  - 초대 코드로 간편 참여
- **제출 현황 실시간 확인**
  - 방장이 전체 현황 열람 가능
  - 각 멤버 제출/수정/삭제 가능
  - 색상 안내:
    - 🖤 불가 (OFF)
    - 💚 일부 가능 (AM: 0.3 / PM: 0.1 / Night: 0.5)
    - 💜 하루 종일 가능 (FULL)
- **관리자 권한**
  - 멤버 삭제, 제출 삭제 가능
  - 방 삭제 가능

---

## 🛠 기술 스택
| 구분 | 기술 |
|------|------|
| Frontend & Backend | Streamlit |
| Database | SQLite3 |
| Deploy | Streamlit Cloud |
| Version Control | GitHub |

---

## 🚀 설치 및 실행
```bash
# Clone Repository
git clone https://github.com/yura103/meetup-streamlit.git
cd meetup-streamlit

# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run streamlit_app.py
