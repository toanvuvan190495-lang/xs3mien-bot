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

    await asyncio.to_thread(engine.ingest_results, "MB", d, results)

    store.save_settlement(
        d.isoformat(), "MB", results, loto_hits, db_hits
    )
    store.update_source_performance(
        d.isoformat(), "MB", results
    )

    record = performance.record(
        d.isoformat(), p, loto_hits, db_hits
    )

    if notify:
        await send(format_result(record))

    return True


async def settlement_poll():
    d = today()
    pending = [
        p for p in store.unsettled_today(d.isoformat())
        if p.get("region") == "MB"
    ]

    if not pending:
        return

    for p in pending:
        try:
            results = await asyncio.to_thread(
                engine.fetch_results, "MB", d
            )

            source = getattr(engine.results, "last_source", None)
            errors = getattr(engine.results, "last_errors", [])

            if not results:
                log.info(
                    "MB result not ready/parsed. tried=%s",
                    " | ".join(errors[-3:]) if errors else "unknown"
                )
                continue

            ok = await _settle_prediction(
                p, d, results, notify=True
            )

            if ok:
                log.info(
                    "MB settlement completed. source=%s",
                    source or "unknown"
                )
            else:
                log.info(
                    "MB result fetched but settlement incomplete. source=%s keys=%s",
                    source or "unknown",
                    list(results.keys()),
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
        "/today - tổng kết hôm nay\n"
        "/week - tổng kết tuần hiện tại\n"
        "/month - tổng kết tháng hiện tại\n"
        "/status - trạng thái bot\n"
        "/test - kiểm tra Telegram"
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        f"✅ <b>Telegram hoạt động bình thường.</b>\n"
        f"⏰ {now().strftime('%H:%M:%S %d/%m/%Y')}"
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
    if existing:
        await reply(update, format_result(existing))
        return

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
            await reply(
                update,
                "⏳ Chưa lấy được bộ KQ MB đầy đủ 27 giải.\n"
                f"<b>Nguồn đã thử:</b>\n{detail or 'không có thông tin'}"
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
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("week", cmd_week))
    application.add_handler(CommandHandler("month", cmd_month))

    scheduler = AsyncIOScheduler(timezone=TZ)

    mb_time = PREDICT_CRON["MB"]

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
    log.info("Commands: /mb /result /settle /today /week /month /status /test")

    # Tự xử lý trường hợp Railway vừa restart gần giờ dự đoán/đối soát.
    await startup_recovery()

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
