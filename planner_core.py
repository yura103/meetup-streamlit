from typing import List, Dict
import datetime as dt

def daterange(d0: str, d1: str):
    a = dt.date.fromisoformat(d0); b = dt.date.fromisoformat(d1)
    cur = a
    while cur <= b:
        yield cur.isoformat()
        cur += dt.timedelta(days=1)

def best_windows(days: List[str], agg: Dict[str, dict], min_days: int, quorum: int) -> List[dict]:
    wins = []
    for i in range(0, len(days)-min_days+1):
        chunk = days[i:i+min_days]
        score = sum(agg[d]["score"] for d in chunk)
        feasible = all(
            (agg[d]["full"]+agg[d]["am"]+agg[d]["pm"]+agg[d]["eve"]) >= quorum
            for d in chunk
        )
        wins.append({"days": chunk, "score": round(score,2), "feasible": feasible})
    wins.sort(key=lambda x: (x["feasible"], x["score"]), reverse=True)
    return wins[:3]