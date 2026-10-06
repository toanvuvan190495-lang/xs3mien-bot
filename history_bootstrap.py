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



def existing_history_dates(store, before_date: str, limit=1000):
    rows = store.get_region_history("MB", before_date, limit)
    return {r.get("draw_date") for r in rows if r.get("draw_date")}


def recent_history_status(store, lookback_days=10, include_today=False):
    """
    Kiểm tra coverage các ngày gần nhất.
    Mặc định bỏ hôm nay vì hôm nay được lưu qua settlement.
    """
    end = date.today()
    last_day = end if include_today else end - timedelta(days=1)
    first_day = last_day - timedelta(days=lookback_days - 1)

    existing = existing_history_dates(
        store,
        (end + timedelta(days=1)).isoformat()
        if include_today
        else end.isoformat(),
        max(lookback_days + 30, 60),
    )

    days = []
    d = first_day
    while d <= last_day:
        days.append({
            "date": d.isoformat(),
            "exists": d.isoformat() in existing,
        })
        d += timedelta(days=1)

    return days


def repair_recent_history(
    store,
    source,
    lookback_days=10,
    include_today=False,
    sleep_seconds=0.10,
):
    """
    Chỉ fetch những ngày gần đây còn thiếu.
    Không phụ thuộc tổng số dòng history đang có.

    Nếu include_today=False:
      - dùng cho startup/00:10, vá các ngày đã qua.
    Nếu include_today=True:
      - có thể dùng thủ công; ngày hiện tại vẫn chịu Result Guard của source.
    """
    status = recent_history_status(
        store,
        lookback_days=lookback_days,
        include_today=include_today,
    )

    missing = [x["date"] for x in status if not x["exists"]]
    repaired = []
    failed = []

    for ds in missing:
        d = date.fromisoformat(ds)
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
                repaired.append(ds)
            else:
                failed.append(ds)

        except Exception:
            failed.append(ds)

        if sleep_seconds:
            time.sleep(sleep_seconds)

    final_status = recent_history_status(
        store,
        lookback_days=lookback_days,
        include_today=include_today,
    )

    return {
        "missing_before": missing,
        "repaired": repaired,
        "failed": failed,
        "status": final_status,
        "count": history_count(store, date.today().isoformat()),
    }
