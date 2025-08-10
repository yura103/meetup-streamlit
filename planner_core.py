from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import date, timedelta
import json, os

# 상태 정의
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
    by_date: Dict[str, str] = field(default_factory=dict)
    submitted: bool = False

@dataclass
class RoomSettings:
    num_members: int
    min_days: int
    start: str
    end: str
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
        if len(self.members) < self.settings.num_members:
            return False
        return sum(1 for m in self.members.values() if m.submitted) >= self.settings.num_members

# 저장소
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
            n: {"name": m.name, "by_date": m.by_date, "submitted": m.submitted}
            for n, m in room.members.items()
        }
    }
    with open(room_path(room.room_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_room(room_id: str) -> Room | None:
    p = room_path(room_id)
    if not os.path.exists(p): return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    settings = RoomSettings(**data["settings"])
    room = Room(room_id=data["room_id"], title=data["title"], creator=data["creator"], settings=settings)
    for n, m in data["members"].items():
        room.members[n] = MemberAvailability(name=m["name"], by_date=m.get("by_date", {}), submitted=m.get("submitted", False))
    return room

# 점수 계산
def day_scores(room: Room) -> Dict[str, Dict]:
    start, end, w = date.fromisoformat(room.settings.start), date.fromisoformat(room.settings.end), room.settings.weights
    out = {}
    for d in daterange(start, end):
        ds = d.isoformat()
        per_member = {n: status_to_weight(m.by_date.get(ds, "off"), w) for n, m in room.members.items()}
        out[ds] = {"total": sum(per_member.values()), "per_member": per_member}
    return out

def best_windows(room: Room, topk=3) -> List[Dict]:
    sc = day_scores(room)
    start, end = date.fromisoformat(room.settings.start), date.fromisoformat(room.settings.end)
    L, quorum, N = room.settings.min_days, room.settings.min_daily_quorum, room.settings.num_members
    days = [d.isoformat() for d in daterange(start, end)]
    wins = []
    for i in range(len(days) - L + 1):
        win_days = days[i:i+L]
        score = sum(sc[d]["total"] for d in win_days)
        picks, feasible = {}, True
        for d in win_days:
            ranked = sorted(sc[d]["per_member"].items(), key=lambda x: x[1], reverse=True)
            chosen = [n for n, w in ranked if w > 0][:max(quorum, 1)]
            if len(chosen) < quorum: feasible = False
            chosen_full = [n for n, w in ranked if w > 0][:N]
            picks[d] = {"quorum_pick": chosen, "max_pick": chosen_full}
        wins.append({"days": win_days, "score": score, "feasible": feasible, "picks": picks})
    return sorted(wins, key=lambda x: (x["feasible"], x["score"]), reverse=True)[:topk]

def perfect_windows_all_full(room: Room) -> List[List[str]]:
    start, end, L = date.fromisoformat(room.settings.start), date.fromisoformat(room.settings.end), room.settings.min_days
    days = [d.isoformat() for d in daterange(start, end)]
    def all_full(day): return all(m.by_date.get(day) == "full" for m in room.members.values())
    return [chunk for i in range(len(days)-L+1) if all(all_full(d) for d in (chunk:=days[i:i+L]))]

# 관리 유틸
def clear_member_submission(room: Room, name: str) -> bool:
    mv = room.members.get(name)
    if not mv: return False
    mv.by_date, mv.submitted = {}, False
    save_room(room); return True

def remove_member(room: Room, name: str) -> bool:
    if name in room.members:
        del room.members[name]; save_room(room); return True
    return False
