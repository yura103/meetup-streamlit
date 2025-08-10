import streamlit as st, pandas as pd, datetime as dt
import database as DB
import auth as AUTH
from planner_core import best_windows, optimize_route
from email_utils import send_reset_email
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim

st.set_page_config(page_title="친구 약속 잡기", layout="wide")
DB.init_db()

def _rerun():
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()

COLOR = {
    "off":  {"bg":"#000000","fg":"#FFFFFF","label":"불가(0.0)"},
    "am":   {"bg":"#FFD54F","fg":"#000000","label":"7시간 이상(0.7)"},
    "pm":   {"bg":"#C6FF00","fg":"#000000","label":"5시간 이상(0.5)"},
    "eve":  {"bg":"#26C6DA","fg":"#000000","label":"3시간 이상 / 잘 모르겠다(0.4)"},
    "full": {"bg":"#B038FF","fg":"#FFFFFF","label":"하루종일(1.0)"},
}
STATUS_OPTIONS = ["off","am","pm","eve","full"]

def badge(status, text=None):
    c = COLOR[status]; t = text or c["label"]
    return f'<span style="background:{c["bg"]};color:{c["fg"]};padding:4px 8px;border-radius:8px;">{t}</span>'

def legend():
    cols = st.columns(5)
    for status, col in zip(STATUS_OPTIONS, cols):
        with col: st.markdown(badge(status), unsafe_allow_html=True)
    st.caption("색상: 불가=검정 / 7시간=노랑 / 5시간=연두 / 3시간=청록 / 하루종일=보라")

# ---------------- Auth ----------------
def login_ui():
    st.header("로그인 / 회원가입 / 비밀번호 재설정")
    tabs = st.tabs(["로그인", "회원가입", "비밀번호 찾기", "비밀번호 재설정"])

    with tabs[0]:
        login_id = st.text_input("이메일 또는 닉네임")
        pw = st.text_input("비밀번호", type="password")
        if st.button("로그인"):
            user, msg = AUTH.login_user(login_id, pw)
            if not user: st.error(msg)
            else:
                st.session_state.update(
                    user_id=user["id"], user_name=user["name"],
                    user_email=user["email"], user_nick=user["nickname"] or user["name"],
                    page="dashboard"
                ); _rerun()

    with tabs[1]:
        name = st.text_input("이름(실명/표시명)")
        nickname = st.text_input("닉네임(고유값)")
        email2 = st.text_input("이메일")
        pw2 = st.text_input("비밀번호(6자 이상)", type="password")
        if st.button("회원가입"):
            if len(name.strip())<1: st.error("이름을 입력하세요."); st.stop()
            if len(nickname.strip())<2: st.error("닉네임을 2자 이상 입력하세요."); st.stop()
            if len(pw2)<6: st.error("비밀번호는 6자 이상"); st.stop()
            ok,msg = AUTH.register_user(email2, name, nickname, pw2)
            st.success(msg) if ok else st.error(msg)

    with tabs[2]:
        fp_email = st.text_input("가입 이메일")
        if st.button("재설정 토큰 보내기"):
            token, status = AUTH.issue_reset_token(fp_email)
            if status!="ok":
                st.error("해당 이메일의 사용자가 없습니다.")
            else:
                if send_reset_email(fp_email, token):
                    st.success("이메일을 확인하세요! (30분 이내)")
                else:
                    st.info("SMTP 미설정이라 토큰을 아래에 표시합니다.")
                    st.code(token, language="text")

    with tabs[3]:
        token_in = st.text_input("재설정 토큰")
        new_pw = st.text_input("새 비밀번호", type="password")
        if st.button("비밀번호 재설정"):
            if len(new_pw)<6: st.error("비밀번호는 6자 이상"); st.stop()
            ok, status = AUTH.reset_password_with_token(token_in, new_pw)
            if status=="ok": st.success("변경되었습니다. 로그인하세요.")
            else:
                msg = {"not_found":"토큰이 올바르지 않아요.","used":"이미 사용됨","expired":"만료됨"}.get(status,"토큰 오류")
                st.error(msg)

def logout():
    for k in ("user_id","user_name","user_email","user_nick","page","room_id"): st.session_state.pop(k, None)

def require_login():
    if "user_id" not in st.session_state:
        st.session_state["page"]="auth"; _rerun()

# ---------------- Dashboard ----------------
def dashboard():
    require_login()
    disp = st.session_state.get("user_nick") or st.session_state.get("user_name")
    st.header(f"안녕, {disp}님 👋")
    if st.button("로그아웃"): logout(); _rerun()

    st.subheader("내 방")
    rows = DB.list_my_rooms(st.session_state["user_id"])
    if not rows: st.info("아직 방이 없어요. 아래에서 새로 만들어보세요!")
    else:
        for r in rows:
            col1,col2,col3,col4 = st.columns([3,3,2,2])
            with col1: st.write(f"**{r['title']}**  (`{r['id']}`)")
            with col2: st.caption(f"{r['start']} ~ {r['end']} / 최소{r['min_days']}일 / 쿼럼{r['quorum']}")
            role = "👑 소유자" if r["role"]=="owner" else "👥 멤버"
            sub  = "✅ 제출" if r["submitted"] else "⏳ 미제출"
            with col3: st.write(role+" · "+sub)
            with col4:
                if st.button("입장", key=f"enter_{r['id']}"):
                    st.session_state["room_id"]=r["id"]; st.session_state["page"]="room"; _rerun()

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
        with colE: wfull    = st.number_input("가중치: 하루종일", 0.0, 2.0, 1.0, 0.1)
        colF,colG,colH = st.columns(3)
        with colF: wam = st.number_input("가중치: 7시간 이상", 0.0, 1.0, 0.7, 0.1)
        with colG: wpm = st.number_input("가중치: 5시간 이상", 0.0, 1.0, 0.5, 0.1)
        with colH: wev = st.number_input("가중치: 3시간 이상/잘 모르겠다", 0.0, 1.0, 0.3, 0.1)
        submitted = st.form_submit_button("방 생성")
        if submitted:
            rid = DB.create_room(st.session_state["user_id"], title, start.isoformat(), end.isoformat(),
                                 int(min_days), int(quorum), wfull, wam, wpm, wev)
            st.success(f"방 생성! 코드: **{rid}**"); _rerun()

# ---------------- Room ----------------
def room_page():
    require_login()
    rid = st.session_state.get("room_id")
    if not rid:
        st.session_state["page"] = "dashboard"; _rerun(); return

    room, members = DB.get_room(rid)
    if not room:
        st.error("방이 존재하지 않습니다.")
        st.session_state["page"] = "dashboard"
        st.session_state.pop("room_id", None)
        _rerun(); return

    is_owner = (room["owner_id"] == st.session_state["user_id"])

    # 헤더 + 레전드
    st.header(f"방: {room['title']} ({rid})")
    st.caption(f"{room['start']} ~ {room['end']} / 최소{room['min_days']}일 / 쿼럼{room['quorum']}")
    legend()

    # ---- 방장 관리 ----
    if is_owner:
        with st.expander("👑 방 관리", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1: new_title = st.text_input("제목", room["title"])
            with c2: start = st.date_input("시작", dt.date.fromisoformat(room["start"]))
            with c3: end   = st.date_input("끝",   dt.date.fromisoformat(room["end"]))
            c4, c5, c6, c7 = st.columns(4)
            with c4: min_days = st.number_input("최소 연속 일수", 1, 30, room["min_days"])
            with c5: quorum   = st.number_input("일자별 최소 인원", 1, 100, room["quorum"])
            with c6: wfull    = st.number_input("가중치: 하루종일", 0.0, 2.0, float(room["w_full"]), 0.1)
            with c7: pass
            c8, c9, c10 = st.columns(3)
            with c8:  wam = st.number_input("가중치: 7시간 이상", 0.0, 1.0, float(room["w_am"]), 0.1)
            with c9:  wpm = st.number_input("가중치: 5시간 이상", 0.0, 1.0, float(room["w_pm"]), 0.1)
            with c10: wev = st.number_input("가중치: 3시간 이상/모름", 0.0, 1.0, float(room["w_eve"]), 0.1)

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("설정 저장", key="owner_save"):
                    DB.update_room(
                        room["owner_id"], rid,
                        title=new_title, start=start.isoformat(), end=end.isoformat(),
                        min_days=int(min_days), quorum=int(quorum),
                        w_full=wfull, w_am=wam, w_pm=wpm, w_eve=wev
                    )
                    st.success("저장 완료"); _rerun()
            with b2:
                inv_email = st.text_input("초대 이메일", key="invite_email")
                if st.button("초대하기", key="invite_btn"):
                    email_str = (inv_email or "").strip()
                    if not email_str:
                        st.error("이메일을 입력하세요.")
                    else:
                        ok, msg = DB.invite_user_by_email(rid, email_str)
                        (st.success if ok else st.error)(str(msg)); _rerun()
            with b3:
                if st.button("⚠️ 방 삭제", type="secondary", key="room_delete"):
                    DB.delete_room(rid, room["owner_id"])
                    st.success("방 삭제 완료")
                    st.session_state["page"] = "dashboard"
                    st.session_state.pop("room_id", None)
                    _rerun()

        # 멤버 목록/제거
        st.markdown("#### 멤버 목록")
        st.dataframe(
            pd.DataFrame([{
                "이름": m["name"],
                "닉네임": (m["nickname"] or m["name"]),
                "이메일": m["email"],
                "역할": m["role"],
                "제출": "✅" if m["submitted"] else "⏳"
            } for m in members]),
            hide_index=True, use_container_width=True
        )
        options = ["(선택)"] + [
            f'{(m["nickname"] or m["name"])} ({m["email"]})'
            for m in members if m["id"] != room["owner_id"]
        ]
        pick = st.selectbox("멤버 제거", options, key="remove_pick")
        if pick != "(선택)":
            target_email = pick.split("(")[-1].replace(")","").strip()
            target = next((m for m in members if m["email"]==target_email), None)
            if target and st.button("선택 멤버 제거", key="remove_btn"):
                DB.remove_member(rid, target["id"]); st.success("제거 완료"); _rerun()

    # ---- 탭 구분 ----
    st.markdown("---")
    tab_time, tab_plan, tab_cost = st.tabs(["⏰ 시간/약속", "🗺️ 계획 & 동선 / 예산", "💳 정산"])

    # ========== ⏰ 시간/약속 ==========
    with tab_time:
        st.subheader("내 달력 입력")
        my_av = DB.get_my_availability(st.session_state["user_id"], rid)

        # 날짜 범위 → DataFrame
        days = []
        d0 = dt.date.fromisoformat(room["start"]); d1 = dt.date.fromisoformat(room["end"])
        cur = d0
        while cur <= d1:
            ds = cur.isoformat()
            days.append({"날짜": ds, "상태": my_av.get(ds, "off")})
            cur += dt.timedelta(days=1)
        df = pd.DataFrame(days)

        label_map = {
            "off":  "불가(0.0)",
            "am":   "7시간 이상(0.7)",
            "pm":   "5시간 이상(0.5)",
            "eve":  "3시간 이상 / 잘 모르겠다(0.4)",
            "full": "하루종일(1.0)"
        }
        inv_label = {v:k for k,v in label_map.items()}
        df["상태(선택)"] = [label_map.get(v, "불가(0.0)") for v in df["상태"]]

        edited = st.data_editor(
            df[["날짜","상태(선택)"]],
            hide_index=True,
            column_config={
                "날짜": st.column_config.TextColumn(disabled=True),
                "상태(선택)": st.column_config.SelectboxColumn(options=list(label_map.values()))
            },
            use_container_width=True,
            key="time_editor"
        )
        edited["상태"] = [inv_label[x] for x in edited["상태(선택)"]]
        payload = {row["날짜"]: row["상태"] for _, row in edited.iterrows()}

        c1,c2,c3 = st.columns(3)
        with c1:
            if st.button("저장", key="time_save"):
                DB.upsert_availability(st.session_state["user_id"], rid, payload)
                DB.set_submitted(st.session_state["user_id"], rid, False)
                st.success("저장 완료(미제출)"); _rerun()
        with c2:
            if st.button("제출(Submit)", key="time_submit"):
                DB.upsert_availability(st.session_state["user_id"], rid, payload)
                DB.set_submitted(st.session_state["user_id"], rid, True)
                st.success("제출 완료"); _rerun()
        with c3:
            if st.button("내 입력 삭제", key="time_clear"):
                DB.clear_my_availability(st.session_state["user_id"], rid)
                DB.set_submitted(st.session_state["user_id"], rid, False)
                st.success("입력을 비웠습니다."); _rerun()

        st.markdown("#### 제출 현황")
        submitted = [ (m["nickname"] or m["name"]) for m in members if m["submitted"]]
        pending   = [ (m["nickname"] or m["name"]) for m in members if not m["submitted"]]
        pill = lambda t: f'<span style="background:#eee;padding:4px 8px;border-radius:999px;margin-right:6px">{t}</span>'
        st.markdown("**제출 완료:** " + (" ".join(pill(n) for n in submitted) or "없음"), unsafe_allow_html=True)
        st.markdown("**제출 대기:** " + (" ".join(pill(n) for n in pending) or "없음"), unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("집계 및 추천")

        # ---- 이름 포함 집계 ----
        room_row, days_list, agg, weights = DB.day_aggregate(rid)
        names_by_day = DB.availability_names_by_day(rid)   # ★ 추가

        df_agg = pd.DataFrame([
            {
                "date": d,
                "full": agg[d]["full"], "am": agg[d]["am"], "pm": agg[d]["pm"], "eve": agg[d]["eve"],
                "score": round(agg[d]["score"],2),
                "quorum_ok": "✅" if (agg[d]["full"]+agg[d]["am"]+agg[d]["pm"]+agg[d]["eve"])>=room_row["quorum"] else "❌",
                "FULL(이름)": ", ".join(names_by_day.get(d, {}).get("full", [])),
                "AM(이름)":   ", ".join(names_by_day.get(d, {}).get("am", [])),
                "PM(이름)":   ", ".join(names_by_day.get(d, {}).get("pm", [])),
                "EVE(이름)":  ", ".join(names_by_day.get(d, {}).get("eve", [])),
            }
            for d in days_list
        ])
        st.dataframe(df_agg, use_container_width=True, hide_index=True)

        # 날짜 하나 골라서 뱃지로 보기
        def chip(txt):
            return f'<span style="background:#f5f5f5;border:1px solid #ddd;padding:2px 8px;border-radius:999px;margin-right:4px;display:inline-block">{txt}</span>'

        st.markdown("#### 날짜별 가능 멤버(뱃지)")
        pick_for_names = st.selectbox("날짜 선택", days_list, index=0, key="names_day_pick")
        nb = names_by_day.get(pick_for_names, {})
        for label, key in [("하루종일", "full"), ("7시간", "am"), ("5시간", "pm"), ("3시간/모름", "eve")]:
            chips = " ".join(chip(n) for n in nb.get(key, [])) or "(없음)"
            st.markdown(f"**{label}** · {chips}", unsafe_allow_html=True)

        # ---- TopK 연속 구간 + (신규) 겹치는 동일 점수 구간 묶기 ----
        topk = best_windows(days_list, agg, int(room_row["min_days"]), int(room_row["quorum"]))

        def _overlap(days_a, days_b):
            return bool(set(days_a) & set(days_b))

        def group_overlapping_windows(wins, tol=1e-6):
            groups = []
            for w in wins:
                placed = False
                for g in groups:
                    rep = g["rep"]
                    if abs(w["score"] - rep["score"]) < tol and _overlap(w["days"], rep["days"]):
                        g["variants"].append(w)
                        # 대표 선정: feasible 우선, 같으면 시작일 빠른 것
                        cand = rep
                        if (w["feasible"] and not rep["feasible"]) or \
                           (w["feasible"] == rep["feasible"] and w["days"][0] < rep["days"][0]):
                            cand = w
                        g["rep"] = cand
                        placed = True
                        break
                if not placed:
                    groups.append({"rep": w, "variants": [w]})
            # 대표 기준 정렬
            groups.sort(key=lambda g: (g["rep"]["days"][0], -g["rep"]["score"]))
            return groups

        collapse_same = st.toggle(
            "겹치는 동일 점수 구간 묶어서 보기",
            value=True,
            help="동일 점수이며 서로 겹치는 구간을 대표 1개 + 대안 목록으로 묶어 보여줘요."
        )

        def level_rank(s):
            return {"off":0, "eve":1, "pm":2, "am":3, "full":4}.get(s,0)

        def render_win(win):
            feas = "충족" if win["feasible"] else "⚠️ 최소 인원 미충족 포함"
            st.write(f"**{win['days'][0]} ~ {win['days'][-1]} | 점수 {win['score']:.2f} | {feas}**")
            # 구간 전체 가능 멤버 뱃지
            days_in_win = win["days"]
            sets_per_day = []
            for d in days_in_win:
                nb2 = names_by_day.get(d, {})
                eligible = set(nb2.get("full", [])) | set(nb2.get("am", [])) | set(nb2.get("pm", [])) | set(nb2.get("eve", []))
                sets_per_day.append(eligible)
            always_ok = set.intersection(*sets_per_day) if sets_per_day else set()

            lowest_status = {}
            for d in days_in_win:
                nb3 = names_by_day.get(d, {})
                for s in ("full","am","pm","eve"):
                    for name in nb3.get(s, []):
                        cur = lowest_status.get(name, "full")
                        lowest_status[name] = min(cur, s, key=lambda x: level_rank(x))

            chips = []
            for name in sorted(always_ok):
                tag = lowest_status.get(name, "eve")
                label = {"full":"하루종일", "am":"7시간", "pm":"5시간", "eve":"3시간/모름"}.get(tag, tag)
                chips.append(chip(f"{name} · {label}"))
            st.markdown("가능 멤버(구간 전체): " + (" ".join(chips) or "(없음)"), unsafe_allow_html=True)

        if topk:
            if collapse_same:
                groups = group_overlapping_windows(topk)
                st.markdown("### ⭐ 추천 구간 (겹치는 동일 점수는 묶어서)")
                for i, g in enumerate(groups[:3], 1):
                    st.write(f"**#{i} 대표 구간**")
                    render_win(g["rep"])
                    if len(g["variants"]) > 1:
                        with st.expander("같은 점수의 대안 구간 보기"):
                            for v in g["variants"]:
                                if v is g["rep"]:
                                    continue
                                st.caption(f"- {v['days'][0]} ~ {v['days'][-1]}  ·  {'충족' if v['feasible'] else '⚠️'}")
            else:
                st.markdown("### ⭐ 추천 Top-3 연속 구간")
                for i, win in enumerate(topk[:3], 1):
                    st.write(f"**#{i}**")
                    render_win(win)
        else:
            st.info("추천할 구간이 아직 없어요. 인원 입력을 더 받아보세요.")
        if DB.all_submitted(rid):
            st.success("모든 인원이 제출 완료! 위 추천 구간을 참고해 최종 확정하세요 ✅")

    # ========== 🗺️ 계획 & 동선 / 예산 ==========
    with tab_plan:
        left, right = st.columns([1.1, 1.2])

        # 날짜 선택
        days_options = pd.date_range(room["start"], room["end"]).strftime("%Y-%m-%d").tolist()
        pick_day = st.selectbox("날짜 선택", days_options, index=0, key="plan_day")

        # 좌: 계획표 + 검색/추가
        with left:
            st.subheader("계획표 (순서·시간·카테고리·장소·예산)")

            with st.expander("📍 장소 검색해서 추가", expanded=False):
                q = st.text_input("장소/주소 검색", key="plan_q")
                cA,cB,cC = st.columns([2,1,1])
                with cA: cat = st.selectbox("카테고리", ["식사","숙소","놀기","카페","쇼핑","기타"], key="plan_cat")
                with cB: bud = st.number_input("예산(원)", 0, step=1000, value=0, key="plan_budget")
                with cC: is_anchor = st.checkbox("숙소/고정", value=False, key="plan_anchor")
                if st.button("검색 & 추가", key="plan_add"):
                    if not q.strip():
                        st.error("검색어를 입력하세요.")
                    else:
                        try:
                            geoloc = Nominatim(user_agent="youchin").geocode(q)
                            lat, lon = (geoloc.latitude, geoloc.longitude) if geoloc else (None, None)
                        except Exception:
                            lat, lon = (None, None)
                        DB.add_item(rid, pick_day, q.strip(), cat, lat, lon, bud, None, None, is_anchor, None, st.session_state["user_id"])
                        st.success("추가됨"); _rerun()

            rows = DB.list_items(rid, pick_day)

            # 화면 표시용 연속 번호 추가
            table = []
            for r in rows:
                table.append({
                    "id": r["id"], "position": r["position"], "번호": 0,
                    "start_time": r["start_time"] or "", "end_time": r["end_time"] or "",
                    "category": r["category"], "name": r["name"],
                    "budget": float(r["budget"] or 0)
                })
            df_plan = pd.DataFrame(table)
            if not df_plan.empty:
                df_plan = df_plan.sort_values("position").reset_index(drop=True)
                df_plan["번호"] = range(1, len(df_plan)+1)

            if df_plan.empty:
                st.info("이 날짜의 계획이 없습니다. 위에서 장소를 검색/추가하세요.")
            else:
                edited = st.data_editor(
                    df_plan,
                    column_config={
                        "id": st.column_config.TextColumn("ID", disabled=True),
                        "번호": st.column_config.NumberColumn("번호(표시용)", disabled=True),
                        "position": st.column_config.NumberColumn("순서", min_value=1, step=1),
                        "start_time": st.column_config.TextColumn("시작", help="예: 10:00"),
                        "end_time": st.column_config.TextColumn("종료", help="예: 12:00"),
                        "category": st.column_config.SelectboxColumn("카테고리", options=["식사","숙소","놀기","카페","쇼핑","기타"]),
                        "name": st.column_config.TextColumn("장소"),
                        "budget": st.column_config.NumberColumn("예산(원)", step=1000),
                    },
                    hide_index=True, use_container_width=True, key="plan_editor"
                )

                d1, d2, d3 = st.columns(3)
                with d1:
                    if st.button("저장(계획)", key="plan_save"):
                        DB.bulk_save_positions(rid, pick_day, edited.to_dict("records"))
                        st.success("저장 완료"); _rerun()
                with d2:
                    if st.button("자동 동선 추천(순서 재배치)", key="plan_opt"):
                        items_for_route = [{
                            "id": r["id"], "lat": r["lat"], "lon": r["lon"], "is_anchor": r["is_anchor"]
                        } for r in DB.list_items(rid, pick_day)]
                        order_ids = optimize_route(items_for_route)
                        new_rows=[]; p=1
                        for oid in order_ids:
                            row = next(rr for rr in edited.to_dict("records") if rr["id"]==oid)
                            row["position"]=p; new_rows.append(row); p+=1
                        DB.bulk_save_positions(rid, pick_day, new_rows)
                        st.success("동선 정렬 완료!"); _rerun()
                with d3:
                    del_id = st.number_input("삭제할 ID", min_value=0, step=1, value=0, key="plan_del_id")
                    if st.button("선택 ID 삭제", key="plan_del_btn") and del_id>0:
                        DB.delete_item(int(del_id), rid)
                        rest = DB.list_items(rid, pick_day)
                        rest_sorted = sorted(rest, key=lambda x: x["position"])
                        repacked = []
                        p = 1
                        for it in rest_sorted:
                            repacked.append({
                                "id": it["id"], "position": p,
                                "start_time": it["start_time"] or "",
                                "end_time": it["end_time"] or "",
                                "category": it["category"], "name": it["name"],
                                "budget": float(it["budget"] or 0)
                            })
                            p += 1
                        if repacked:
                            DB.bulk_save_positions(rid, pick_day, repacked)
                        st.success("삭제 및 순서 재정렬 완료"); _rerun()

        # 우: 지도
        with right:
            st.subheader("동선 지도")
            items = DB.list_items(rid, pick_day)
            if not items:
                st.info("표에서 장소를 추가하면 지도에 표시됩니다.")
            else:
                lat0 = next((it["lat"] for it in items if it["lat"]), None) or 37.5665
                lon0 = next((it["lon"] for it in items if it["lon"]), None) or 126.9780
                m = folium.Map(location=[lat0, lon0], zoom_start=12, control_scale=True)
                items_sorted = sorted(items, key=lambda r:r["position"])
                coords=[]
                for i,it in enumerate(items_sorted, start=1):
                    if it["lat"] and it["lon"]:
                        coords.append((it["lat"], it["lon"]))
                        popup = f"{i}. {it['name']} · {it['category']} · 예산 {int(it['budget'])}원"
                        folium.Marker(
                            [it["lat"], it["lon"]],
                            popup=popup, tooltip=popup,
                            icon=folium.Icon(color="purple" if it["is_anchor"] else "blue")
                        ).add_to(m)
                if len(coords)>=2:
                    folium.PolyLine(coords, weight=4, opacity=0.8).add_to(m)
                st_folium(m, height=520, width=None)

    # ========== 💳 정산 (좌: 지출, 우: 요약) ==========
    with tab_cost:
        left, right = st.columns([1.2, 1])

        with left:
            st.subheader("지출 입력")
            days_options = pd.date_range(room["start"], room["end"]).strftime("%Y-%m-%d").tolist()
            exp_day = st.selectbox("날짜", days_options, key="exp_day")
            x1,x2,x3,x4 = st.columns([1.2,1,1,1.2])
            with x1: place_n = st.text_input("장소(선택 입력)", key="exp_place")
            with x2: payer    = st.selectbox("결제자", options=[(m["id"], (m["nickname"] or m["name"])) for m in members],
                                             format_func=lambda x: x[1], key="exp_payer")
            with x3: amt      = st.number_input("금액(원)", 0, step=1000, key="exp_amt")
            with x4: memo     = st.text_input("메모", key="exp_memo")
            if st.button("지출 추가", key="exp_add"):
                DB.add_expense(rid, exp_day, place_n or "", payer[0], float(amt), memo or "")
                st.success("지출 추가됨"); _rerun()

            st.markdown("### 지출 목록")
            exps = DB.list_expenses(rid)
            if exps:
                st.dataframe(
                    pd.DataFrame([{
                        "id":e["id"], "날짜":e["day"], "장소":e["place"],
                        "결제자": (e["payer_nick"] or e["payer_name"]),
                        "금액": int(e["amount"]), "메모": e["memo"] or ""
                    } for e in exps]),
                    hide_index=True, use_container_width=True
                )
                delx = st.number_input("지출 삭제 ID", min_value=0, step=1, value=0, key="exp_del_id")
                if st.button("지출 삭제", key="exp_del_btn") and delx>0:
                    DB.delete_expense(int(delx), rid); st.success("삭제됨"); _rerrun()
            else:
                st.info("지출 내역이 없습니다.")

        with right:
            st.subheader("정산 요약")
            transfers, total = DB.settle_transfers(rid)
            per_head = int(total / max(1, len(members)))
            st.caption(f"총 지출: **{int(total)}원** · 인당 **{per_head}원**")

            if not transfers:
                st.info("정산할 항목이 아직 없어요.")
            else:
                name_of = {m["id"]: (m["nickname"] or m["name"]) for m in members}
                st.write("**이체 추천 목록 (최소 이체 수)**")
                for t in transfers:
                    st.write(f"- {name_of[t['from']]} → {name_of[t['to']]} : **{int(t['amount'])}원**")

# ---------------- Router ----------------
def router():
    page = st.session_state.get("page", "auth")
    if "user_id" not in st.session_state:
        login_ui()
    else:
        if page == "dashboard": dashboard()
        elif page == "room": room_page()
        else: st.session_state["page"]="dashboard"; dashboard()

router()