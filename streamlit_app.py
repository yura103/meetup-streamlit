import streamlit as st, pandas as pd, datetime as dt
import database as DB
import auth as AUTH
from planner_core import best_windows, optimize_route
from email_utils import send_reset_email
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim

# (선택) 카테고리 파이차트용 - 설치가 안 되어 있으면 막대 그래프로 대체
try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False

st.set_page_config(page_title="친구 약속 잡기", layout="wide")
DB.init_db()

def _rerun():
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()

# 색약 친화 팔레트 + 심볼
COLOR = {
    "off":  {"bg":"#000000","fg":"#FFFFFF","label":"불가(0.0)"},
    "eve":  {"bg":"#56B4E9","fg":"#FFFFFF","label":"3시간 이상 / 잘 모르겠다(0.4)"},
    "pm":   {"bg":"#009E73","fg":"#FFFFFF","label":"5시간 이상(0.5)"},
    "am":   {"bg":"#E69F00","fg":"#000000","label":"7시간 이상(0.7)"},
    "full": {"bg":"#CC79A7","fg":"#FFFFFF","label":"하루종일(1.0)"},
}
STATUS_SYMBOL  = {"off":"×","eve":"3","pm":"5","am":"7","full":"F"}
STATUS_KO      = {"off":"불가","eve":"3시간/모름","pm":"5시간","am":"7시간","full":"하루종일"}
def level_rank(s): return {"off":0,"eve":1,"pm":2,"am":3,"full":4}.get(s,0)

def legend():
    st.markdown("""
<style>
.badge{padding:6px 10px;border-radius:999px;margin-right:6px;display:inline-block;font-weight:700}
@media (max-width: 480px){
  .mobile-hide{display:none;}
}
</style>
    """, unsafe_allow_html=True)
    for s in ["off","eve","pm","am","full"]:
        c = COLOR[s]
        st.markdown(
            f'<span class="badge" style="background:{c["bg"]};color:{c["fg"]}">{STATUS_SYMBOL[s]} · {c["label"]}</span>',
            unsafe_allow_html=True
        )
    st.caption("심볼: F=하루종일, 7=7시간, 5=5시간, 3=3시간/모름, ×=불가")

def chip(txt):
    return f'<span style="background:#f5f5f5;border:1px solid #ddd;padding:2px 8px;border-radius:999px;margin-right:6px;display:inline-block">{txt}</span>'

# -------- 매트릭스 렌더 --------
def build_person_day_map(days_seq, names_by_day):
    persons=set()
    for d in days_seq:
        for s in ("full","am","pm","eve"):
            for n in names_by_day.get(d,{}).get(s, []):
                persons.add(n)
    persons=sorted(persons, key=lambda x:x.lower())
    pmap={n:{} for n in persons}
    for d in days_seq:
        for s in ("full","am","pm","eve"):
            for n in names_by_day.get(d,{}).get(s, []):
                pmap[n][d]=s
        for n in persons:
            pmap[n].setdefault(d,"off")
    return persons, pmap

def render_availability_matrix(days_seq, names_by_day, title=None, note=None, max_rows=None):
    persons, pmap = build_person_day_map(days_seq, names_by_day)
    if max_rows: persons = persons[:max_rows]
    header = "".join(
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #eee;'
        f'font-weight:600;font-size:12px;padding:6px 4px;text-align:center">{d[5:]}</th>'
        for d in days_seq
    )
    rows=[]
    for n in persons:
        cells=[]
        for d in days_seq:
            s = pmap[n][d]; c = COLOR[s]
            sym = STATUS_SYMBOL[s]
            tip = f"{n} · {d} · {STATUS_KO[s]}"
            cells.append(
                f'<td title="{tip}" style="text-align:center;padding:2px 3px;">'
                f'<div style="width:24px;height:18px;border-radius:5px;background:{c["bg"]};color:{c["fg"]};'
                f'display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px">{sym}</div>'
                f'</td>'
            )
        rows.append(
            f'<tr>'
            f'<td style="position:sticky;left:0;background:#fff;font-size:13px;padding:4px 8px;'
            f'border-right:1px solid #eee;white-space:nowrap">{n}</td>'
            f'{"".join(cells)}'
            f'</tr>'
        )
    html = f"""
<div style="margin-top:6px;margin-bottom:10px">
  {f'<div style="font-weight:700;margin-bottom:4px">{title}</div>' if title else ''}
  <div style="overflow:auto;border:1px solid #eee;border-radius:10px">
    <table style="border-collapse:separate;border-spacing:0;min-width:100%">
      <thead><tr>
        <th style="position:sticky;left:0;z-index:2;background:#fff;border-bottom:1px solid #eee;padding:6px 8px;text-align:left">이름</th>
        {header}
      </tr></thead>
      <tbody>
        {"".join(rows) or '<tr><td style="padding:8px">데이터 없음</td></tr>'}
      </tbody>
    </table>
  </div>
  {f'<div style="color:#666;font-size:12px;margin-top:6px">{note}</div>' if note else ''}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

# ===== 겹치거나 인접(하루 차이) 구간 병합 =====
def merge_overlapping_windows(raw_top, agg_by_day, quorum: int):
    if not raw_top:
        return []
    intervals = []
    for w in raw_top:
        start_d = dt.date.fromisoformat(w["days"][0])
        end_d   = dt.date.fromisoformat(w["days"][-1])
        intervals.append({"start": start_d, "end": end_d, "days": set(w["days"])})
    intervals.sort(key=lambda x: x["start"])
    merged = []
    cur = intervals[0]
    for nxt in intervals[1:]:
        if nxt["start"] <= cur["end"] + dt.timedelta(days=1):
            cur["end"]  = max(cur["end"], nxt["end"])
            cur["days"] |= nxt["days"]
        else:
            merged.append(cur)
            cur = nxt
    merged.append(cur)
    out = []
    for m in merged:
        days_sorted = sorted(list(m["days"]))
        score = sum(agg_by_day[d]["score"] for d in days_sorted)
        feasible = all(
            (agg_by_day[d]["full"] + agg_by_day[d]["am"] + agg_by_day[d]["pm"] + agg_by_day[d]["eve"]) >= quorum
            for d in days_sorted
        )
        out.append({"days": days_sorted, "score": score, "feasible": feasible})
    out.sort(key=lambda w: (-w["score"], w["days"][0]))
    return out

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

# ---------------- 지출 렌더 (날짜/카테고리 요약 + 삭제) ----------------
def render_expenses(rid, members):
    st.subheader("지출 입력")
    room, _, _, _ = DB.day_aggregate(rid)
    days_options = pd.date_range(room["start"], room["end"]).strftime("%Y-%m-%d").tolist()
    exp_day = st.selectbox("날짜", days_options, key="exp_day")
    x1,x2,x3,x4,x5 = st.columns([1.2,1,1,1.2,1.1])
    with x1: place_n = st.text_input("장소(선택 입력)", key="exp_place")
    with x2: payer    = st.selectbox("결제자", options=[(m["id"], (m["nickname"] or m["name"])) for m in members],
                                     format_func=lambda x: x[1], key="exp_payer")
    with x3: amt      = st.number_input("금액(원)", 0, step=1000, key="exp_amt")
    with x4: memo     = st.text_input("메모", key="exp_memo")
    with x5:
        cat = st.selectbox("카테고리", ["식사","숙소","놀기","카페","쇼핑","기타"], key="exp_cat")
    if st.button("지출 추가", key="exp_add"):
        # DB에 category 컬럼 반영된 버전이어야 함(없다면 DB 스키마에 column 추가)
        try:
            DB.add_expense(rid, exp_day, place_n or "", payer[0], float(amt), memo or "", category=cat)
        except TypeError:
            # 구버전 호환: category 인자 없는 경우 그냥 저장
            DB.add_expense(rid, exp_day, place_n or "", payer[0], float(amt), memo or "")
        st.success("지출 추가됨"); _rerun()

    st.markdown("### 지출 목록 / 통계")
    exps = DB.list_expenses(rid)
    def row_get(row, key, default=None):
    # sqlite3.Row는 .get이 없으므로 keys()로 확인해서 안전하게 꺼낸다
        try:
            if hasattr(row, "keys") and key in row.keys():
                val = row[key]
                return default if (val is None or val == "") else val
        except Exception:
            pass
        return default

    df_exp_raw = pd.DataFrame([{
        "id":       e["id"],
        "day":      e["day"] or "",
        "place":    e["place"] or "",
        # category 컬럼이 DB에 없어도 안전하게 "기타"로 세팅
        "category": row_get(e, "category", "기타"),
        "payer":    (e["payer_nick"] or e["payer_name"]),
        "amount":   float(e["amount"] or 0),
        "memo":     e["memo"] or "",
    } for e in exps])

    df_exp_raw["amount"] = pd.to_numeric(df_exp_raw["amount"], errors="coerce").fillna(0)
    df_exp_raw["day"] = pd.to_datetime(df_exp_raw["day"], errors="coerce").dt.strftime("%Y-%m-%d")

    df_view = df_exp_raw.rename(columns={
        "day":"날짜","place":"장소","payer":"결제자","amount":"금액","category":"카테고리","memo":"메모"
    })
    st.dataframe(df_view[["id","날짜","장소","결제자","금액","카테고리","메모"]], hide_index=True, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        by_day = df_exp_raw.groupby("day", dropna=False)["amount"].sum().reset_index().sort_values("day")
        st.markdown("#### 📅 날짜별 지출 합계")
        st.dataframe(by_day.rename(columns={"day":"날짜","amount":"합계(원)"}), hide_index=True, use_container_width=True)
    with c2:
        by_cat = df_exp_raw.groupby("category", dropna=False)["amount"].sum().reset_index().sort_values("amount", ascending=False)
        st.markdown("#### 🥧 카테고리별 지출 비중")
        if HAS_MPL:
            fig, ax = plt.subplots()
            ax.pie(by_cat["amount"], labels=by_cat["category"], autopct="%1.0f%%")
            ax.axis("equal")
            st.pyplot(fig)
        else:
            st.bar_chart(by_cat.set_index("category")["amount"])

    delx = st.number_input("지출 삭제 ID", min_value=0, step=1, value=0, key="exp_del_id")
    if st.button("지출 삭제", key="exp_del_btn") and delx>0:
        DB.delete_expense(int(delx), rid); st.success("삭제됨"); _rerun()

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
    # 사이트 관리자 여부(있으면 True)
    try:
        is_admin = bool(DB.is_site_admin(st.session_state["user_id"]))
    except Exception:
        is_admin = False
    is_manager = (is_owner or is_admin)

    # 헤더 + 레전드
    st.header(f"방: {room['title']} ({rid})")
    st.caption(f"{room['start']} ~ {room['end']} / 최소{room['min_days']}일 / 쿼럼{room['quorum']}")

    # 최종 선택 표시(강조)
    if room["final_start"] and room["final_end"]:
        st.markdown(
            f"""
<div style="padding:10px 12px;border:2px solid #7c3aed;border-radius:12px;background:#faf5ff">
  <b>✅ 최종 확정</b>:
  <span style="font-weight:700">{room['final_start']} ~ {room['final_end']}</span>
</div>
""", unsafe_allow_html=True)

    legend()

    # ----- 사이드바: 공지 & 투표 -----
    with st.sidebar:
        st.header("🗞 공지 & 🗳 투표")

        st.subheader("📌 공지사항")
        anns = DB.list_announcements(rid)
        pinned = [a for a in anns if a["pinned"]]
        for a in pinned[:2]:
            st.info(f"**{a['title']}**\n\n{a['body']}")
        with st.expander("전체 공지 보기", expanded=False):
            for a in anns:
                st.markdown(f"**{a['title']}**  · {a['created_at'][:16].replace('T',' ')}")
                st.caption(a["body"])
                if is_manager:
                    c1,c2 = st.columns(2)
                    with c1:
                        if st.button(("고정 해제" if a["pinned"] else "고정"), key=f"pin_{a['id']}"):
                            DB.toggle_pin_announcement(a["id"], rid, room["owner_id"]); _rerun()
                    with c2:
                        if st.button("삭제", key=f"delann_{a['id']}"):
                            DB.delete_announcement(a["id"], rid, room["owner_id"]); _rerun()
                st.markdown("---")
        if is_manager:
            st.caption("새 공지")
            ann_title = st.text_input("제목", key="ann_title_sb")
            ann_body  = st.text_area("내용", key="ann_body_sb")
            ann_pin   = st.checkbox("고정", value=False, key="ann_pin_sb")
            if st.button("등록", key="ann_add_sb"):
                if ann_title.strip():
                    DB.add_announcement(rid, ann_title.strip(), ann_body.strip(), int(ann_pin), st.session_state["user_id"])
                    st.success("등록됨"); _rerun()
                else:
                    st.error("제목은 필수예요.")
        st.markdown("---")

        st.subheader("🗳 투표")
        polls = DB.list_polls(rid)
        if not polls:
            st.caption("진행 중 투표 없음")
        else:
            for p in polls:
                st.markdown(f"**{p['question']}**" + (f" · 마감 {p['closes_at'][:16].replace('T',' ')}" if p["closes_at"] else ""))
                opts = DB.list_poll_options(p["id"])
                my_votes = set(DB.get_user_votes(p["id"], st.session_state["user_id"]))
                if p["is_multi"]:
                    picked = st.multiselect("선택", [o["id"] for o in opts], default=list(my_votes),
                                            format_func=lambda oid: next(o["text"] for o in opts if o["id"]==oid), key=f"pv_{p['id']}")
                else:
                    all_ids = [o["id"] for o in opts]
                    idx = (all_ids.index(next(iter(my_votes))) if my_votes else 0) if all_ids else 0
                    picked = st.radio("선택", all_ids, index=idx if all_ids else None,
                                      format_func=lambda oid: next(o["text"] for o in opts if o["id"]==oid), key=f"pv_{p['id']}")
                    picked = [picked] if all_ids else []
                if st.button("투표/변경", key=f"vote_{p['id']}"):
                    DB.cast_vote(p["id"], picked, st.session_state["user_id"], bool(p["is_multi"]))
                    st.success("반영됨"); _rerun()
                counts, total = DB.tally_poll(p["id"])
                for o in opts:
                    c = counts.get(o["id"], 0); ratio = (c/total*100) if total else 0
                    st.progress(min(1.0, ratio/100.0), text=f"{o['text']} · {c}표 ({ratio:0.0f}%)")
                st.markdown("---")
        if is_manager:
            with st.expander("새 투표 만들기", expanded=False):
                q = st.text_input("질문", key="newpoll_q")
                raw_opts = st.text_area("보기들(줄바꿈)", key="newpoll_opts")
                multi = st.checkbox("다중 선택", value=False, key="newpoll_multi")
                closes = st.date_input("마감일(선택)", value=None, key="newpoll_date")
                if st.button("투표 생성", key="newpoll_make"):
                    options = [s.strip() for s in (raw_opts or "").splitlines() if s.strip()]
                    closes_at = (dt.datetime.combine(closes, dt.time(23,59)).isoformat() if closes else None)
                    if q.strip() and options:
                        DB.create_poll(rid, q.strip(), int(multi), options, closes_at, st.session_state["user_id"])
                        st.success("투표 생성!"); _rerun()
                    else:
                        st.error("질문과 보기 필요")

    # ---- 방장/관리자 관리 ----
    if is_manager:
        with st.expander("👑 방 관리 (관리자/방장)", expanded=False):
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
                # 방장 + 관리자 모두 삭제 가능 (DB.delete_room은 owner_id만 맞으면 삭제됨)
                if st.button("⚠️ 방 삭제 (관리자/방장)", type="secondary", key="room_delete"):
                    DB.delete_room(rid, room["owner_id"])
                    st.success("방 삭제 완료")
                    st.session_state["page"] = "dashboard"
                    st.session_state.pop("room_id", None)
                    _rerun()

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

    # ---- 탭 ----
    st.markdown("---")
    tab_time, tab_plan, tab_cost = st.tabs(["⏰ 시간/약속", "🗺️ 계획 & 동선 / 예산", "💳 정산"])

    # ========== ⏰ 시간/약속 ==========
    with tab_time:
        st.subheader("내 달력 입력")
        my_av = DB.get_my_availability(st.session_state["user_id"], rid)

        # 범위 → DataFrame
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

        room_row, days_list, agg, weights = DB.day_aggregate(rid)
        names_by_day = DB.availability_names_by_day(rid)

        # 날짜별 요약 표
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

        # 날짜별 뱃지
        st.markdown("#### 날짜별 가능 멤버(뱃지)")
        pick_for_names = st.selectbox("날짜 선택", days_list, index=0, key="names_day_pick")
        nb = names_by_day.get(pick_for_names, {})
        for label, key in [("하루종일","full"),("7시간","am"),("5시간","pm"),("3시간/모름","eve")]:
            chips = " ".join(chip(n) for n in nb.get(key, [])) or "(없음)"
            st.markdown(f"**{label}** · {chips}", unsafe_allow_html=True)

        # --------- 추천 계산 (Top‑7 + 병합) ---------
        raw_top = best_windows(days_list, agg, int(room_row["min_days"]), int(room_row["quorum"]))
        if raw_top:
            merged_top = merge_overlapping_windows(raw_top, agg, int(room_row["quorum"]))
            st.markdown("### ⭐ 추천 Top‑7 (겹치거나 붙는 구간은 하나로 합침)")

            def render_win_summary(days_seq, score, feasible, show_select_button=False, small=False):
                feas = "충족" if feasible else "⚠️ 최소 인원 미충족 포함"
                cols = st.columns([5,2]) if show_select_button else None
                if show_select_button:
                    with cols[0]:
                        st.write(f"**{days_seq[0]} ~ {days_seq[-1]} | 점수 {score:.2f} | {feas}**")
                    with cols[1]:
                        if st.button("이 구간 최종 선택", key=f"choose_{days_seq[0]}_{days_seq[-1]}"):
                            DB.set_final_window(rid, room["owner_id"], days_seq[0], days_seq[-1])
                            st.success("최종 일정으로 저장했습니다."); _rerun()
                else:
                    st.write(f"**{days_seq[0]} ~ {days_seq[-1]} | 점수 {score:.2f} | {feas}**")

                K = len(days_seq)
                stats = {}; all_names=set()
                for d in days_seq:
                    nb_d = names_by_day.get(d, {})
                    for s in ("full","am","pm","eve"):
                        for name in nb_d.get(s, []):
                            all_names.add(name)
                            rec = stats.setdefault(name, {"cnt":0, "lowest":"full"})
                            rec["cnt"] += 1
                            rec["lowest"] = min(rec["lowest"], s, key=level_rank)
                full_ok = [ (n, stats[n]["lowest"]) for n in all_names if stats[n]["cnt"] == K ]
                part_ok = [ (n, stats[n]["lowest"], stats[n]["cnt"]) for n in all_names if 0 < stats[n]["cnt"] < K ]
                full_ok.sort(key=lambda x: (-level_rank(x[1]), x[0].lower()))
                part_ok.sort(key=lambda x: (-x[2], -level_rank(x[1]), x[0].lower()))
                level_label={"full":"하루종일","am":"7시간","pm":"5시간","eve":"3시간/모름"}
                chips_full = " ".join(chip(f"{n} · {level_label.get(lvl,lvl)}") for n,lvl in full_ok) or "(없음)"
                st.markdown("가능 멤버(구간 **전체**): " + chips_full, unsafe_allow_html=True)
                if part_ok:
                    chips_part = " ".join(chip(f"{n} · {level_label.get(lvl,lvl)} · {cnt}/{K}일") for n,lvl,cnt in part_ok)
                    st.markdown("가능 멤버(구간 **부분**): " + chips_part, unsafe_allow_html=True)

                # 미니 매트릭스
                render_availability_matrix(
                    days_seq, names_by_day,
                    title=("미니 달력(대안 구간 상세)" if small else "사람×날짜 가능수준 (F/7/5/3/×)"),
                    note=("칸에 마우스를 올리면 상태 툴팁이 보여요." if small else None),
                    max_rows=(8 if small else None)
                )

            for i, w in enumerate(merged_top[:7], 1):
                st.write(f"**#{i}**")
                render_win_summary(w["days"], w["score"], w["feasible"], show_select_button=is_manager)
        else:
            st.info("추천할 구간이 아직 없어요. 인원 입력을 더 받아보세요.")
        if DB.all_submitted(rid):
            st.success("모든 인원이 제출 완료! 위 추천 구간을 참고해 최종 확정하세요 ✅")

        # --- 전체 타임라인 (옵션) ---
        if st.toggle("사람별 타임라인(전체 기간) 보기", value=False):
            render_availability_matrix(
                days_list, names_by_day,
                title="전체 기간 타임라인 (F/7/5/3/×)",
                note="이름/날짜 헤더는 스크롤해도 고정됩니다."
            )

    # ========== 🗺️ 계획 & 동선 / 예산 ==========
    with tab_plan:
        left, right = st.columns([1.05, 1])

        days_options = pd.date_range(room["start"], room["end"]).strftime("%Y-%m-%d").tolist()
        pick_day = st.selectbox("날짜 선택", days_options, index=0, key="plan_day")

        with left:
            st.subheader("계획표 (날짜·순서·시간·카테고리·장소·예산)")

            with st.expander("📍 장소 검색해서 추가", expanded=False):
                q = st.text_input("장소/주소 검색", key="plan_q")
                cA,cB,cC,cD = st.columns([2,1,1,1])
                with cA: cat = st.selectbox("카테고리", ["식사","숙소","놀기","카페","쇼핑","기타"], key="plan_cat")
                with cB: bud = st.number_input("예산(원)", 0, step=1000, value=0, key="plan_budget")
                with cC: is_anchor = st.checkbox("숙소/고정", value=False, key="plan_anchor")
                with cD: sel_day = st.selectbox("날짜", days_options, index=(days_options.index(pick_day) if pick_day in days_options else 0), key="plan_sel_day")
                if st.button("검색 & 추가", key="plan_add"):
                    if not q.strip():
                        st.error("검색어를 입력하세요.")
                    else:
                        try:
                            geoloc = Nominatim(user_agent="youchin").geocode(q)
                            lat, lon = (geoloc.latitude, geoloc.longitude) if geoloc else (None, None)
                        except Exception:
                            lat, lon = (None, None)
                        DB.add_item(rid, sel_day, q.strip(), cat, lat, lon, bud, None, None, is_anchor, None, st.session_state["user_id"])
                        st.success("추가됨"); _rerun()

            rows = DB.list_items(rid, pick_day)
            table = []
            for r in rows:
                table.append({
                    "id": r["id"], "position": r["position"], "번호": 0,
                    "day": r["day"],
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
                        "day": st.column_config.SelectboxColumn("날짜", options=days_options),
                        "start_time": st.column_config.TextColumn("시작", help="예: 10:00"),
                        "end_time": st.column_config.TextColumn("종료", help="예: 12:00"),
                        "category": st.column_config.SelectboxColumn("카테고리", options=["식사","숙소","놀기","카페","쇼핑","기타"]),
                        "name": st.column_config.TextColumn("장소"),
                        "budget": st.column_config.NumberColumn("예산(원)", step=1000),
                    },
                    hide_index=True, use_container_width=True, key="plan_editor"
                )

                d1, d2, d3, d4 = st.columns(4)
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
                with d4:
                    st.caption("지도에서 마커 클릭 → 아래에서 ↑/↓")
                    clicked_id = st.session_state.get("clicked_item_id")
                    if clicked_id:
                        st.info(f"선택된 ID: {clicked_id}")
                        if st.button("선택 항목 ↑", key="route_up"):
                            recs = edited.to_dict("records")
                            idx = next((i for i,r in enumerate(recs) if r["id"]==clicked_id), None)
                            if idx is not None and idx>0:
                                recs[idx]["position"], recs[idx-1]["position"] = recs[idx-1]["position"], recs[idx]["position"]
                                DB.bulk_save_positions(rid, pick_day, recs)
                                st.success("위로 이동"); _rerun()
                        if st.button("선택 항목 ↓", key="route_down"):
                            recs = edited.to_dict("records")
                            idx = next((i for i,r in enumerate(recs) if r["id"]==clicked_id), None)
                            if idx is not None and idx < len(recs)-1:
                                recs[idx]["position"], recs[idx+1]["position"] = recs[idx+1]["position"], recs[idx]["position"]
                                DB.bulk_save_positions(rid, pick_day, recs)
                                st.success("아래로 이동"); _rerun()

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
                        order_num = i
                        # 숫자 라벨이 보이는 아이콘
                        folium.map.Marker(
                            [it["lat"], it["lon"]],
                            icon=folium.DivIcon(html=f"""<div style="font-weight:800;color:#1f2937;background:#fff;padding:2px 6px;border-radius:12px;border:1px solid #ddd">{order_num}</div>"""),
                        ).add_to(m)
                        popup = f"{order_num}. {it['name']} · {it['category']} · 예산 {int(it['budget'])}원 (ID:{it['id']})"
                        # 실제 클릭용 마커(투명)
                        folium.CircleMarker(
                            location=[it["lat"], it["lon"]],
                            radius=8, color="#6366f1", fill=True, fill_opacity=0.2, popup=popup, tooltip=popup
                        ).add_to(m)
                if len(coords)>=2:
                    folium.PolyLine(coords, weight=4, opacity=0.8).add_to(m)
                ret = st_folium(m, height=520, width=None)
                # 지도 클릭 → 가장 가까운 아이템을 선택한 걸로 처리
                if ret and ret.get("last_clicked"):
                    lat = ret["last_clicked"]["lat"]; lon = ret["last_clicked"]["lng"]
                    # 최근접 아이템 찾기
                    def dist2(a,b): return (a[0]-b[0])**2 + (a[1]-b[1])**2
                    nearest = None; best = 1e18
                    for it in items_sorted:
                        if it["lat"] and it["lon"]:
                            d2 = dist2((lat,lon),(it["lat"],it["lon"]))
                            if d2 < best:
                                best = d2; nearest = it
                    if nearest:
                        st.session_state["clicked_item_id"] = nearest["id"]
                        st.toast(f"선택: {nearest['name']} (ID:{nearest['id']})", icon="✅")

    # ========== 💳 정산 ==========
    with tab_cost:
        left, right = st.columns([1.2, 1])
        with left:
            render_expenses(rid, members)
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
        else:
            st.session_state["page"]="dashboard"; dashboard()

router()