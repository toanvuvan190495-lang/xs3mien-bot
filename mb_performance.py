from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from db45_combo import prediction_combo, DB45_STAKE_PER_NUMBER, DB45_PAYOUT_IF_HIT

# SONG THỦ
LOTO_HIT_PAYOUT = 990_000
LOTO_STAKE_PER_NUMBER = 270_000
LOTO_NUMBERS_PER_DAY = 2
LOTO_DAILY_STAKE = LOTO_STAKE_PER_NUMBER * LOTO_NUMBERS_PER_DAY  # 540k

# ĐB64
DB64_DAILY_STAKE = 640_000
DB64_HIT_PAYOUT = 990_000

TOTAL_DAILY_STAKE = LOTO_DAILY_STAKE + DB64_DAILY_STAKE  # 1.180m


def _money(v: int) -> str:
    sign = "+" if v > 0 else ""
    return f"{sign}{int(v):,}đ".replace(",", ".")


class MBPerformance:
    def __init__(self, db_path: str):
        base = Path(db_path).expanduser().resolve().parent
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "mb_performance.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {"days": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"days": {}}
            data.setdefault("days", {})
            return data
        except Exception:
            return {"days": {}}

    def _save(self, data: dict):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def record(self, draw_date: str, prediction: dict, loto_hits: dict, db_hits: dict):
        # Song thủ
        total_loto_hits = sum(
            int(v.get("total", 0)) for v in (loto_hits or {}).values()
        )
        loto_payout = total_loto_hits * LOTO_HIT_PAYOUT
        loto_capital = LOTO_DAILY_STAKE
        loto_net = loto_payout - loto_capital

        # ĐB64 - MB chỉ có 1 đài mỗi ngày
        db_stations = (
            db_hits.get("stations", {}) if isinstance(db_hits, dict) else {}
        )
        db_hit = int(db_hits.get("hits", 0)) > 0 if isinstance(db_hits, dict) else False
        db_payout = DB64_HIT_PAYOUT if db_hit else 0
        db_capital = DB64_DAILY_STAKE
        db_net = db_payout - db_capital

        special = None
        special_last2 = None
        for _, info in db_stations.items():
            special = info.get("special")
            special_last2 = info.get("last2")
            break

        # DÀN GHÉP 4×5: chỉ tính tiền cho dự đoán có dàn được chốt
        # (không gán vốn hoặc hồi tố kết quả cho những ngày V4.1 cũ).
        combo = prediction_combo(prediction)
        combo_numbers = list(combo.get("numbers", []))
        combo_enabled = bool(combo_numbers)
        combo_capital = len(combo_numbers) * DB45_STAKE_PER_NUMBER if combo_enabled else 0
        combo_hit = bool(combo_enabled and special_last2 in set(combo_numbers))
        combo_payout = DB45_PAYOUT_IF_HIT if combo_hit else 0
        combo_net = combo_payout - combo_capital

        total_payout = loto_payout + db_payout + combo_payout
        total_capital = loto_capital + db_capital + combo_capital
        total_net = total_payout - total_capital

        record = {
            "date": draw_date,
            "song_thu": list(prediction.get("song_thu") or []),
            "db64": list(prediction.get("db50") or [])[:64],

            "loto_hits": loto_hits or {},
            "total_loto_hits": total_loto_hits,
            "loto_payout": loto_payout,
            "loto_capital": loto_capital,
            "loto_net": loto_net,

            "db64_hit": bool(db_hit),
            "db64_payout": db_payout,
            "db64_capital": db_capital,
            "db64_net": db_net,
            "db45_enabled": combo_enabled,
            "db45_numbers": combo_numbers,
            "db45_count": len(combo_numbers),
            "db45_hit": combo_hit,
            "db45_capital": combo_capital,
            "db45_payout": combo_payout,
            "db45_net": combo_net,
            "special": special,
            "special_last2": special_last2,

            "total_payout": total_payout,
            "total_capital": total_capital,
            "total_net": total_net,
        }

        data = self._load()
        data["days"][draw_date] = record
        self._save(data)
        return record

    def get_day(self, draw_date: str):
        return self._load().get("days", {}).get(draw_date)

    def week(self, ref_date: date):
        start = ref_date - timedelta(days=ref_date.weekday())
        end = start + timedelta(days=6)

        all_days = self._load().get("days", {})
        rows = []

        d = start
        while d <= end:
            key = d.isoformat()
            if key in all_days:
                rows.append(all_days[key])
            d += timedelta(days=1)

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": rows,
            "settled_days": len(rows),

            "loto_hits": sum(int(r.get("total_loto_hits", 0)) for r in rows),
            "loto_payout": sum(int(r.get("loto_payout", 0)) for r in rows),
            "loto_capital": sum(int(r.get("loto_capital", LOTO_DAILY_STAKE)) for r in rows),

            "db64_wins": sum(int(bool(r.get("db64_hit", False))) for r in rows),
            "db64_payout": sum(int(r.get("db64_payout", 0)) for r in rows),
            "db64_capital": sum(int(r.get("db64_capital", DB64_DAILY_STAKE)) for r in rows),

            "db45_days": sum(int(bool(r.get("db45_enabled", False))) for r in rows),
            "db45_wins": sum(int(bool(r.get("db45_hit", False))) for r in rows),
            "db45_payout": sum(int(r.get("db45_payout", 0)) for r in rows),
            "db45_capital": sum(int(r.get("db45_capital", 0)) for r in rows),

            "total_payout": sum(int(r.get("total_payout", 0)) for r in rows),
            "total_capital": sum(int(r.get("total_capital", TOTAL_DAILY_STAKE)) for r in rows),
        }



    def month(self, ref_date: date):
        start = ref_date.replace(day=1)

        # Xác định ngày cuối tháng.
        if ref_date.month == 12:
            next_month = ref_date.replace(
                year=ref_date.year + 1,
                month=1,
                day=1,
            )
        else:
            next_month = ref_date.replace(
                month=ref_date.month + 1,
                day=1,
            )

        end = next_month - timedelta(days=1)

        all_days = self._load().get("days", {})
        rows = []

        d = start
        while d <= end:
            key = d.isoformat()
            if key in all_days:
                rows.append(all_days[key])
            d += timedelta(days=1)

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": rows,
            "settled_days": len(rows),

            "loto_hits": sum(
                int(r.get("total_loto_hits", 0))
                for r in rows
            ),
            "loto_payout": sum(
                int(r.get("loto_payout", 0))
                for r in rows
            ),
            "loto_capital": sum(
                int(r.get("loto_capital", LOTO_DAILY_STAKE))
                for r in rows
            ),

            "db64_wins": sum(
                int(bool(r.get("db64_hit", False)))
                for r in rows
            ),
            "db64_payout": sum(
                int(r.get("db64_payout", 0))
                for r in rows
            ),
            "db64_capital": sum(
                int(r.get("db64_capital", DB64_DAILY_STAKE))
                for r in rows
            ),

            "db45_days": sum(int(bool(r.get("db45_enabled", False))) for r in rows),
            "db45_wins": sum(int(bool(r.get("db45_hit", False))) for r in rows),
            "db45_payout": sum(int(r.get("db45_payout", 0)) for r in rows),
            "db45_capital": sum(int(r.get("db45_capital", 0)) for r in rows),

            "total_payout": sum(
                int(r.get("total_payout", 0))
                for r in rows
            ),
            "total_capital": sum(
                int(r.get("total_capital", TOTAL_DAILY_STAKE))
                for r in rows
            ),
        }


def format_result(record: dict) -> str:
    loto_net = record["loto_net"]
    db_net = record["db64_net"]
    total_net = record["total_net"]

    lines = [
        "✅ <b>KẾT QUẢ MIỀN BẮC</b>",
        f"📅 {record['date']}",
        "",

        f"🔥 <b>SONG THỦ: {' – '.join(record.get('song_thu', []))}</b>",
    ]

    for n, item in (record.get("loto_hits") or {}).items():
        lines.append(f"• {n}: <b>{int(item.get('total', 0))} nháy</b>")

    lines += [
        f"🎯 Ngày: <b>về {record['total_loto_hits']} nháy</b>",
        f"💰 Nhận: <b>{_money(record['loto_payout'])}</b>",
        f"💸 Vốn STL: <b>{_money(record['loto_capital'])}</b>",
        f"📈 STL lãi/lỗ: <b>{_money(loto_net)}</b>",
        "",

        f"🎯 <b>ĐB64: {'✅ TRÚNG' if record['db64_hit'] else '❌ TRƯỢT'}</b>",
        f"🏆 KQ ĐB: <b>{record.get('special') or '-'} → {record.get('special_last2') or '-'}</b>",
        f"💰 Nhận ĐB64: <b>{_money(record['db64_payout'])}</b>",
        f"💸 Vốn ĐB64: <b>{_money(record['db64_capital'])}</b>",
        f"📈 ĐB64 lãi/lỗ: <b>{_money(db_net)}</b>",
        "",

        *_db45_result_lines(record),

        "━━━━━━━━━━━━━━",
        f"💼 Tổng vốn ngày: <b>{_money(record['total_capital'])}</b>",
        f"💵 Tổng nhận: <b>{_money(record['total_payout'])}</b>",
        f"📊 Tổng lãi/lỗ: <b>{_money(total_net)}</b>",
    ]

    return "\n".join(lines)


def format_daily(record: dict | None, draw_date: str) -> str:
    if not record:
        return (
            "📊 <b>TỔNG KẾT MIỀN BẮC NGÀY</b>\n"
            f"📅 {draw_date}\n\n"
            "⏳ Chưa có dữ liệu đối soát hoàn chỉnh."
        )

    return "\n".join([
        "📊 <b>TỔNG KẾT MIỀN BẮC NGÀY</b>",
        f"📅 {draw_date}",
        "",

        f"🔥 Song thủ: <b>{' – '.join(record.get('song_thu', []))}</b>",
        f"🎯 Ngày: <b>về {record['total_loto_hits']} nháy</b>",
        f"💰 STL nhận: <b>{_money(record['loto_payout'])}</b>",
        f"💸 STL vốn: <b>{_money(record['loto_capital'])}</b>",
        f"📈 STL lãi/lỗ: <b>{_money(record['loto_net'])}</b>",
        "",

        f"🎯 ĐB64: <b>{'✅ TRÚNG' if record['db64_hit'] else '❌ TRƯỢT'}</b>",
        f"🏆 Giải ĐB: <b>{record.get('special') or '-'} → {record.get('special_last2') or '-'}</b>",
        f"💰 ĐB64 nhận: <b>{_money(record['db64_payout'])}</b>",
        f"💸 ĐB64 vốn: <b>{_money(record['db64_capital'])}</b>",
        f"📈 ĐB64 lãi/lỗ: <b>{_money(record['db64_net'])}</b>",
        "",

        *_db45_result_lines(record),

        "━━━━━━━━━━━━━━",
        f"💼 Tổng vốn: <b>{_money(record['total_capital'])}</b>",
        f"💵 Tổng nhận: <b>{_money(record['total_payout'])}</b>",
        f"📊 Tổng lãi/lỗ ngày: <b>{_money(record['total_net'])}</b>",
    ])


def format_weekly(summary: dict) -> str:
    lines = [
        "📆 <b>TỔNG KẾT TUẦN MIỀN BẮC</b>",
        f"🗓 {summary['start']} → {summary['end']}",
        "",
    ]

    rows = summary.get("days", [])
    if not rows:
        lines.append("Chưa có dữ liệu đối soát trong tuần.")
        return "\n".join(lines)

    for r in rows:
        lines.append(
            f"• {r['date']}: STL {r.get('total_loto_hits', 0)} nháy"
            f" | ĐB64 {'✅' if r.get('db64_hit') else '❌'}"
            + (f" | ĐB ghép {'✅' if r.get('db45_hit') else '❌'}"
               if r.get('db45_enabled') else "")
        )

    loto_net = summary["loto_payout"] - summary["loto_capital"]
    db_net = summary["db64_payout"] - summary["db64_capital"]
    total_net = summary["total_payout"] - summary["total_capital"]

    lines += [
        "",
        f"🔥 Song thủ tuần: <b>về {summary['loto_hits']} nháy</b>",
        f"💰 STL nhận: <b>{_money(summary['loto_payout'])}</b>",
        f"💸 STL vốn: <b>{_money(summary['loto_capital'])}</b>",
        f"📈 STL lãi/lỗ: <b>{_money(loto_net)}</b>",
        "",

        f"🎯 ĐB64 tuần: <b>trúng {summary['db64_wins']}/{summary['settled_days']} ngày</b>",
        f"💰 ĐB64 nhận: <b>{_money(summary['db64_payout'])}</b>",
        f"💸 ĐB64 vốn: <b>{_money(summary['db64_capital'])}</b>",
        f"📈 ĐB64 lãi/lỗ: <b>{_money(db_net)}</b>",
        "",

        *_db45_summary_lines(summary),

        "━━━━━━━━━━━━━━",
        f"📌 Số ngày đã đối soát: <b>{summary['settled_days']}</b>",
        f"💼 Tổng vốn tuần: <b>{_money(summary['total_capital'])}</b>",
        f"💵 Tổng nhận tuần: <b>{_money(summary['total_payout'])}</b>",
        f"📊 Tổng lãi/lỗ tuần: <b>{_money(total_net)}</b>",
        "",
        "<i>Quy ước: STL 270.000đ/số/ngày × 2 số; "
        "1 nháy nhận 990.000đ. ĐB64 vốn 640.000đ/ngày; "
        "trúng nhận 990.000đ. ĐB ghép: 10.000đ/số đã chốt; "
        "trúng nhận 990.000đ; không tính ngày chưa triển khai.</i>",
    ]

    return "\n".join(lines)
def format_monthly(summary: dict) -> str:
    lines = [
        "🗓 <b>TỔNG KẾT THÁNG MIỀN BẮC</b>",
        f"📅 {summary['start']} → {summary['end']}",
        "",
    ]

    rows = summary.get("days", [])
    if not rows:
        lines.append("Chưa có dữ liệu đối soát trong tháng.")
        return "\n".join(lines)

    # Hiển thị theo từng ngày nhưng giữ gọn.
    for r in rows:
        lines.append(
            f"• {r['date']}: STL {r.get('total_loto_hits', 0)} nháy"
            f" | ĐB64 {'✅' if r.get('db64_hit') else '❌'}"
            + (f" | ĐB ghép {'✅' if r.get('db45_hit') else '❌'}"
               if r.get('db45_enabled') else "")
        )

    loto_net = summary["loto_payout"] - summary["loto_capital"]
    db_net = summary["db64_payout"] - summary["db64_capital"]
    total_net = summary["total_payout"] - summary["total_capital"]

    lines += [
        "",
        f"🔥 Song thủ tháng: <b>về {summary['loto_hits']} nháy</b>",
        f"💰 STL nhận: <b>{_money(summary['loto_payout'])}</b>",
        f"💸 STL vốn: <b>{_money(summary['loto_capital'])}</b>",
        f"📈 STL lãi/lỗ: <b>{_money(loto_net)}</b>",
        "",

        f"🎯 ĐB64 tháng: <b>trúng {summary['db64_wins']}/{summary['settled_days']} ngày</b>",
        f"💰 ĐB64 nhận: <b>{_money(summary['db64_payout'])}</b>",
        f"💸 ĐB64 vốn: <b>{_money(summary['db64_capital'])}</b>",
        f"📈 ĐB64 lãi/lỗ: <b>{_money(db_net)}</b>",
        "",

        *_db45_summary_lines(summary),

        "━━━━━━━━━━━━━━",
        f"📌 Số ngày đã đối soát: <b>{summary['settled_days']}</b>",
        f"💼 Tổng vốn tháng: <b>{_money(summary['total_capital'])}</b>",
        f"💵 Tổng nhận tháng: <b>{_money(summary['total_payout'])}</b>",
        f"📊 Tổng lãi/lỗ tháng: <b>{_money(total_net)}</b>",
        "",
        "<i>Quy ước: STL 270.000đ/số/ngày × 2 số; "
        "1 nháy nhận 990.000đ. ĐB64 vốn 640.000đ/ngày; "
        "trúng nhận 990.000đ. ĐB ghép: 10.000đ/số đã chốt; "
        "trúng nhận 990.000đ; không tính ngày chưa triển khai.</i>",
    ]

    return "\n".join(lines)



def _db45_result_lines(record):
    if not record.get("db45_enabled"):
        return ["🧩 <b>ĐB GHÉP 4×5:</b> — chưa có dàn ở kỳ này", ""]
    return [
        f"🧩 <b>ĐB GHÉP 4×5: {'✅ TRÚNG' if record.get('db45_hit') else '❌ TRƯỢT'}</b>",
        f"🔢 Dàn {record.get('db45_count', 0)} số: "
        + " ".join(record.get("db45_numbers", [])),
        f"💸 Vốn ĐB ghép: <b>{_money(record.get('db45_capital', 0))}</b>",
        f"💰 Nhận ĐB ghép: <b>{_money(record.get('db45_payout', 0))}</b>",
        f"📈 ĐB ghép lãi/lỗ: <b>{_money(record.get('db45_net', 0))}</b>",
        "",
    ]


def _db45_summary_lines(summary):
    days = int(summary.get("db45_days", 0))
    if days <= 0:
        return ["🧩 <b>ĐB GHÉP 4×5:</b> Chưa có ngày dự đoán", ""]
    wins = int(summary.get('db45_wins', 0))
    cap = int(summary.get('db45_capital', 0))
    paid = int(summary.get('db45_payout', 0))
    return [
        f"🧩 ĐB ghép 4×5: <b>trúng {wins}/{days} ngày có dàn</b>",
        f"💸 Vốn ĐB ghép: <b>{_money(cap)}</b>",
        f"💰 Nhận ĐB ghép: <b>{_money(paid)}</b>",
        f"📈 ĐB ghép lãi/lỗ: <b>{_money(paid - cap)}</b>",
        "",
    ]


def format_db45_daily(record, draw_date):
    lines = ["🧩 <b>KẾT QUẢ ĐB GHÉP 4×5</b>", f"📅 {draw_date}", ""]
    if record is None:
        lines.append("⏳ Chưa có kết quả được đối soát.")
    elif not record.get("db45_enabled"):
        lines.append("— Kỳ này chưa có dàn ghép được chốt (không tính tiền).")
    else:
        lines.append(f"🏆 Đặc biệt: <b>{record.get('special') or '—'}</b> → {record.get('special_last2') or '—'}")
        lines.extend(_db45_result_lines(record))
    return "\n".join(lines)


def format_db45_period(summary, label):
    lines = [
        f"🧩 <b>TỔNG KẾT ĐB GHÉP 4×5 - {label}</b>",
        f"📅 {summary['start']} → {summary['end']}", "",
    ]
    for row in summary.get("days", []):
        if row.get("db45_enabled"):
            lines.append(
                f"• {row['date']}: {row.get('db45_count', 0)} số "
                f"| {'✅' if row.get('db45_hit') else '❌'} "
                f"| {_money(row.get('db45_net', 0))}"
            )
    lines.extend(["", *_db45_summary_lines(summary)])
    lines.append("<i>10.000đ/số · ĐB trúng nhận 990.000đ. "
                 "Chỉ thống kê các kỳ có dàn ghép được chốt.</i>")
    return "\n".join(lines)
