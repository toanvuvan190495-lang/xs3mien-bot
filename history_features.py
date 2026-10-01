from __future__ import annotations
from collections import Counter
import statistics

NUMBERS=[f"{i:02d}" for i in range(100)]

def last2(x):
    s="".join(ch for ch in str(x) if ch.isdigit())
    return s[-2:].zfill(2) if s else "00"

def build_history_scores(rows):
    """
    rows: newest first. Feature strictly from earlier draws.
    Returns normalized-ish raw values 0..1.
    """
    loto_series=[]
    db_series=[]
    for r in rows:
        vals=[last2(x) for x in r.get("prizes",[])]
        loto_series.extend(vals)
        if r.get("special") is not None:db_series.append(last2(r["special"]))

    def freq_score(series, take):
        c=Counter(series[:take])
        mx=max(c.values()) if c else 1
        return {n:c.get(n,0)/mx for n in NUMBERS}

    f30=freq_score(loto_series, max(1,30*18))
    f90=freq_score(loto_series, max(1,90*18))
    db30=freq_score(db_series,30)
    db90=freq_score(db_series,90)

    # Gap: kỳ kể từ lần xuất hiện cuối (capped). Gap trung bình vừa phải được chấm tốt,
    # tránh mặc định "gan lâu sẽ về" là quy luật.
    gaps={}
    for n in NUMBERS:
        try:g=loto_series.index(n)
        except ValueError:g=999
        gaps[n]=min(g,120)
    maxg=max(gaps.values()) or 1
    gap_score={n:1-(abs((gaps[n]/maxg)-0.35)) for n in NUMBERS}
    gap_score={n:max(0.0,min(1.0,v)) for n,v in gap_score.items()}

    loto={n:0.48*f30[n]+0.34*f90[n]+0.18*gap_score[n] for n in NUMBERS}
    db={n:0.58*db30[n]+0.42*db90[n] for n in NUMBERS}
    return loto,db
