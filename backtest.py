from __future__ import annotations
import argparse,json,math
from datetime import date,timedelta
from config import DRAW_SCHEDULE
from storage import Storage
from history_features import build_history_scores
from scoring import station_score_bundle, aggregate_region

def last2(x):
    s="".join(c for c in str(x) if c.isdigit())
    return s[-2:].zfill(2) if s else "00"

def daterange(a,b):
    d=a
    while d<=b:
        yield d
        d+=timedelta(days=1)

def baseline(k):
    k=max(0,min(100,k))
    if k>=99:return 1.0
    return 1-math.comb(100-k,2)/math.comb(100,2)

def eval_period(store,region,start,end):
    days=hit=both=zero=0
    dbhits=dbtrials=0
    basesum=0.0

    for d in daterange(start,end):
        stations=DRAW_SCHEDULE[region][d.weekday()]
        bundles={}
        hist_map={}
        actual={}
        ok=True

        with store.connect() as con:
            for st in stations:
                hist=store.get_history(region,st,d.isoformat(),365)
                if len(hist)<12:
                    ok=False;break
                hs=build_history_scores(hist)
                hist_map[st]=hs
                bundles[st]=station_score_bundle({},hs,None,region=region)

                row=con.execute(
                    "SELECT * FROM draw_history WHERE region=? AND station=? AND draw_date=?",
                    (region,st,d.isoformat())
                ).fetchone()
                if not row:
                    ok=False;break
                actual[st]=dict(row)

        if not ok:
            continue

        stl,db50,_=aggregate_region(
            bundles,None,0,region=region,
            history_scores_by_station=hist_map
        )

        actual_unique=set()
        for st,row in actual.items():
            prizes=json.loads(row["prizes_json"])
            actual_unique.update(last2(x) for x in prizes)

        h={n for n in stl if n in actual_unique}
        days+=1
        hit+=int(len(h)>=1)
        both+=int(len(h)==2)
        zero+=int(len(h)==0)
        basesum+=baseline(len(actual_unique))

        for st,row in actual.items():
            sp=last2(row["special"]) if row["special"] else None
            dbtrials+=1
            if sp:
                dbhits+=int(sp in db50)

    m=hit/days if days else None
    b=basesum/days if days else None
    dbr=dbhits/dbtrials if dbtrials else None

    return {
        "days":days,
        "song_thu_day_hit_rate":round(m,4) if m is not None else None,
        "random_pair_baseline_hit_rate":round(b,4) if b is not None else None,
        "song_thu_edge_vs_random":round(m-b,4) if m is not None and b is not None else None,
        "song_thu_both_hit_rate":round(both/days,4) if days else None,
        "song_thu_zero_hit_rate":round(zero/days,4) if days else None,
        "db50_hit_rate":round(dbr,4) if dbr is not None else None,
        "db50_edge_vs_random":round(dbr-0.5,4) if dbr is not None else None,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--region",choices=["MN","MT","MB"],required=True)
    ap.add_argument("--db",default="data/lottery_v2.sqlite3")
    args=ap.parse_args()

    store=Storage(args.db)
    result={
        "region":args.region,
        "model":"V2.6 hybrid",
        "train":eval_period(store,args.region,date(2026,4,1),date(2026,5,31)),
        "validation":eval_period(store,args.region,date(2026,6,1),date(2026,7,31)),
        "test":eval_period(store,args.region,date(2026,8,1),date(2026,9,29)),
    }
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
