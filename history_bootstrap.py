from __future__ import annotations

import time
from datetime import date, timedelta

from config import DRAW_SCHEDULE


def history_count(store, before_date: str) -> int:
    return len(store.get_region_history("MB", before_date, 1000))


def sync_mb_history(store, source, days=240, sleep_seconds=0.12):
    """
    Backfill lịch sử MB vào SQLite/Volume.
    Chạy lại nhiều lần vẫn an toàn vì draw_history dùng upsert.
    """
    end = date.today()
    start = end - timedelta(days=days)

    ok = 0
    miss = 0
    d = start

    while d < end:
        station = DRAW_SCHEDULE["MB"][d.weekday()][0]

        try:
            rows = source.fetch("MB", d, [station])
            entry = rows.get(station)

            if entry and len(entry.get("all_prizes", [])) == 27:
                store.upsert_draw(
                    d.isoformat(),
                    "MB",
                    station,
                    entry.get("special"),
                    entry.get("all_prizes", []),
                )
                ok += 1
            else:
                miss += 1

        except Exception:
            miss += 1

        if sleep_seconds:
            time.sleep(sleep_seconds)

        d += timedelta(days=1)

    return {
        "ok": ok,
        "miss": miss,
        "count": history_count(store, date.today().isoformat()),
    }
