from __future__ import annotations

import re
import unicodedata
from datetime import date
import requests
from bs4 import BeautifulSoup

REGION_SLUG = {"MN": "mien-nam", "MT": "mien-trung", "MB": "mien-bac"}

PRIZE_LENGTH_PATTERN_MNMT = [
    2, 3,
    4, 4, 4,
    4,
    5, 5, 5, 5, 5, 5, 5,
    5, 5,
    5,
    5,
    6,
]

ALIASES = {
    "TP. HCM": ["TP. HCM", "TP HCM", "Hồ Chí Minh", "TP Hồ Chí Minh"],
    "Đồng Tháp": ["Đồng Tháp"], "Cà Mau": ["Cà Mau"], "Bến Tre": ["Bến Tre"],
    "Vũng Tàu": ["Vũng Tàu"], "Bạc Liêu": ["Bạc Liêu"], "Đồng Nai": ["Đồng Nai"],
    "Cần Thơ": ["Cần Thơ"], "Sóc Trăng": ["Sóc Trăng"], "Tây Ninh": ["Tây Ninh"],
    "An Giang": ["An Giang"], "Bình Thuận": ["Bình Thuận"], "Vĩnh Long": ["Vĩnh Long"],
    "Bình Dương": ["Bình Dương"], "Trà Vinh": ["Trà Vinh"], "Long An": ["Long An"],
    "Bình Phước": ["Bình Phước"], "Hậu Giang": ["Hậu Giang"], "Tiền Giang": ["Tiền Giang"],
    "Kiên Giang": ["Kiên Giang"], "Đà Lạt": ["Đà Lạt", "Lâm Đồng"],

    "Huế": ["Huế", "Thừa Thiên Huế", "Thừa T. Huế"], "Phú Yên": ["Phú Yên"],
    "Đắk Lắk": ["Đắk Lắk", "Đắc Lắc"], "Quảng Nam": ["Quảng Nam"],
    "Đà Nẵng": ["Đà Nẵng"], "Khánh Hòa": ["Khánh Hòa"], "Bình Định": ["Bình Định"],
    "Quảng Trị": ["Quảng Trị"], "Quảng Bình": ["Quảng Bình"], "Gia Lai": ["Gia Lai"],
    "Ninh Thuận": ["Ninh Thuận"], "Quảng Ngãi": ["Quảng Ngãi"],
    "Đắk Nông": ["Đắk Nông", "Đắc Nông"], "Kon Tum": ["Kon Tum"],

    "Hà Nội": ["Hà Nội"], "Quảng Ninh": ["Quảng Ninh"], "Bắc Ninh": ["Bắc Ninh"],
    "Hải Phòng": ["Hải Phòng"], "Nam Định": ["Nam Định"], "Thái Bình": ["Thái Bình"],
}

def strip_accents(s: str) -> str:
    s = s.replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.lower().replace(".", " ").split())

def matching_run(tokens):
    n = len(PRIZE_LENGTH_PATTERN_MNMT)
    for i in range(len(tokens) - n + 1):
        w = tokens[i:i+n]
        if [len(x) for x in w] == PRIZE_LENGTH_PATTERN_MNMT:
            return w
    return None

class FreeResultSource:
    def __init__(self, timeout=20):
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
        })

    def url(self, region, d):
        return f"https://www.minhngoc.net.vn/ket-qua-xo-so/{REGION_SLUG[region]}/{d.strftime('%d-%m-%Y')}.html"

    def _text(self, region, d):
        r = self.s.get(self.url(region, d), timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup(["script", "style", "noscript", "svg", "iframe"]):
            t.decompose()
        return " ".join(soup.stripped_strings)

    def _today_block(self, text, region, d):
        """
        Cắt đúng khối KẾT QUẢ ngày D, bỏ menu/navigation và các ngày trước đó.
        """
        target = d.strftime("%d/%m/%Y")
        region_name = {"MN":"Miền Nam","MT":"Miền Trung","MB":"Miền Bắc"}[region]

        # Dùng normalized text để tìm marker không phụ thuộc dấu.
        norm = strip_accents(text)
        marker = strip_accents(f"KẾT QUẢ XỔ SỐ {region_name} - {target}")

        start = norm.find(marker)
        if start < 0:
            # fallback: tìm lần xuất hiện ngày sau tiêu đề KQXS
            day = strip_accents(target)
            candidates = [m.start() for m in re.finditer(re.escape(day), norm)]
            if not candidates:
                return text
            start = candidates[0]

        # Tìm marker ngày kế tiếp trong lịch sử để cắt block hiện tại.
        # Trang thường hiển thị ngày hiện tại rồi ngày trước đó.
        tail = norm[start+1:]
        next_marker = strip_accents(f"KẾT QUẢ XỔ SỐ {region_name} - ")
        m = tail.find(next_marker)
        end = (start + 1 + m) if m >= 0 else min(len(text), start + 8000)

        # Do strip_accents giữ nguyên chiều dài gần như toàn bộ ký tự Latin,
        # vị trí đủ ổn để cắt block. Nếu có chênh lệch nhỏ, cộng buffer.
        return text[max(0, start-150): min(len(text), end+150)]

    def _parse_mnmt(self, block, stations):
        out = {}
        norm = strip_accents(block)

        positions = []
        for st in stations:
            best = None
            for alias in ALIASES.get(st, [st]):
                # lấy occurrence cuối cùng trong block để tránh heading/link lặp ở đầu
                hits = [m.start() for m in re.finditer(re.escape(strip_accents(alias)), norm)]
                if hits:
                    p = hits[-1]
                    if best is None or p < best:
                        best = p
            if best is not None:
                positions.append((st, best))

        positions.sort(key=lambda x: x[1])

        for i, (st, start) in enumerate(positions):
            end = positions[i+1][1] if i+1 < len(positions) else len(norm)
            seg = norm[start:end]
            tokens = re.findall(r"(?<!\d)(\d{2,6})(?!\d)", seg)
            run = matching_run(tokens)
            if run:
                out[st] = {"special": run[-1], "all_prizes": run}

        return out

    def _parse_mb(self, block, stations):
        # Trong block ngày đã cắt, lấy theo nhãn giải.
        norm = " ".join(block.split())

        m = re.search(r"(?:Giải ĐB|Giải Đặc Biệt)\s+(\d{5})", norm, re.I)
        special = m.group(1) if m else None

        if not special:
            # fallback: DB MB là số 5 chữ số đầu tiên sau phần nhãn giải
            nums5 = re.findall(r"(?<!\d)(\d{5})(?!\d)", norm)
            special = nums5[0] if nums5 else None

        nums = re.findall(r"(?<!\d)(\d{2,5})(?!\d)", norm)

        if special:
            try:
                idx = nums.index(special)
                nums = nums[idx:]
            except ValueError:
                nums.insert(0, special)

        prizes = nums[:27]
        if special and len(prizes) >= 27:
            return {stations[0]: {"special": special, "all_prizes": prizes}}
        return {}

    def fetch(self, region, d, stations):
        text = self._text(region, d)
        block = self._today_block(text, region, d)
        if region in ("MN","MT"):
            return self._parse_mnmt(block, stations)
        return self._parse_mb(block, stations)
