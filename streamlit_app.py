import streamlit as st
import math
from datetime import date, timedelta
import random, string, pandas as pd
from planner_core import (
    Room, RoomSettings, MemberAvailability,
    save_room, load_room, WEIGHTS_DEFAULT,
    daterange, best_windows, perfect_windows_all_full
)

st.set_page_config(page_title="약속/여행 날짜 잡기", layout="wide")

# ---------------- Utils ----------------
def gen_room_id(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

def date_df(start: date, end: date, existing: dict[str,str]|None=None) -> pd.DataFrame:
    rows = []
    for d in daterange(start, end):
        ds = d.isoformat()
        rows.append({
            "date": ds,
            "status": (existing or {}).get(ds, "off")
        })
    return pd.DataFrame(rows)

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

def preview_calendar(df: pd.DataFrame, title="내 달력 미리보기"):
    st.markdown(f"### {title}")
    # 간단 미리보기(표) – 날짜/상태 컬러 뱃지
    df2 = df.copy()
    df2["표시"] = [colored_badge(s, s.upper()) for s in df2["status"]]
    st.write(df2[["date","표시"]].to_html(escape=False, index=False), unsafe_allow_html=True)

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
        num_members = st.number_input("인원 수", min_value=2, max_value=30, value=4, step=1)
        min_days    = st.number_input("최소 여행/약속 일수", min_value=1, max_value=14, value=2, step=1)
        start = st.date_input("가능 시작일", value=date.today())
        end   = st.date_input("가능 종료일", value=date.today()+timedelta(days=14))
        if start > end:
            st.error("시작일이 종료일보다 뒤예요.")
    with colB:
        default_quorum = max(2, math.ceil(num_members*0.6))
        quorum = st.number_input("일자별 최소 모임 인원(Quorum)", min_value=1, max_value=int(num_members), value=int(default_quorum))
        st.markdown("가중치(필요시 조정)")
        w_full = st.number_input("하루종일", 0.0, 2.0, 1.0, 0.1)
        w_half = st.number_input("반만(오전/오후/저녁)", 0.0, 2.0, 0.5, 0.1)
        weights = {"off":0.0, "am":w_half, "pm":w_half, "eve":w_half, "full":w_full}

    if st.button("방 생성"):
        rid = gen_room_id()
        settings = RoomSettings(
            num_members=int(num_members),
            min_days=int(min_days),
            start=start.isoformat(),
            end=end.isoformat(),
            min_daily_quorum=int(quorum),
            weights=weights
        )
        room = Room(room_id=rid, title=title, creator=host, settings=settings, members={})
        save_room(room)
        st.success(f"방이 생성됐어요! 방 코드: **{rid}**")
        st.info("참여자는 상단 모드에서 '참여하기'를 선택하고 방 코드를 입력하세요.")
        st.stop()

# ---------------- Join ----------------
else:
    st.header("약속 방 참여하기 / 입력")
    rid = st.text_input("방 코드(Room ID) 입력")
    me  = st.text_input("내 이름")

    if st.button("불러오기"):
        st.session_state["room_id_loaded"] = rid
        st.session_state["me"] = me

    rid = st.session_state.get("room_id_loaded")
    me  = st.session_state.get("me")

    if not rid or not me:
        st.info("방 코드와 이름을 입력하고 '불러오기'를 눌러주세요.")
        st.stop()

    room = load_room(rid)
    if not room:
        st.error("방을 찾을 수 없어요.")
        st.stop()

    st.subheader(f"방: {room.title}  |  인원 {len(room.members)}/{room.settings.num_members}")
    st.caption(f"기간 {room.settings.start} ~ {room.settings.end} / 최소 일수 {room.settings.min_days} / 일자별 최소 인원 {room.settings.min_daily_quorum}")

    # 내 기존 입력 불러오기/초기화
    start = date.fromisoformat(room.settings.start)
    end   = date.fromisoformat(room.settings.end)
    existing = room.members.get(me).by_date if me in room.members else {}

    df = date_df(start, end, existing)

    # 편집기: 상태 선택형
    st.markdown("#### 날짜별 상태 입력")
    def _map_show_to_value(label: str) -> str:
        return STATUS_OPTIONS[label]

    def _map_value_to_show(val: str) -> str:
        inv = {v:k for k,v in STATUS_OPTIONS.items()}
        return inv.get(val, "불가(검정)")

    df["상태(클릭해서 선택)"] = [_map_value_to_show(v) for v in df["status"]]
    edited = st.data_editor(
        df[["date","상태(클릭해서 선택)"]],
        hide_index=True,
        column_config={
            "상태(클릭해서 선택)": st.column_config.SelectboxColumn(
                width="medium",
                options=list(STATUS_OPTIONS.keys()),
            ),
            "date": st.column_config.TextColumn("날짜", disabled=True, width="small"),
        },
        use_container_width=True,
    )
    # 저장용 값 복원
    edited["status"] = [ _map_show_to_value(x) for x in edited["상태(클릭해서 선택)"] ]
    edited = edited[["date","status"]]

    preview_calendar(edited, title="색상 미리보기")

    left, right = st.columns(2)
    with left:
        if st.button("내 입력 저장"):
            mv = room.members.get(me) or MemberAvailability(name=me)
            mv.by_date = {r["date"]: r["status"] for _, r in edited.iterrows()}
            mv.submitted = False  # 저장만
            room.members[me] = mv
            save_room(room)
            st.success("저장 완료(아직 제출 전)")
    with right:
        if st.button("제출(Submit)"):
            mv = room.members.get(me) or MemberAvailability(name=me)
            mv.by_date = {r["date"]: r["status"] for _, r in edited.iterrows()}
            mv.submitted = True
            room.members[me] = mv
            save_room(room)
            st.success("제출 완료!")

    # 제출 현황
    st.markdown("#### 제출 현황")
    sub = {name: ("✅" if mv.submitted else "⏳") for name, mv in room.members.items()}
    st.write(sub)

    # 모두 제출 시 추천 계산
    if room.all_submitted():
        st.success("모든 인원이 제출 완료! 추천 일정을 계산합니다.")
        # 1) 모두 'full'로만 구성된 완벽 구간
        perfect = perfect_windows_all_full(room)
        if perfect:
            st.markdown("### ✅ 전원 '하루종일 가능'으로 연속 충족하는 완벽 구간")
            for seq in perfect:
                st.write(f"- {seq[0]} ~ {seq[-1]}  ({len(seq)}일)")
        else:
            st.info("전원 완벽 구간은 없어요. 가중치 기반 최적 구간을 추천합니다.")

        # 2) 가중치 기반 상위 윈도우
        topk = best_windows(room, topk=3)
        st.markdown("### ⭐ 가중치 기반 Top-3 연속 구간 추천")
        for i, win in enumerate(topk, 1):
            feas = "충족" if win["feasible"] else "⚠️ 일부 날짜 최소 인원 미충족"
            st.write(f"**#{i} | {win['days'][0]} ~ {win['days'][-1]} | 점수 {win['score']:.2f} | {feas}**")
            with st.expander("날짜별 제안 조합 보기"):
                for d in win["days"]:
                    q = ", ".join(win["picks"][d]["quorum_pick"])
                    mx = ", ".join(win["picks"][d]["max_pick"])
                    st.write(f"- {d}: 최소인원 조합 → [{q}]  /  최대 가용 인원 조합 → [{mx}]")
    else:
        need = room.settings.num_members - sum(1 for m in room.members.values() if m.submitted)
        st.warning(f"아직 {need}명 제출 대기 중입니다. 모두 제출되면 추천을 보여줄게요.")
