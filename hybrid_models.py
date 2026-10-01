from __future__ import annotations

NUMBERS=[f"{i:02d}" for i in range(100)]

def normalize(scores):
    mx=max(scores.values()) if scores else 1.0
    if mx<=0:
        return {n:0.0 for n in NUMBERS}
    return {n:scores.get(n,0.0)/mx for n in NUMBERS}

def mn_rank_model(history_scores_by_station):
    agg={n:0.0 for n in NUMBERS}
    stations=[s for s,v in (history_scores_by_station or {}).items() if v]
    if not stations:
        return agg
    for st in stations:
        loto=history_scores_by_station[st][0]
        ranked=sorted(NUMBERS,key=loto.get,reverse=True)
        for rank,n in enumerate(ranked):
            if rank<10:
                pts=1.00-rank*0.04
            elif rank<25:
                pts=0.60-(rank-10)*0.02
            else:
                pts=0.0
            agg[n]+=max(0.0,pts)
    for n in NUMBERS:
        agg[n]/=len(stations)
    return normalize(agg)

def mt_v24_score(station_bundles):
    out={n:0.0 for n in NUMBERS}
    count=len(station_bundles)
    for n in NUMBERS:
        vals=[b[0][n] for b in station_bundles.values()]
        mean=sum(vals)/count
        mx=max(vals) if vals else 0
        support=sum(v>=mx*0.60 and v>0 for v in vals)/count if mx else 0
        spread=max(vals)-min(vals) if vals else 0
        out[n]=0.50*mean+0.24*support+0.16*min(vals)+0.10*(1/(1+spread))
    return normalize(out)

def mb_v24_score(station_bundles):
    out={n:0.0 for n in NUMBERS}
    for n in NUMBERS:
        vals=[b[0][n] for b in station_bundles.values()]
        mean=sum(vals)/len(vals)
        spread=max(vals)-min(vals) if vals else 0
        out[n]=0.70*mean+0.18*min(vals)+0.12*(1/(1+spread))
    return normalize(out)

def choose_top2(score_map):
    return sorted(NUMBERS,key=score_map.get,reverse=True)[:2]
