from __future__ import annotations
import re
from datetime import date
import requests
from bs4 import BeautifulSoup

REGION_SLUG = {"MN": "mien-nam", "MT": "mien-trung", "MB": "mien-bac"}

# Kỳ vọng theo cơ cấu giải:
EXPECTED_PRIZE_COUNT = {"MN": 18, "MT": 18, "MB": 27}

def _norm(s):
    return (
        s.lower().replace(".", "").replace("đ", "d")
        .replace("ắ", "a").replace("ă", "a").replace("â", "a")
        .replace("à", "a").replace("á", "a").replace("ả", "a").replace("ã", "a").replace("ạ", "a")
        .replace("ê", "e").replace("é", "e").replace("è", "e")
        .replace("ô", "o").replace("ơ", "o").replace("ó", "o").replace("ò", "o")
        .replace("ư", "u").replace("ú", "u").replace("ù", "u")
        .replace("í", "i").replace("ì", "i")
        .replace("ý", "y").replace("ỳ", "y")
    )

def _tokens_after(text, station):
    # Lấy đoạn sau tên đài, trước marker bảng loto/đài kế tiếp.
    low = _norm(text)
    key = _norm(station)
    i = low.find(key)
    if i < 0:
        return []
    segment = text[i:i+2200]
    # Các mã đài/nhãn có thể xen giữa; chỉ lấy token số 2..6 chữ số.
    return re.findall(r"(?<!\d)(\d{2,6})(?!\d)", segment)

class FreeResultSource:
    """
    Nguồn kết quả công khai Minh Ngọc.
    Không cần API key.
    """
    def __init__(self, timeout=20):
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
        })

    def url(self, region: str, d: date):
        dd = d.strftime("%d-%m-%Y")
        return f"https://www.minhngoc.net.vn/ket-qua-xo-so/{REGION_SLUG[region]}/{dd}.html"

    def fetch(self, region: str, d: date, stations: list[str]):
        r = self.s.get(self.url(region, d), timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup(["script","style","noscript","svg"]):
            t.decompose()
        text = " ".join(soup.stripped_strings)

        out = {}
        need = EXPECTED_PRIZE_COUNT[region]

        if region in ("MN", "MT"):
            for station in stations:
                nums = _tokens_after(text, station)
                # Với MN/MT sau tên đài thường là mã đài rồi đúng 18 số giải.
                # Chọn chuỗi đầu tiên có pattern độ dài hợp lý.
                cleaned = [x for x in nums if 2 <= len(x) <= 6]
                if len(cleaned) >= need:
                    prize = cleaned[:need]
                    out[station] = {"special": prize[-1], "all_prizes": prize}
        else:
            # MB: chỉ 1 đài/ngày, trang miền Bắc chứa 27 số giải.
            # Bắt đầu gần tiêu đề KẾT QUẢ XỔ SỐ Miền Bắc.
            marker = text.lower().find("kết quả xổ số miền bắc")
            seg = text[marker:marker+4500] if marker >= 0 else text[:4500]
            nums = re.findall(r"(?<!\d)(\d{2,5})(?!\d)", seg)
            # Loại các ngày/tháng/năm và số điều hướng bằng cách ưu tiên đoạn sau "Giải Đặc Biệt"
            p = seg.lower().find("giải đặc biệt")
            if p >= 0:
                nums = re.findall(r"(?<!\d)(\d{2,5})(?!\d)", seg[p:p+3000])
            if len(nums) >= need:
                # HTML có thể liệt kê theo thứ tự DB -> G1... hoặc ngược lại.
                # Xác định DB là token 5 chữ số đầu tiên.
                selected = nums[:need]
                db = next((x for x in selected if len(x) == 5), selected[0])
                out[stations[0]] = {"special": db, "all_prizes": selected}

        return out
