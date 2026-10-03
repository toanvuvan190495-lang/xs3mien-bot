from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

REGION_NAMES = {"MB": "MIỀN BẮC"}

# Python weekday: Monday=0 ... Sunday=6
DRAW_SCHEDULE = {
    "MB": {
        0: ["Hà Nội"],
        1: ["Quảng Ninh"],
        2: ["Bắc Ninh"],
        3: ["Hà Nội"],
        4: ["Hải Phòng"],
        5: ["Nam Định"],
        6: ["Thái Bình"],
    }
}

PREDICT_CRON = {
    "MB": {"hour": 17, "minute": 15},
}


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    timezone: str = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")
    db_path: str = os.getenv("DB_PATH", "data/lottery_v2.sqlite3")

    history_days: int = int(os.getenv("HISTORY_DAYS", "365"))
    web_timeout: int = int(os.getenv("WEB_TIMEOUT", "12"))

    # GPT chỉ là reviewer tùy chọn; scoring định lượng vẫn là lõi.
    use_gpt: bool = env_bool("USE_GPT", False)
    use_web_sources: bool = env_bool("USE_WEB_SOURCES", True)

    # Web không được lấn át history/model.
    community_max_weight: float = float(os.getenv("COMMUNITY_MAX_WEIGHT", "0.28"))


settings = Settings()
