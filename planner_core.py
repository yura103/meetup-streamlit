from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import date, timedelta
import json, os, math

# --- 상태 정의 ---
# 'off'  : 불가(검정)
# 'full' : 하루 종일 가능(보라/분홍)
# 'am'/'pm'/'eve' : 반만 가능(초록)

WEIGHTS_DEFAULT = {"off": 0.0, "am": 0.5, "pm": 0.5, "eve": 0.5, "full": 1.0}

def daterange(d0: date, d1: date):
    cur = d0
    while cur <= d1:
        yield cur
        cur += timedelta(days=1)

def status_to_weight(status: str, weights: Dict[str, float]) -> float:
    return float(weights.get(status, 0.0))

@dataclass
class MemberAvailability:
    name: str
    # 'YYYY-MM-DD' -> status(str)
    by_date: Dict[str, str] = field(default_factory=dict)
    submitted: bool = False

@dataclass
class RoomSettings:
    num_members: int
    min_days: int
    start: str           # YYYY-MM-DD
    end: str             # YYYY-MM-DD
    min_daily_quorum: int
    weights: Dict[str, float] = field(default_factory=lambda: WEIGHTS_DEFAULT.copy())

@dataclass
class Room:
    room_id: str
    title: str
    creator: str
    settings: RoomSettings
    members: Dict[str, MemberAvailability] = field(default_factory=dict)

    def all_submitted(self) -> bool:
        # 모든 구성원이 다 들어오지 않았다면 False
        if len(self.members) < self.settings.num_members:
            return False
        # 수 지정만큼 모두 submitted?
        submitted_count = sum(1 for m in self.members.values() if m.submitted)
        return submitted_count >= self.settings.num_members

# --- 파일 저장소 (간단 JSON) ---
DATA_DIR = "rooms_data"
os.makedirs(DATA_DIR, exist_ok=True)

def room_path(room_id: str) -> str:
    return os.path.join(DATA_DIR, f"{room_id}.json")

def save_room(room: Room) -> None:
    data = {
        "room_id": room.room_id,
        "title": room.title,
        "creator": room.creator,
        "settings": {
            "num_members": room.settings.num_members,
            "min_days": room.settings.min_days,
            "start": room.settings.start,
            "end": room.settings.end,
            "min_daily_quorum": room.settings.min_daily_quorum,
            "weights": room.settings.weights
        },
        "members": {
            name: {
                "name": mv.name,
                "by_date": mv.by_date,
                "submitted": mv.submitted
            } for name, mv in room.members.items()
        }
    }
    with open(room_path(room.room_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_room(room_id: str) -> Room | None:
    p = room_path(room_id)
    if not os.path.exists(p): return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    settings = RoomSettings(
        num_members=data["settings"]["num_members"],
        min_days=data["settings"]["min_days"],
        start=data["settings"]["start"],
        end=data["settings"]["end"],
        min_daily_quorum=data["settings"]["min_daily_quorum"],
        weights=data["settings"].get("weights", WEIGHTS_DEFAULT.copy())
    )
    room = Room(
        room_id=data["room_id"],
        title=data["title"],
        creator=data["creator"],
        settings=settings,
        members={}
    )
    for name, mv in data["members"].items():
        room.members[name] = MemberAvailability(
            name=mv["name"],
            by_date=mv.get("by_date", {}),
            submitted=mv.get("submitted", False)
        )
    return room

# --- 점수 계산 ---
def day_scores(room: Room) -> Dict[str, Dict]:
    """각 날짜별 총점/세부 점수"""
    start = date.fromisoformat(room.settings.start)
    end   = date.fromisoformat(room.settings.end)
    weights = room.settings.weights

    out = {}
    for d in daterange(start, end):
        ds = d.isoformat()
        per_member = {}
        for name, mv in room.members.items():
            st = mv.by_date.get(ds, "off")
            per_member[name] = status_to_weight(st, weights)
        out[ds] = {
            "total": sum(per_member.values()),
            "per_member": per_member
        }
    return out

def best_windows(room: Room, topk: int = 3) -> List[Dict]:
    """min_days 연속 구간 중 상위 k개 추천 + 날짜별 추천 인원 조합"""
    sc = day_scores(room)
    start = date.fromisoformat(room.settings.start)
    end   = date.fromisoformat(room.settings.end)
    L     = room.settings.min_days
    quorum = room.settings.min_daily_quorum
    N = room.settings.num_members

    all_days = [d.isoformat() for d in daterange(start, end)]
    windows = []
    for i in range(0, len(all_days) - L + 1):
        win_days = all_days[i:i+L]
        # 구간 점수 = 날짜 total 합
        win_score = sum(sc[d]["total"] for d in win_days)
        # 날짜별 추천 멤버 선택: 점수 높은 순으로 최대 N명, 최소 quorum
        picks = {}
        feasible = True
        for d in win_days:
            pm = sc[d]["per_member"]
            ranked = sorted(pm.items(), key=lambda x: x[1], reverse=True)
            # quorum 이상 되는 상위 집합 (0점=불가 멤버는 제외)
            chosen = [name for name, w in ranked if w > 0][:max(quorum, 1)]
            if len(chosen) < quorum:
                feasible = False  # 이 날짜는 모일 인원이 너무 적음
            # 옵션: quorum 이상이면, 원하면 더 추가(가중치 높은 순으로 N까지)
            chosen_full = [name for name, w in ranked if w > 0][:N]
            picks[d] = {
                "quorum_pick": chosen,
                "max_pick": chosen_full
            }
        windows.append({
            "days": win_days,
            "score": win_score,
            "feasible": feasible,
            "picks": picks
        })
    # 점수+feasible 우선 정렬
    windows.sort(key=lambda x: (x["feasible"], x["score"]), reverse=True)
    return windows[:topk]

def perfect_windows_all_full(room: Room) -> List[List[str]]:
    """모든 멤버가 'full'인 날로만 이루어진 완전 구간 찾기"""
    start = date.fromisoformat(room.settings.start)
    end   = date.fromisoformat(room.settings.end)
    L     = room.settings.min_days

    seqs = []
    days = [d.isoformat() for d in daterange(start, end)]
    def all_full(day: str) -> bool:
        for mv in room.members.values():
            if mv.by_date.get(day, "off") != "full":
                return False
        return True

    for i in range(0, len(days)-L+1):
        chunk = days[i:i+L]
        if all(all_full(d) for d in chunk):
            seqs.append(chunk)
    return seqs
