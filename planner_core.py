from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import date, timedelta
import json, os

# 상태 정의 (가중치)
WEIGHTS_DEFAULT: Dict[str, float] = {
    "off": 0.0,  # 불가능
    "am": 0.5,   # 오전/오후만 가능
    "pm": 0.5,
    "full": 1.0  # 하루 가능
}

@dataclass
class Member:
    name: str
    availability: Dict[str, str] = field(default_factory=dict)  # 날짜별 상태
    submitted: bool = False

@dataclass
class Room:
    room_id: str
    host: str
    start: date
    end: date
    min_days: int
    members: Dict[str, Member] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "room_id": self.room_id,
            "host": self.host,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "min_days": self.min_days,
            "members": {
                name: {
                    "availability": m.availability,
                    "submitted": m.submitted
                } for name, m in self.members.items()
            }
        }

    @staticmethod
    def from_dict(data: Dict) -> Room:
        room = Room(
            room_id=data["room_id"],
            host=data["host"],
            start=date.fromisoformat(data["start"]),
            end=date.fromisoformat(data["end"]),
            min_days=data["min_days"],
            members={}
        )
        for name, m in data["members"].items():
            room.members[name] = Member(
                name=name,
                availability=m.get("availability", {}),
                submitted=m.get("submitted", False)
            )
        return room

# 데이터 저장 경로
ROOMS_DIR = "rooms_data"
os.makedirs(ROOMS_DIR, exist_ok=True)

def save_room(room: Room) -> None:
    """방 데이터를 JSON으로 저장"""
    path = os.path.join(ROOMS_DIR, f"{room.room_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(room.to_dict(), f, ensure_ascii=False, indent=2)

def load_room(room_id: str) -> Optional[Room]:
    """방 데이터 로드"""
    path = os.path.join(ROOMS_DIR, f"{room_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Room.from_dict(data)

def daterange(start: date, end: date):
    """날짜 범위 생성"""
    for n in range((end - start).days + 1):
        yield start + timedelta(n)

def compute_best_dates(room: Room) -> List[str]:
    """날짜별 점수를 계산하고 추천 날짜 순서 반환"""
    scores: Dict[str, float] = {}
    for d in daterange(room.start, room.end):
        date_str = d.isoformat()
        score = 0.0
        for m in room.members.values():
            state = m.availability.get(date_str, "off")
            score += WEIGHTS_DEFAULT.get(state, 0.0)
        scores[date_str] = score
    sorted_dates = sorted(scores, key=lambda k: scores[k], reverse=True)
    return sorted_dates

def perfect_windows_all_full(room: Room) -> List[List[str]]:
    """모든 인원이 최소 기간 이상 전부 가능한 연속 날짜 조합"""
    start = room.start
    end = room.end
    L = room.min_days
    days = [d.isoformat() for d in daterange(start, end)]

    def all_full(day):
        return all(m.availability.get(day) == "full" for m in room.members.values())

    result = []
    for i in range(len(days) - L + 1):
        chunk = days[i:i+L]
        if all(all_full(d) for d in chunk):
            result.append(chunk)
    return result

# 관리 유틸
def clear_member_submission(room: Room, name: str) -> bool:
    """특정 멤버의 제출 초기화"""
    mv = room.members.get(name)
    if not mv:
        return False
    mv.availability, mv.submitted = {}, False
    save_room(room)
    return True

def remove_member(room: Room, name: str) -> bool:
    """멤버 제거"""
    if name in room.members:
        del room.members[name]
        save_room(room)
        return True
    return False
