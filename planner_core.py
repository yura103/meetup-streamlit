# planner_core.py
from typing import List, Dict
import datetime as dt

def daterange(d0: str, d1: str):
    a = dt.date.fromisoformat(d0); b = dt.date.fromisoformat(d1)
    cur = a
    while cur <= b:
        yield cur.isoformat()
        cur += dt.timedelta(days=1)

def best_windows(days: List[str], agg: Dict[str, dict], min_days: int, quorum: int) -> List[dict]:
    """연속 min_days 창에서 점수 합이 큰 상위 3개 + quorum 충족 여부"""
    wins = []
    for i in range(0, len(days)-min_days+1):
        chunk = days[i:i+min_days]
        score = sum(agg[d]["score"] for d in chunk)
        feasible = True
        for d in chunk:
            avail_cnt = agg[d]["full"] + agg[d]["am"] + agg[d]["pm"] + agg[d]["eve"]
            if avail_cnt < quorum:
                feasible = False
        wins.append({"days": chunk, "score": round(score,2), "feasible": feasible})
    wins.sort(key=lambda x: (x["feasible"], x["score"]), reverse=True)
    return wins[:3]