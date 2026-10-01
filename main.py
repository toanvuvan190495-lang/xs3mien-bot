from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from config import settings, PREDICT_CRON, REGION_NAMES
from storage import Storage
from engine import PredictionEngine
from settlement import settle
from messages import format_prediction, format_settlement, format_daily_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("xs3mien_v21")

store = Storage(settings.db_path)
engine = PredictionEngine(store)
TZ = ZoneInfo(settings.timezone)
application: Application | None = None

def today():
    return datetime.now(TZ).date()

async def reply(update: Update, text: str):
    if update.effective_message:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )

async def send(text: str):
    if not application or not settings.telegram_chat_id:
        log.info("TELEGRAM DISABLED\\n%s", text)
        return
    await application.bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def predict_region_now(region: str):
    d = today()
    p = await asyncio.to_thread(engine.predict_region, region, d)
    store.save_prediction(p)
    return p

async def predict_job(region: str):
    try:
        p = await predict_region_now(region)
        await send(format_prediction(p))
    except Exception:
        log.exception("Prediction failed %s", region)

async def settlement_poll():
    d = today()
    for p in store.unsettled_today(d.isoformat()):
        try:
            results = await asyncio.to_thread(engine.fetch_results, p["region"], d)
            complete, loto_hits, db_hits = settle(p, results)
            if not complete:
                continue
            await asyncio.to_thread(engine.ingest_results, p["region"], d, results)
            store.save_settlement(d.isoformat(), p["region"], results, loto_hits, db_hits)
            store.update_source_performance(d.isoformat(), p["region"], results)
            await send(format_settlement(p["region"], d.isoformat(), loto_hits, db_hits))
        except Exception:
            log.exception("Settlement failed %s", p["region"])

async def summary_job():
    d = today()
    await send(format_daily_summary(d.isoformat(), store.daily_summary(d.isoformat())))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "🤖 <b>BOT XỔ SỐ 3 MIỀN V2.1</b>\\n\\n"
        "/status - trạng thái bot\\n"
        "/mn - phân tích Miền Nam ngay\\n"
        "/mt - phân tích Miền Trung ngay\\n"
        "/mb - phân tích Miền Bắc ngay\\n"
        "/result - xem dự đoán hôm nay\\n"
        "/test - kiểm tra Telegram"
    )

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, f"✅ <b>Telegram hoạt động bình thường.</b>\\n⏰ {datetime.now(TZ).strftime('%H:%M:%S %d/%m/%Y')}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = today()
    lines = [
        "🟢 <b>BOT ONLINE</b>", "",
        f"⏰ {datetime.now(TZ).strftime('%H:%M:%S %d/%m/%Y')}",
        f"Telegram: {'✅' if settings.telegram_token else '❌'}",
        f"Chat ID: {'✅' if settings.telegram_chat_id else '❌'}",
        f"Xổ số API key: {'✅' if settings.xoso_api_key else '❌'}",
        f"GPT: {'✅ ON' if settings.use_gpt else '⏸ OFF'}",
        f"Web sources: {'✅ ON' if settings.use_web_sources else '⏸ OFF'}",
        "", "📅 <b>Lịch tự động</b>",
        "MN: 15:15", "MT: 16:15", "MB: 17:15", "Tổng kết: 19:00",
        "", "📌 <b>Dự đoán hôm nay</b>"
    ]
    for region in ("MN", "MT", "MB"):
        p = store.get_prediction(d.isoformat(), region)
        lines.append(
            f"{REGION_NAMES[region]}: {' – '.join(p['song_thu'])} ✅"
            if p else f"{REGION_NAMES[region]}: chưa chốt"
        )
    await reply(update, "\n".join(lines))

async def manual_region(update: Update, region: str):
    await reply(update, f"⏳ Đang phân tích <b>{REGION_NAMES[region]}</b>...")
    try:
        p = await predict_region_now(region)
        await reply(update, format_prediction(p))
    except Exception as e:
        log.exception("Manual prediction failed %s", region)
        await reply(update, f"❌ Lỗi {REGION_NAMES[region]}: <code>{type(e).__name__}: {str(e)[:400]}</code>")

async def cmd_mn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manual_region(update, "MN")

async def cmd_mt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manual_region(update, "MT")

async def cmd_mb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manual_region(update, "MB")

async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = today()
    found = False
    for region in ("MN", "MT", "MB"):
        p = store.get_prediction(d.isoformat(), region)
        if p:
            found = True
            await reply(update, format_prediction(p))
    if not found:
        await reply(update, "📭 Hôm nay chưa có dự đoán. Dùng /mn, /mt hoặc /mb để chạy ngay.")

async def startup():
    global application
    if not settings.telegram_token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    application = Application.builder().token(settings.telegram_token).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(CommandHandler("test", cmd_test))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("mn", cmd_mn))
    application.add_handler(CommandHandler("mt", cmd_mt))
    application.add_handler(CommandHandler("mb", cmd_mb))
    application.add_handler(CommandHandler("result", cmd_result))

    scheduler = AsyncIOScheduler(timezone=TZ)
    for region, t in PREDICT_CRON.items():
        scheduler.add_job(predict_job, "cron", args=[region], hour=t["hour"], minute=t["minute"], id=f"predict_{region}", replace_existing=True)
    scheduler.add_job(settlement_poll, "cron", hour="16-18", minute="*/5", id="settlement", replace_existing=True)
    scheduler.add_job(summary_job, "cron", hour=19, minute=0, id="summary", replace_existing=True)

    await application.initialize()
    await application.start()
    if application.updater is None:
        raise RuntimeError("Telegram updater unavailable")
    await application.updater.start_polling(drop_pending_updates=True)
    scheduler.start()

    log.info("XS 3 miền V2.1 started")
    log.info("Commands: /status /mn /mt /mb /result /test")

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
