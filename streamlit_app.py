# streamlit_app.py
import streamlit as st
import pandas as pd
import datetime as dt

import db as DB
from planner_core import best_windows

# 페이지 설정
st.set_page_config(page_title="친구 약속 잡기", layout="wide")
DB.init_db()

# rerun 함수 (버전 호환)
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# ------------------ 로그인 & 회원가입 ------------------
def login_ui():
    st.header("로그인")
    email = st.text_input("이메일")
    password = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        user = DB.get_user_by_login(email, password)
        if user:
            st.session_state.user = user
            st.success(f"{user['nickname']}님 환영합니다!")
            _rerun()
        else:
            st.error("이메일 또는 비밀번호가 올바르지 않습니다.")

    st.markdown("---")
    st.subheader("회원가입")
    reg_email = st.text_input("가입 이메일")
    reg_nickname = st.text_input("닉네임")
    reg_pw = st.text_input("가입 비밀번호", type="password")
    if st.button("회원가입"):
        if DB.create_user(reg_email, reg_pw, reg_nickname):
            st.success("회원가입 성공! 로그인 해주세요.")
        else:
            st.error("이미 존재하는 이메일/닉네임입니다.")

# ------------------ 대시보드 ------------------
def dashboard():
    st.title(f"📅 {st.session_state.user['nickname']}님의 약속방")
    tabs = st.tabs(["내 방 목록", "방 만들기", "참여하기"])

    # 내 방 목록
    with tabs[0]:
        host_rooms = DB.get_rooms_by_host(st.session_state.user['id'])
        invited_rooms = DB.get_rooms_by_member(st.session_state.user['id'])
        st.subheader("내가 만든 방")
        for r in host_rooms:
            st.write(f"▶ {r['name']} | 코드: {r['code']}")
            if st.button(f"방 입장 ({r['code']})", key=f"host_{r['code']}"):
                st.session_state.room_code = r['code']
                _rerun()
        st.subheader("참여중인 방")
        for r in invited_rooms:
            st.write(f"▶ {r['name']} | 코드: {r['code']}")
            if st.button(f"방 입장 ({r['code']})", key=f"mem_{r['code']}"):
                st.session_state.room_code = r['code']
                _rerun()

    # 방 만들기
    with tabs[1]:
        name = st.text_input("방 이름")
        start = st.date_input("시작일")
        end = st.date_input("종료일")
        min_days = st.number_input("최소 연속일수", 1, 10, 2)
        min_people = st.number_input("최소 인원", 1, 20, 2)
        if st.button("방 만들기"):
            code = DB.create_room(name, st.session_state.user['id'], start, end, min_days, min_people)
            st.success(f"방 생성 완료! 코드: {code}")

    # 방 참여하기
    with tabs[2]:
        code = st.text_input("방 코드 입력")
        if st.button("참여"):
            if DB.join_room(code, st.session_state.user['id']):
                st.success("방 참여 완료!")
            else:
                st.error("잘못된 코드이거나 이미 참여중입니다.")

# ------------------ 방 페이지 ------------------
def room_page():
    code = st.session_state.room_code
    room = DB.get_room_by_code(code)
    members = DB.get_room_members(code)
    is_host = (room['host_id'] == st.session_state.user['id'])

    st.header(f"방: {room['name']} | 코드: {code}")
    st.write(f"{room['start_date']} ~ {room['end_date']} / 최소 연속일수 {room['min_days']}일 / 최소 인원 {room['min_people']}명")
    st.write(f"인원 {len(members)}/{room['min_people']}")

    # 호스트 기능
    if is_host:
        st.subheader("👑 호스트 전용 기능")
        if st.button("방 삭제"):
            DB.delete_room(code)
            del st.session_state.room_code
            st.success("방이 삭제되었습니다.")
            _rerun()

    # 제출 현황
    st.subheader("제출 현황")
    submissions = DB.get_submissions(code)
    st.write(submissions)

    # 내 제출 달력
    st.subheader("내 달력 제출")
    dates = pd.date_range(room['start_date'], room['end_date'])
    selections = {}
    for d in dates:
        sel = st.selectbox(f"{d.date()} 상태", ["불가", "오전", "점심", "저녁", "가능"], key=str(d))
        selections[str(d.date())] = sel
    if st.button("제출"):
        DB.save_submission(code, st.session_state.user['id'], selections)
        st.success("제출 완료!")
        _rerun()

# ------------------ 라우터 ------------------
def router():
    if "user" not in st.session_state:
        login_ui()
    elif "room_code" not in st.session_state:
        dashboard()
    else:
        room_page()

# ------------------ 실행 ------------------
router()