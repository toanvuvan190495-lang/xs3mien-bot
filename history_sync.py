from __future__ import annotations
import argparse, time
from datetime import date, timedelta

from config import settings, DRAW_SCHEDULE
from storage import Storage
from free_results import FreeResultSource

def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-date", required=True)
    ap.add_argument("--to-date", required=True)
    ap.add_argument("--regions", default="MN,MT,MB")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    store = Storage(settings.db_path)
    src = FreeResultSource(settings.web_timeout)
    regions = [x.strip() for x in args.regions.split(",")]
    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)

    ok = err = 0
    for d in daterange(start, end):
        for region in regions:
            stations = DRAW_SCHEDULE[region][d.weekday()]
            try:
                res = src.fetch(region, d, stations)
                for st, e in res.items():
                    store.upsert_draw(d.isoformat(), region, st, e.get("special"), e.get("all_prizes", []))
                print(d, region, "stations", len(res))
                ok += int(bool(res))
            except Exception as e:
                print("ERR", d, region, type(e).__name__, e)
                err += 1
            time.sleep(args.sleep)

    print("DONE ok=", ok, "err=", err)

if __name__ == "__main__":
    main()
