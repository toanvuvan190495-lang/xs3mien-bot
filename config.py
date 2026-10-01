from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

REGION_NAMES = {"MN": "MIỀN NAM", "MT": "MIỀN TRUNG", "MB": "MIỀN BẮC"}

# Python weekday Monday=0 ... Sunday=6
DRAW_SCHEDULE = {
    "MN": {
        0: ["TP. HCM", "Đồng Tháp", "Cà Mau"],
        1: ["Bến Tre", "Vũng Tàu", "Bạc Liêu"],
        2: ["Đồng Nai", "Cần Thơ", "Sóc Trăng"],
        3: ["Tây Ninh", "An Giang", "Bình Thuận"],
        4: ["Vĩnh Long", "Bình Dương", "Trà Vinh"],
        5: ["TP. HCM", "Long An", "Bình Phước", "Hậu Giang"],
        6: ["Tiền Giang", "Kiên Giang", "Đà Lạt"],
    },
    "MT": {
        0: ["Huế", "Phú Yên"],
        1: ["Đắk Lắk", "Quảng Nam"],
        2: ["Đà Nẵng", "Khánh Hòa"],
        3: ["Bình Định", "Quảng Trị", "Quảng Bình"],
        4: ["Gia Lai", "Ninh Thuận"],
        5: ["Đà Nẵng", "Quảng Ngãi", "Đắk Nông"],
        6: ["Khánh Hòa", "Kon Tum", "Huế"],
    },
    "MB": {
        0: ["Hà Nội"],
        1: ["Quảng Ninh"],
        2: ["Bắc Ninh"],
        3: ["Hà Nội"],
        4: ["Hải Phòng"],
        5: ["Nam Định"],
        6: ["Thái Bình"],
    },
}

PREDICT_CRON = {
    "MN": {"hour": 15, "minute": 15},
    "MT": {"hour": 16, "minute": 15},
    "MB": {"hour": 17, "minute": 15},
}

# Các nguồn đã được tách độc lập. Nguồn lỗi sẽ bị bỏ qua, bot vẫn chạy.
WEB_SOURCES = [
    {
        "name": "soicau666",
        "base_url": "https://soicau666.com/",
        "regions": ["MN", "MT", "MB"],
        "crawl_links": 4,
    },
    {
        "name": "caudesongthu",
        "base_url": "https://caudesongthu.com/",
        "regions": ["MN", "MT", "MB"],
        "crawl_links": 4,
    },
    {
        "name": "soicaumiennamchinhxac",
        "base_url": "https://soicaumiennamchinhxac.com/",
        "regions": ["MN", "MT", "MB"],
        "crawl_links": 4,
    },
    {
        "name": "soicauxsmb",
        "base_url": "https://soicauxsmb.me/",
        "regions": ["MB"],
        "crawl_links": 3,
    },
    {
        "name": "forumketqua",
        "base_url": "https://forumketqua.net/",
        "regions": ["MB"],
        "crawl_links": 5,
    },
    {
        "name": "xosome",
        "base_url": "https://xoso.me/",
        "regions": ["MN", "MT", "MB"],
        "crawl_links": 4,
    },
]

@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    timezone: str = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")
    db_path: str = os.getenv("DB_PATH", "data/lottery_v2.sqlite3")
    history_days: int = int(os.getenv("HISTORY_DAYS", "365"))
    web_timeout: int = int(os.getenv("WEB_TIMEOUT", "18"))
    use_gpt: bool = os.getenv("USE_GPT", "0") == "1"
    use_web_sources: bool = os.getenv("USE_WEB_SOURCES", "1") == "1"
    community_max_weight: float = float(os.getenv("COMMUNITY_MAX_WEIGHT", "0.24"))

settings = Settings()
