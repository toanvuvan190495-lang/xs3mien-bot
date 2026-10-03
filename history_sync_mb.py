from __future__ import annotations

import sys
from datetime import date, timedelta

from config import settings, DRAW_SCHEDULE
from free_results import FreeResultSource
from storage import Storage


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 180

    store = Storage(settings.db_path)
    source = FreeResultSource(settings.web_timeout)

    end = date.today()
    start = end - timedelta(days=days)

    ok = 0
    fail = 0
    d = start

    while d < end:
        station = DRAW_SCHEDULE["MB"][d.weekday()][0]

        try:
            result = source.fetch("MB", d, [station])
            if station in result:
                entry = result[station]
                store.upsert_draw(
                    d.isoformat(),
                    "MB",
                    station,
                    entry.get("special"),
                    entry.get("all_prizes", []),
                )
                ok += 1
                print("OK", d, station)
            else:
                fail += 1
                print("MISS", d, station)
        except Exception as e:
            fail += 1
            print("ERR", d, type(e).__name__, e)

        d += timedelta(days=1)

    print(f"DONE ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
