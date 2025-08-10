# streamlit_app.py
import streamlit as st, pandas as pd, datetime as dt
from db import init_db, get_user_by_email, create_user, check_pw, get_user, \
               create_room, list_my_rooms, get_room, invite_user_by_email, \
               upsert_availability, get_my_availability, clear_my_availability, \
               day_aggregate, remove_member, delete_room, update_room, \
               set_submitted, all_submitted
from planner_core import best_windows

st.set_page_config(page_title="친구 약속 잡기", layout="wide")
init_db()

# ---------- 스타일/색 ----------
COLOR = {
    "off": {"bg":"#000000","fg":"#FFFFFF","label":"불가"},
    "am":  {"bg":"#FFD54F","fg":"#000000","label":"오전(0.3)"},   # 노랑
    "pm":  {"bg":"#C6FF00","fg":"#000000","label":"점심(0.1)"},   # 연두
    "eve": {"bg":"#26C6DA","fg":"#000000","label":"저녁(0.5)"},   # 청록
    "full":{"bg":"#B038FF","fg":"#FFFFFF","label":"하루(1.0)"},   # 보라
}
STATUS_OPTIONS = ["off","am","pm","eve","full"]

def badge(status, text=None):
    c = COLOR[status]; t = text or c["label"]
    return f'<span style="background:{c["bg"]};color:{c["fg"]};padding:4px 8px;border-radius:8px;">{t}</span>'

def legend():
    cols = st.columns(5)
    for status, col in zip(STATUS_OPTIONS, cols):
        with col: st.markdown(badge(status), unsafe_allow_html=True)
    st.caption("색상 의미: 불가=검정 / 오전=노랑 / 점심=연두 / 저녁=청록 / 하루=보라")

# ---------- Auth ----------
def logout():
    for k in ("user_id","user_name","user_email","page","room_id"): st.session_state.pop(k, None)

def require_login():
    if "user_id" not in st.session_state:
        st.experimental_rerun()

def login_ui():
    st.header("로그인 / 회원가입")
    tab1, tab2 = st.tabs(["로그인", "회원가입"])

    with tab1:
        email = st.text_input("이메일")
        pw = st.text_input("비밀번호", type="password")
        if st.button("로그인"):
            row = get_user_by_email(email)
            if not row or not check_pw(pw, row["pw_hash"]):
                st.error("이메일 또는 비밀번호가 올바르지 않습니다.")
            else:
                st.session_state.update(user_id=row["id"], user_name=row["name"], user_email=row["email"], page="dashboard")
                st.experimental_rerun()

    with tab2:
        name = st.text_input("이름")
        email2 = st.text_input("이메일(회원가입)")
        pw2 = st.text_input("비밀번호(6자 이상)", type="password")
        if st.button("회원가입"):
            if len(name.strip())<1: st.error("이름을 입력해주세요."); return
            if len(pw2) < 6: st.error("비밀번호는 6자 이상"); return
            if get_user_by_email(email2): st.error("이미 가입된 이메일"); return
            create_user(email2, name, pw2)
            st.success("가입 완료! 로그인해주세요.")

# ---------- Dashboard ----------
def dashboard():
    require_login()
    st.header(f"안녕, {st.session_state['user_name']}님 👋")
    if st.button("로그아웃"): logout(); st.experimental_rerun()

    st.subheader("내 방")
    rows = list_my_rooms(st.session_state["user_id"])
    if not rows:
        st.info("아직 방이 없어요. 아래에서 새로 만들어보세요!")
    else:
        for r in rows:
            col1,col2,col3,col4 = st.columns([3,3,2,2])
            with col1: st.write(f"**{r['title']}**  (`{r['id']}`)")
            with col2: st.caption(f"{r['start']} ~ {r['end']} / 최소{r['min_days']}일 / 쿼럼{r['quorum']}")
            role = "👑 소유자" if r["role"]=="owner" else "👥 멤버"
            sub  = "✅ 제출" if r["submitted"] else "⏳ 미제출"
            with col3: st.write(role + " · " + sub)
            with col4:
                if st.button("입장", key=f"enter_{r['id']}"):
                    st.session_state["room_id"]=r["id"]; st.session_state["page"]="room"; st.experimental_rerun()

    st.markdown("---")
    st.subheader("방 만들기")
    with st.form("create_room_form"):
        title = st.text_input("방 제목", value="우리 약속")
        colA,colB = st.columns(2)
        with colA: start = st.date_input("시작", value=dt.date.today())
        with colB: end   = st.date_input("끝", value=dt.date.today()+dt.timedelta(days=14))
        colC,colD,colE = st.columns(3)
        with colC: min_days = st.number_input("최소 연속 일수", 1, 30, 2)
        with colD: quorum   = st.number_input("일자별 최소 모임 인원", 1, 100, 2)
        with colE: wfull    = st.number_input("가중치: 하루", 0.0, 2.0, 1.0, 0.1)
        colF,colG,colH = st.columns(3)
        with colF: wam = st.number_input("가중치: 오전", 0.0, 1.0, 0.3, 0.1)
        with colG: wpm = st.number_input("가중치: 점심", 0.0, 1.0, 0.1, 0.1)
        with colH: wev = st.number_input("가중치: 저녁", 0.0, 1.0, 0.5, 0.1)
        submitted = st.form_submit_button("방 생성")
        if submitted:
            rid = create_room(st.session_state["user_id"], title, start.isoformat(), end.isoformat(),
                              int(min_days), int(quorum), wfull, wam, wpm, wev)
            st.success(f"방 생성! 코드: **{rid}**")
            st.experimental_rerun()

# ---------- Room ----------
def room_page():
    require_login()
    rid = st.session_state.get("room_id")
    room, members = get_room(rid)
    if not room:
        st.error("방이 존재하지 않습니다.")
        st.session_state["page"]="dashboard"; st.session_state.pop("room_id",None); st.experimental_rerun()
        return

    is_owner = (room["owner_id"] == st.session_state["user_id"])

    st.header(f"방: {room['title']}  ({rid})")
    st.caption(f"{room['start']} ~ {room['end']} / 최소{room['min_days']}일 / 쿼럼{room['quorum']}")
    legend()

    # ----- owner tools -----
    if is_owner:
        with st.expander("👑 방 관리 (소유자 전용)", expanded=False):
            c1,c2,c3 = st.columns(3)
            with c1: new_title = st.text_input("제목", value=room["title"])
            with c2: start = st.date_input("시작", dt.date.fromisoformat(room["start"]))
            with c3: end   = st.date_input("끝", dt.date.fromisoformat(room["end"]))
            c4,c5,c6,c7 = st.columns(4)
            with c4: min_days = st.number_input("최소 연속 일수", 1, 30, room["min_days"])
            with c5: quorum   = st.number_input("일자별 최소 인원", 1, 100, room["quorum"])
            with c6: wfull    = st.number_input("가중치 하루", 0.0,2.0, float(room["w_full"]),0.1)
            with c7: pass
            c8,c9,c10 = st.columns(3)
            with c8: wam = st.number_input("가중치 오전", 0.0,1.0, float(room["w_am"]),0.1)
            with c9: wpm = st.number_input("가중치 점심",0.0,1.0, float(room["w_pm"]),0.1)
            with c10: wev= st.number_input("가중치 저녁",0.0,1.0, float(room["w_eve"]),0.1)

            b1,b2,b3 = st.columns(3)
            with b1:
                if st.button("설정 저장"):
                    ok = update_room(room["owner_id"], rid,
                                     title=new_title, start=start.isoformat(), end=end.isoformat(),
                                     min_days=int(min_days), quorum=int(quorum),
                                     w_full=wfull, w_am=wam, w_pm=wpm, w_eve=wev)
                    st.success("저장 완료" if ok else "변경 없음")
                    st.experimental_rerun()
            with b2:
                inv_email = st.text_input("초대 이메일", key="invite_email")
                if st.button("초대하기"):
                    if not inv_email.strip():
                        st.error("이메일을 입력하세요.")
                    else:
                        ok,msg = invite_user_by_email(rid, inv_email.strip())
                        st.success(msg) if ok else st.error(msg)
                        st.experimental_rerun()
            with b3:
                if st.button("⚠️ 방 삭제", type="secondary"):
                    delete_room(rid, room["owner_id"])
                    st.success("방을 삭제했습니다.")
                    st.session_state["page"]="dashboard"; st.session_state.pop("room_id",None); st.experimental_rerun()

        st.markdown("#### 멤버 목록")
        tbl = []
        for m in members:
            tbl.append({"이름": m["name"], "이메일": m["email"], "역할": m["role"], "제출": "✅" if m["submitted"] else "⏳"})
        st.dataframe(pd.DataFrame(tbl), hide_index=True, use_container_width=True)

        # 멤버 제거
        options = ["(선택)"] + [f'{m["name"]} ({m["email"]})' for m in members if m["id"] != room["owner_id"]]
        pick = st.selectbox("멤버 제거", options)
        if pick != "(선택)":
            target_email = pick.split("(")[-1].replace(")","").strip()
            target = next((m for m in members if m["email"]==target_email), None)
            if target and st.button("선택 멤버 제거"):
                remove_member(rid, target["id"]); st.success("제거 완료"); st.experimental_rerun()

    # ----- 내 입력/제출 -----
    st.markdown("---")
    st.subheader("내 달력 입력")
    my_av = get_my_availability(st.session_state["user_id"], rid)

    # 데이터프레임 편집기
    days = []
    d0 = dt.date.fromisoformat(room["start"]); d1 = dt.date.fromisoformat(room["end"])
    cur = d0
    while cur <= d1:
        ds = cur.isoformat()
        days.append({"날짜": ds, "상태": my_av.get(ds, "off")})
        cur += dt.timedelta(days=1)
    df = pd.DataFrame(days)

    # 선택지 레이블로 보기 좋게
    label_map = {"off":"불가(검정)","am":"오전(노랑)","pm":"점심(연두)","eve":"저녁(청록)","full":"하루(보라)"}
    inv_label = {v:k for k,v in label_map.items()}
    df["상태(선택)"] = [label_map.get(v, "불가(검정)") for v in df["상태"]]

    edited = st.data_editor(
        df[["날짜","상태(선택)"]],
        hide_index=True,
        column_config={
            "날짜": st.column_config.TextColumn(disabled=True),
            "상태(선택)": st.column_config.SelectboxColumn(options=list(label_map.values()))
        },
        use_container_width=True,
    )
    # 역매핑
    edited["상태"] = [inv_label[x] for x in edited["상태(선택)"]]
    payload = {row["날짜"]: row["상태"] for _, row in edited.iterrows()}

    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("저장"):
            upsert_availability(st.session_state["user_id"], rid, payload)
            set_submitted(st.session_state["user_id"], rid, False)
            st.success("저장 완료(미제출 상태)"); st.experimental_rerun()
    with c2:
        if st.button("제출(Submit)"):
            upsert_availability(st.session_state["user_id"], rid, payload)
            set_submitted(st.session_state["user_id"], rid, True)
            st.success("제출 완료"); st.experimental_rerun()
    with c3:
        if st.button("내 입력 삭제"):
            clear_my_availability(st.session_state["user_id"], rid)
            set_submitted(st.session_state["user_id"], rid, False)
            st.success("입력을 비웠습니다."); st.experimental_rerun()

    # 제출 현황/뱃지
    st.markdown("#### 제출 현황")
    submitted = [m["name"] for m in members if m["submitted"]]
    pending   = [m["name"] for m in members if not m["submitted"]]
    badge_simple = lambda t: f'<span style="background:#eee;padding:4px 8px;border-radius:999px;margin-right:6px">{t}</span>'
    st.markdown("**제출 완료:** " + (" ".join(badge_simple(n) for n in submitted) or "없음"), unsafe_allow_html=True)
    st.markdown("**제출 대기:** " + (" ".join(badge_simple(n) for n in pending) or "없음"), unsafe_allow_html=True)

    # ----- 집계/추천 -----
    st.markdown("---")
    st.subheader("집계 및 추천")
    room_row, days_list, agg, weights = day_aggregate(rid)
    df_agg = pd.DataFrame([
        {"date": d, "full": agg[d]["full"], "am": agg[d]["am"], "pm": agg[d]["pm"], "eve": agg[d]["eve"],
         "score": round(agg[d]["score"],2),
         "quorum_ok": "✅" if (agg[d]["full"]+agg[d]["am"]+agg[d]["pm"]+agg[d]["eve"])>=room_row["quorum"] else "❌"}
        for d in days_list
    ])
    st.dataframe(df_agg, use_container_width=True, hide_index=True)

    topk = best_windows(days_list, agg, int(room_row["min_days"]), int(room_row["quorum"]))
    if topk:
        st.markdown("### ⭐ 추천 Top-3 연속 구간")
        for i,win in enumerate(topk, 1):
            feas = "충족" if win["feasible"] else "⚠️ 최소 인원 미충족 포함"
            st.write(f"**#{i} | {win['days'][0]} ~ {win['days'][-1]} | 점수 {win['score']:.2f} | {feas}**")
    else:
        st.info("추천할 구간이 아직 없어요. 인원 입력을 더 받아보세요.")

    # 최종 알림
    if all_submitted(rid):
        st.success("모든 인원이 제출 완료! 위 추천 구간을 참고해 최종 확정하세요 ✅")

# ---------- Router ----------
def router():
    page = st.session_state.get("page", "auth")
    if "user_id" not in st.session_state:
        login_ui()
    else:
        if page == "dashboard":
            dashboard()
        elif page == "room":
            room_page()
        else:
            st.session_state["page"]="dashboard"; dashboard()

router()
