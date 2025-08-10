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

import math

def _haversine(a,b):
    R=6371
    lat1,lon1=a; lat2,lon2=b
    p=math.radians
    dlat=p(lat2-lat1); dlon=p(lon2-lon1)
    x=math.sin(dlat/2)**2 + math.cos(p(lat1))*math.cos(p(lat2))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(x))

def nn_route(points):
    """points: [{'id':..,'lat':..,'lon':..}] -> index 순서 반환"""
    if not points: return []
    rem=list(range(len(points))); path=[rem.pop(0)]
    while rem:
        last=points[path[-1]]
        j=min(rem, key=lambda k:_haversine((last["lat"],last["lon"]),(points[k]["lat"],points[k]["lon"])))
        rem.remove(j); path.append(j)
    return path

def two_opt(points, order):
    improved=True
    while improved:
        improved=False
        for i in range(1,len(order)-2):
            for j in range(i+1,len(order)-1):
                a,b=order[i-1],order[i]
                c,d=order[j],order[j+1]
                dab=_haversine((points[a]["lat"],points[a]["lon"]),(points[b]["lat"],points[b]["lon"]))
                dcd=_haversine((points[c]["lat"],points[c]["lon"]),(points[d]["lat"],points[d]["lon"]))
                dac=_haversine((points[a]["lat"],points[a]["lon"]),(points[c]["lat"],points[c]["lon"]))
                dbd=_haversine((points[b]["lat"],points[b]["lon"]),(points[d]["lat"],points[d]["lon"]))
                if dac+dbd < dab+dcd - 1e-6:
                    order[i:j+1]=reversed(order[i:j+1]); improved=True
    return order

def optimize_route(items):
    pts=[{"id":it["id"],"lat":it["lat"],"lon":it["lon"],"is_anchor":it["is_anchor"]} for it in items if it["lat"] and it["lon"]]
    if len(pts)<2: return [it["id"] for it in items]
    anchors=[i for i,p in enumerate(pts) if p["is_anchor"]]
    start_idx = anchors[0] if anchors else 0
    pts[0], pts[start_idx] = pts[start_idx], pts[0]
    order = nn_route(pts)
    order = two_opt(pts, order+[order[0]])[:-1]
    ids_order=[pts[i]["id"] for i in order]
    # anchor를 맨앞/맨뒤로 고정하려면 여기서 조정 가능
    return ids_order