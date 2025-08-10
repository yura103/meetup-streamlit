import streamlit as st
from datetime import date, timedelta
import random, string, pandas as pd, math
from streamlit.components.v1 import html as components_html

from planner_core import (
    Room, RoomSettings, MemberAvailability,
    save_room, load_room, WEIGHTS_DEFAULT,
    daterange, best_windows, perfect_windows_all_full,
    clear_member_submission, remove_member
)

st.set_page_config(page_title="약속/여행 날짜 잡기", layout="wide")

# ---------------- Utils ----------------
def gen_room_id(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

def date_df(start: date, end: date, existing: dict[str,str]|None=None) -> pd.DataFrame:
    return pd.DataFrame([{"date": d.isoformat(), "status": (existing or {}).get(d.isoformat(), "off")}
                         for d in daterange(start, end)])

STATUS_OPTIONS = {
    "불가(검정)": "off",
    "오전만(초록)": "am",
    "오후만(초록)": "pm",
    "저녁만(초록)": "eve",
    "하루종일(보라/분홍)": "full",
}

COLOR_MAP = {
    "off":   {"bg":"#000000","fg":"#FFFFFF","label":"불가"},
    "am":    {"bg":"#2ecc71","fg":"#000000","label":"오전"},
    "pm":    {"bg":"#2ecc71","fg":"#000000","label":"오후"},
    "eve":   {"bg":"#2ecc71","fg":"#000000","label":"저녁"},
    "full":  {"bg":"#b038ff","fg":"#FFFFFF","label":"가능"},
}

def colored_badge(status: str, text: str):
    c = COLOR_MAP[status]
    return f'<span style="background:{c["bg"]};color:{c["fg"]};padding:4px 8px;border-radius:6px;font-size:12px;">{text}</span>'

def render_legend():
    st.markdown("#### 색상 안내")
    cols = st.columns(5)
    legend_items = [
        ("off", "불가 (하루 불가능)"),
        ("am",  "오전만 가능"),
        ("pm",  "오후만 가능"),
        ("eve", "저녁만 가능"),
        ("full","하루 종일 가능"),
    ]
    for (status, text), c in zip(legend_items, cols):
        with c:
            st.markdown(colored_badge(status, COLOR_MAP[status]["label"]), unsafe_allow_html=True)
            st.caption(text)

def preview_calendar(df: pd.DataFrame, title="내 달력 미리보기"):
    st.markdown(f"### {title}")
    df2 = df.copy()
    df2["표시"] = [colored_badge(s, s.upper()) for s in df2["status"]]
    st.write(df2[["date","표시"]].to_html(escape=False, index=False), unsafe_allow_html=True)

def aggregate_by_date(room: Room) -> pd.DataFrame:
    start = date.fromisoformat(room.settings.start)
    end   = date.fromisoformat(room.settings.end)
    w = room.settings.weights
    rows = []
    for ds in [d.isoformat() for d in daterange(start, end)]:
        counts = {k:0 for k in ["off","am","pm","eve","full"]}
        for mv in room.members.values():
            counts[mv.by_date.get(ds, "off")] += 1
        score = (counts["full"] * w["full"] + (counts["am"]+counts["pm"]+counts["eve"]) * w["am"])
        quorum_now = counts["full"] + counts["am"] + counts["pm"] + counts["eve"]
        quorum_met = quorum_now >= room.settings.min_daily_quorum
        rows.append({
            "date": ds,
            "full": counts["full"],
            "half": counts["am"]+counts["pm"]+counts["eve"],
            "off": counts["off"],
            "score": round(score, 2),
            "quorum_ok": "✅" if quorum_met else "❌"
        })
    return pd.DataFrame(rows).sort_values("date")

def auto_refresh(toggle: bool, ms: int = 5000):
    if toggle:
        components_html(f"<script>setTimeout(()=>window.parent.location.reload(), {ms});</script>", height=0)

# ---------------- Sidebar ----------------
mode = st.sidebar.radio("모드 선택", ["만들기(Create)","참여하기(Join)"])
st.sidebar.markdown("---")
st.sidebar.caption("색 코딩: 불가=검정, 반만=초록, 가능=보라/분홍")

# ---------------- Create ----------------
if mode == "만들기(Create)":
    st.header("새 약속 방 만들기")
    colA, colB = st.columns([2,1])
    with colA:
        title = st.text_input("방 제목", value="여행/약속 후보일")
        host  = st.text_input("호스트 이름", value="host")
        num_members = st.number_input("인원 수", 2, 50, 4, step=1)
        min_days    = st.number_input("최소 연속 일수", 1, 30, 2, step=1)
        start = st.date_input("가능 시작일", date.today())
        end   = st.date_input("가능 종료일", date.today()+timedelta(days=14))
        if start > end: st.error("시작일이 종료일보다 뒤예요.")
    with colB:
        default_quorum = max(2, math.ceil(num_members*0.6))
        quorum = st.number_input("일자별 최소 모임 인원", 1, int(num_members), int(default_quorum))
        w_full = st.number_input("하루종일 가능 가중치", 0.0, 2.0, 1.0, 0.1)
        w_half = st.number_input("반만 가능 가중치", 0.0, 2.0, 0.5, 0.1)
        weights = {"off":0.0, "am":w_half, "pm":w_half, "eve":w_half, "full":w_full}
    if st.button("방 생성"):
        rid = gen_room_id()
        settings = RoomSettings(num_members, min_days, start.isoformat(), end.isoformat(), quorum, weights)
        room = Room(rid, title, host, settings)
        save_room(room)
        st.success(f"방 코드: **{rid}** (참여자는 '참여하기'에서 입력)")

# ---------------- Join ----------------
else:
    st.header("약속 방 참여하기 / 입력")
    rid_input = st.text_input("방 코드 입력")
    me_input  = st.text_input("내 이름")
    if st.button("불러오기"):
        st.session_state["rid"], st.session_state["me"] = rid_input.strip(), me_input.strip()
    rid, me = st.session_state.get("rid"), st.session_state.get("me")
    if not rid or not me: st.stop()

    room = load_room(rid)
    if not room: st.error("방을 찾을 수 없어요."); st.stop()

    st.subheader(f"방: {room.title} | 인원 {len(room.members)}/{room.settings.num_members}")
    st.caption(f"{room.settings.start} ~ {room.settings.end} / 최소 연속일수 {room.settings.min_days} / 최소 인원 {room.settings.min_daily_quorum}")
    render_legend()

    existing = room.members.get(me).by_date if me in room.members else {}
    df = date_df(date.fromisoformat(room.settings.start), date.fromisoformat(room.settings.end), existing)
    inv = {v:k for k,v in STATUS_OPTIONS.items()}
    df["상태"] = [inv.get(v, "불가(검정)") for v in df["status"]]
    edited = st.data_editor(df[["date","상태"]], hide_index=True,
        column_config={"상태": st.column_config.SelectboxColumn(options=list(STATUS_OPTIONS.keys()))})
    edited["status"] = [STATUS_OPTIONS[x] for x in edited["상태"]]
    edited = edited[["date","status"]]
    preview_calendar(edited)

    c1,c2 = st.columns(2)
    with c1:
        if st.button("저장"):
            mv = room.members.get(me) or MemberAvailability(name=me)
            mv.by_date, mv.submitted = {r["date"]: r["status"] for _, r in edited.iterrows()}, False
            room.members[me] = mv; save_room(room); st.success("저장됨")
    with c2:
        if st.button("제출"):
            mv = room.members.get(me) or MemberAvailability(name=me)
            mv.by_date, mv.submitted = {r["date"]: r["status"] for _, r in edited.iterrows()}, True
            room.members[me] = mv; save_room(room); st.success("제출 완료")

    # 제출 현황
    sub_dict = {n: "✅" if m.submitted else "⏳" for n,m in room.members.items()}
    st.write("제출 현황:", sub_dict)

    # 제출자/대기자 명단
    subs = [n for n,m in room.members.items() if m.submitted]
    pend = [n for n,m in room.members.items() if not m.submitted]
    badge = lambda t: f'<span style="background:#eee;padding:4px 8px;border-radius:12px">{t}</span>'
    st.markdown("**제출 완료:** " + (" ".join(badge(x) for x in subs) or "없음"), unsafe_allow_html=True)
    st.markdown("**제출 대기:** " + (" ".join(badge(x) for x in pend) or "없음"), unsafe_allow_html=True)

    # 내 제출 관리
    my_cur = room.members.get(me)
    if my_cur and my_cur.by_date:
        with st.expander("내 입력 미리보기"):
            st.dataframe(pd.DataFrame(sorted(my_cur.by_date.items())), hide_index=True)
    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("제출 취소"):
            my_cur.submitted=False; save_room(room); st.experimental_rerun()
    with c2:
        if st.button("내 입력 삭제"):
            clear_member_submission(room, me); st.experimental_rerun()
    with c3:
        if st.button("방 나가기"):
            if me!=room.creator: remove_member(room, me); st.experimental_rerun()

    # 호스트 대시보드
    if me == room.creator:
        st.markdown("### 👑 호스트 대시보드")
        auto_refresh(st.checkbox("자동 새로고침", False), 5000)
        st.dataframe(aggregate_by_date(room), hide_index=True)
        for i,win in enumerate(best_windows(room),1):
            st.write(f"{i}. {win['days']} | 점수 {win['score']:.1f} | {'충족' if win['feasible'] else '미충족'}")
        # 멤버 관리
        tgt = st.selectbox("멤버 선택", [""]+list(room.members.keys()))
        if tgt:
            st.write(room.members[tgt].by_date)
            cc1,cc2,cc3 = st.columns(3)
            with cc1:
                if st.button("제출 해제"): room.members[tgt].submitted=False; save_room(room); st.experimental_rerun()
            with cc2:
                if st.button("입력 비우기"): clear_member_submission(room, tgt); st.experimental_rerun()
            with cc3:
                if st.button("멤버 제거") and tgt!=room.creator: remove_member(room, tgt); st.experimental_rerun()

    # 최종 추천
    if room.all_submitted():
        st.success("모든 인원 제출 완료!")
        fulls = perfect_windows_all_full(room)
        if fulls:
            st.write("전원 가능 구간:", fulls)
        else:
            st.write("가중치 기반 추천:", best_windows(room))
