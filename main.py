from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from config import settings, PREDICT_CRON, REGION_NAMES
from storage import Storage
from engine import PredictionEngine
from settlement import settle
from messages import format_prediction
from mb_performance import MBPerformance, format_result, format_daily, format_weekly, format_monthly
from history_bootstrap import (
    history_count,
    sync_mb_history,
    recent_history_status,
    repair_recent_history,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("xsmb_final")

store = Storage(settings.db_path)
engine = PredictionEngine(store)
performance = MBPerformance(settings.db_path)

TZ = ZoneInfo(settings.timezone)
application: Application | None = None


def now():
    return datetime.now(TZ)


def today():
    return now().date()


async def reply(update: Update, text: str):
    if update.effective_message:
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def send(text: str):
    if not application or not settings.telegram_chat_id:
        log.info("TELEGRAM DISABLED\n%s", text)
        return

    await application.bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def predict_mb_now():
    d = today()
    p = await asyncio.to_thread(engine.predict_region, "MB", d)
    store.save_prediction(p)
    return p


async def predict_job():
    try:
        p = await predict_mb_now()
        await send(format_prediction(p))
    except Exception:
        log.exception("Prediction failed MB")



async def _settle_prediction(p, d, results, notify=True):
    complete, loto_hits, db_hits = settle(p, results)

    if not complete:
        return False

    existing = performance.get_day(d.isoformat())

    await asyncio.to_thread(engine.ingest_results, "MB", d, results)

    store.save_settlement(
        d.isoformat(), "MB", results, loto_hits, db_hits
    )

    # Chỉ chấm reliability nguồn lần đầu để tránh mỗi lần recheck lại cộng trial.
    if not existing:
        store.update_source_performance(
            d.isoformat(), "MB", results
        )

    record = performance.record(
        d.isoformat(), p, loto_hits, db_hits
    )

    changed = False
    if existing:
        changed = (
            existing.get("special") != record.get("special")
            or int(existing.get("total_loto_hits", 0))
               != int(record.get("total_loto_hits", 0))
            or bool(existing.get("db64_hit", False))
               != bool(record.get("db64_hit", False))
        )

    if notify:
        if not existing:
            await send(format_result(record))
        elif changed:
            await send(
                "♻️ <b>KẾT QUẢ HÔM NAY ĐÃ ĐƯỢC SỬA SAU KHI XÁC MINH NGUỒN</b>\n\n"
                + format_result(record)
            )

    return True


async def settlement_poll():
    d = today()

    # Luôn recheck prediction hôm nay tới 19:58, kể cả đã settle.
    # Nếu một nguồn trước đó bị sai/ngày cũ, bản ghi đúng sẽ tự ghi đè.
    p = store.get_prediction(d.isoformat(), "MB")
    if not p:
        return

    try:
        results = await asyncio.to_thread(
            engine.fetch_results, "MB", d
        )

        source = getattr(engine.results, "last_source", None)
        errors = getattr(engine.results, "last_errors", [])

        if not results:
            log.info(
                "MB exact-date result not verified yet. tried=%s",
                " | ".join(errors[-4:]) if errors else "unknown"
            )
            return

        ok = await _settle_prediction(
            p, d, results, notify=True
        )

        if ok:
            log.info(
                "MB settlement verified/corrected. source=%s",
                source or "unknown"
            )
        else:
            log.info(
                "MB fetched but failed hard settlement validation. source=%s",
                source or "unknown",
            )

    except Exception:
        log.exception("Settlement failed MB")


async def daily_summary_job():
    d = today()
    await send(
        format_daily(
            performance.get_day(d.isoformat()),
            d.isoformat(),
        )
    )


async def weekly_summary_job():
    d = today()
    await send(format_weekly(performance.week(d)))


async def monthly_summary_job():
    d = today()
    await send(format_monthly(performance.month(d)))



async def ensure_history_background():
    """
    1) Luôn vá các ngày gần đây bị thiếu.
    2) Chỉ full-backfill 240 ngày nếu tổng lịch sử còn quá ít.
    """
    try:
        recent = await asyncio.to_thread(
            repair_recent_history,
            store,
            engine.results,
            10,
            False,
            0.10,
        )

        if recent["repaired"]:
            log.info(
                "Recent MB history repaired: %s",
                ", ".join(recent["repaired"]),
            )

        if recent["failed"]:
            log.info(
                "Recent MB history still missing: %s",
                ", ".join(recent["failed"]),
            )

        count = history_count(store, today().isoformat())
        log.info("MB history rows after recent repair: %s", count)

        if count >= 120:
            return

        await send(
            f"📚 Lịch sử MB hiện có <b>{count} kỳ</b>. "
            "Bot đang tự đồng bộ thêm lịch sử."
        )

        result = await asyncio.to_thread(
            sync_mb_history,
            store,
            engine.results,
            240,
            0.12,
        )

        log.info("History full sync result: %s", result)

        await send(
            "✅ Đồng bộ lịch sử MB xong.\n"
            f"Lấy được: <b>{result['ok']}</b> kỳ\n"
            f"Tổng lịch sử hiện có: <b>{result['count']}</b> kỳ"
        )

    except Exception:
        log.exception("Background history maintenance failed")


async def recent_history_repair_job():
    """
    Chạy 00:10 hằng ngày để vá các ngày gần nhất.
    Lúc này kết quả hôm qua đã là historical result, dễ fetch ổn định hơn.
    """
    try:
        result = await asyncio.to_thread(
            repair_recent_history,
            store,
            engine.results,
            10,
            False,
            0.10,
        )

        if result["repaired"]:
            log.info(
                "Daily history repair added: %s",
                ", ".join(result["repaired"]),
            )

        if result["failed"]:
            log.warning(
                "Daily history repair still missing: %s",
                ", ".join(result["failed"]),
            )

    except Exception:
        log.exception("Daily recent history repair failed")


async def startup_recovery():
    """
    Nếu Railway vừa restart gần giờ chạy:
    - 17:15–17:40 mà hôm nay chưa có dự đoán -> chạy bù một lần.
    - Sau 18:15 mà có prediction chưa settle -> thử lấy KQ ngay.
    """
    dt = now()
    d = dt.date()
    current = dt.time()

    try:
        p = store.get_prediction(d.isoformat(), "MB")

        if time(17, 15) <= current <= time(17, 40) and not p:
            log.info("Startup recovery: missed 17:15 prediction, running now")
            await predict_job()
            p = store.get_prediction(d.isoformat(), "MB")

        if time(18, 15) <= current <= time(20, 0) and p and not p.get("settled"):
            log.info("Startup recovery: checking settlement")
            await settlement_poll()

    except Exception:
        log.exception("Startup recovery failed")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        "🤖 <b>BOT XỔ SỐ MIỀN BẮC · FINAL</b>\n\n"
        "/mb - phân tích & chốt Miền Bắc ngay\n"
        "/result - xem dự đoán hôm nay\n"
        "/settle - kiểm tra/đối soát kết quả ngay\n"
        "/resettle - xác minh lại & sửa kết quả hôm nay\n"
        "/today - tổng kết hôm nay\n"
        "/week - tổng kết tuần hiện tại\n"
        "/month - tổng kết tháng hiện tại\n"
        "/history - kiểm tra lịch sử MB\n"
        "/sync_history - đồng bộ khoảng 240 ngày lịch sử MB\n"
        "/repair_history - vá 10 ngày gần nhất bị thiếu\n"
        "/status - trạng thái bot\n"
        "/test - kiểm tra Telegram"
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        f"✅ <b>Telegram hoạt động bình thường.</b>\n"
        f"⏰ {now().strftime('%H:%M:%S %d/%m/%Y')}"
    )



async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = history_count(store, today().isoformat())
    rows = store.get_region_history("MB", today().isoformat(), 5)
    dates = [r.get("draw_date", "?") for r in rows]

    status = recent_history_status(
        store,
        lookback_days=10,
        include_today=False,
    )
    missing = [x["date"] for x in status if not x["exists"]]

    coverage = " ".join(
        f"{x['date'][5:]}{'✅' if x['exists'] else '❌'}"
        for x in status
    )

    await reply(
        update,
        "📚 <b>LỊCH SỬ MIỀN BẮC</b>\n"
        f"Tổng số kỳ đã lưu: <b>{count}</b>\n"
        f"5 kỳ gần nhất trong DB: "
        f"{', '.join(dates) if dates else 'chưa có'}\n\n"
        f"<b>10 ngày gần nhất:</b>\n{coverage}\n\n"
        + (
            "✅ Không có ngày thiếu trong 10 ngày gần nhất."
            if not missing
            else
            "⚠️ Đang thiếu: <b>"
            + ", ".join(missing)
            + "</b>\nDùng /repair_history để vá ngay."
        )
    )


async def cmd_sync_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        "📚 Bắt đầu đồng bộ khoảng 240 ngày lịch sử MB. "
        "Có thể mất vài phút."
    )

    try:
        result = await asyncio.to_thread(
            sync_mb_history,
            store,
            engine.results,
            240,
            0.12,
        )

        await reply(
            update,
            "✅ <b>ĐỒNG BỘ XONG</b>\n"
            f"Lấy được: <b>{result['ok']}</b> kỳ\n"
            f"Không lấy được: {result['miss']} kỳ\n"
            f"Tổng trong DB: <b>{result['count']}</b> kỳ"
        )
    except Exception as e:
        log.exception("Manual history sync failed")
        await reply(
            update,
            f"❌ Đồng bộ lỗi: <code>{type(e).__name__}: {str(e)[:400]}</code>"
        )



async def cmd_repair_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        "🛠 Đang kiểm tra và vá lịch sử MB 10 ngày gần nhất..."
    )

    try:
        result = await asyncio.to_thread(
            repair_recent_history,
            store,
            engine.results,
            10,
            False,
            0.10,
        )

        repaired = result.get("repaired", [])
        failed = result.get("failed", [])

        lines = [
            "🛠 <b>VÁ LỊCH SỬ MB XONG</b>",
            f"Tổng history: <b>{result.get('count', 0)}</b> kỳ",
            "",
            "✅ Đã bổ sung: "
            + (", ".join(repaired) if repaired else "không có"),
            "❌ Vẫn thiếu: "
            + (", ".join(failed) if failed else "không có"),
        ]

        await reply(update, "\n".join(lines))

    except Exception as e:
        log.exception("Manual recent history repair failed")
        await reply(
            update,
            f"❌ Vá lịch sử lỗi: "
            f"<code>{type(e).__name__}: {str(e)[:400]}</code>"
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        d = today()
        p = store.get_prediction(d.isoformat(), "MB")
        rec = performance.get_day(d.isoformat())

        lines = [
            "🟢 <b>BOT MB ONLINE</b>",
            "",
            f"⏰ {now().strftime('%H:%M:%S %d/%m/%Y')}",
            f"🌏 Timezone: <code>{settings.timezone}</code>",
            f"Telegram: {'✅' if settings.telegram_token else '❌'}",
            f"Web: {'✅ ON' if settings.use_web_sources else '⏸ OFF'}",
            f"GPT reviewer: {'✅ ON' if settings.use_gpt else '⏸ OFF'}",
            "",
            "📅 <b>LỊCH TỰ ĐỘNG</b>",
            "00:10 → Vá history 10 ngày gần nhất",
            "17:15 → Chốt MB",
            "18:00–19:58 → Dò kết quả mỗi 2 phút",
            "Có KQ → báo ngay",
            "19:15 → Tổng kết ngày",
            "20:00 Chủ nhật → Tổng kết tuần",
            "20:15 ngày cuối tháng → Tổng kết tháng",
            "",
            "📌 <b>HÔM NAY</b>",
        ]

        if p and p.get("song_thu"):
            lines.append(f"Đã chốt: {' – '.join(p['song_thu'])} ✅")
            lines.append(f"ĐB64: {len(p.get('db50', []))} số ✅")
        else:
            lines.append("Chưa chốt.")

        if rec:
            lines.append(
                f"Đã đối soát: STL {rec['total_loto_hits']} nháy"
                f" | ĐB64 {'✅' if rec['db64_hit'] else '❌'}"
            )

        await reply(update, "\n".join(lines))

    except Exception as e:
        log.exception("Status failed")
        await reply(
            update,
            f"❌ /status lỗi: <code>{type(e).__name__}: {str(e)[:400]}</code>",
        )


async def cmd_mb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, "⏳ Đang phân tích <b>MIỀN BẮC</b>...")

    try:
        p = await predict_mb_now()
        await reply(update, format_prediction(p))
    except Exception as e:
        log.exception("Manual prediction failed")
        await reply(
            update,
            f"❌ Lỗi MB: <code>{type(e).__name__}: {str(e)[:400]}</code>",
        )


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = today()
    p = store.get_prediction(d.isoformat(), "MB")

    if p:
        await reply(update, format_prediction(p))
    else:
        await reply(
            update,
            "📭 Hôm nay chưa có dự đoán. Dùng /mb để chạy ngay."
        )



async def cmd_settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = today()

    existing = performance.get_day(d.isoformat())

    p = store.get_prediction(d.isoformat(), "MB")
    if not p:
        await reply(
            update,
            "📭 Hôm nay chưa có dự đoán MB nên chưa thể đối soát."
        )
        return

    await reply(update, "🔎 Đang kiểm tra kết quả Miền Bắc...")

    try:
        results = await asyncio.to_thread(
            engine.fetch_results, "MB", d
        )

        source = getattr(engine.results, "last_source", None)
        errors = getattr(engine.results, "last_errors", [])

        if not results:
            detail = "\n".join(f"• {x}" for x in errors[-3:])
            note = (
                "\n\n⚠️ Bản tổng kết đang lưu trước đó chưa được coi là đã xác minh."
                if existing else ""
            )
            await reply(
                update,
                "⏳ Chưa có bộ KQ MB đúng ngày được ít nhất 2 nguồn xác nhận.\n"
                f"<b>Nguồn đã thử:</b>\n{detail or 'không có thông tin'}"
                + note
            )
            return

        ok = await _settle_prediction(
            p, d, results, notify=False
        )

        if not ok:
            await reply(
                update,
                f"⏳ Đã lấy dữ liệu từ <b>{source or 'nguồn web'}</b> "
                "nhưng chưa đủ điều kiện đối soát."
            )
            return

        record = performance.get_day(d.isoformat())
        await reply(update, format_result(record))

    except Exception as e:
        log.exception("Manual settle failed")
        await reply(
            update,
            f"❌ /settle lỗi: <code>{type(e).__name__}: {str(e)[:500]}</code>"
        )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = today()
    await reply(
        update,
        format_daily(
            performance.get_day(d.isoformat()),
            d.isoformat(),
        ),
    )


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, format_weekly(performance.week(today())))


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, format_monthly(performance.month(today())))


async def startup():
    global application

    if not settings.telegram_token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong Railway Variables/.env")

    application = Application.builder().token(settings.telegram_token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(CommandHandler("test", cmd_test))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("mb", cmd_mb))
    application.add_handler(CommandHandler("result", cmd_result))
    application.add_handler(CommandHandler("settle", cmd_settle))
    application.add_handler(CommandHandler("resettle", cmd_settle))
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("week", cmd_week))
    application.add_handler(CommandHandler("month", cmd_month))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("sync_history", cmd_sync_history))
    application.add_handler(CommandHandler("repair_history", cmd_repair_history))

    scheduler = AsyncIOScheduler(timezone=TZ)

    mb_time = PREDICT_CRON["MB"]

    scheduler.add_job(
        recent_history_repair_job,
        "cron",
        hour=0,
        minute=10,
        id="history_MB_recent_repair",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        predict_job,
        "cron",
        hour=mb_time["hour"],
        minute=mb_time["minute"],
        id="predict_MB",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        settlement_poll,
        "cron",
        hour="18-19",
        minute="*/2",
        id="settlement_MB",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=19,
        minute=15,
        id="summary_MB_daily",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=1200,
    )

    scheduler.add_job(
        weekly_summary_job,
        "cron",
        day_of_week="sun",
        hour=20,
        minute=0,
        id="summary_MB_weekly",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        monthly_summary_job,
        "cron",
        day="last",
        hour=20,
        minute=15,
        id="summary_MB_monthly",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=1800,
    )

    await application.initialize()
    await application.start()

    if application.updater is None:
        raise RuntimeError("Telegram updater unavailable")

    await application.updater.start_polling(drop_pending_updates=True)

    scheduler.start()

    log.info("XS MB FINAL started")
    log.info("Commands: /mb /result /settle /resettle /today /week /month /history /sync_history /repair_history /status /test")

    # Tự xử lý trường hợp Railway vừa restart gần giờ dự đoán/đối soát.
    await startup_recovery()
    asyncio.create_task(ensure_history_background())

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)

        if application.updater:
            await application.updater.stop()

        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(startup())
