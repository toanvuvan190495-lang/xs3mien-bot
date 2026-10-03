from __future__ import annotations

import re
import unicodedata
from datetime import date
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


def _norm(s: str) -> str:
    s = s.replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.lower().split())


EXPECTED = [
    ("DB", 1, 5, [r"\bdb\b", r"giai db", r"giai dac biet"]),
    ("G1", 1, 5, [r"\bg\.?\s*1\b", r"giai nhat", r"giai 1"]),
    ("G2", 2, 5, [r"\bg\.?\s*2\b", r"giai nhi", r"giai 2"]),
    ("G3", 6, 5, [r"\bg\.?\s*3\b", r"giai ba", r"giai 3"]),
    ("G4", 4, 4, [r"\bg\.?\s*4\b", r"giai tu", r"giai 4"]),
    ("G5", 6, 4, [r"\bg\.?\s*5\b", r"giai nam", r"giai 5"]),
    ("G6", 3, 3, [r"\bg\.?\s*6\b", r"giai sau", r"giai 6"]),
    ("G7", 4, 2, [r"\bg\.?\s*7\b", r"giai bay", r"giai 7"]),
]


def _matches_label(text_norm: str, patterns):
    return any(re.search(p, text_norm, re.I) for p in patterns)


def _extract_rows_from_tags(soup: BeautifulSoup):
    """
    Tìm từng hàng giải từ table/div/li. Chỉ nhận nếu đủ 8 giải
    với đúng cơ cấu 27 số của XSMB.
    """
    found = {}

    # Ưu tiên table rows, sau đó các block nhỏ.
    tags = list(soup.find_all("tr"))
    tags += [
        x for x in soup.find_all(["div", "li", "p"])
        if len(" ".join(x.stripped_strings)) <= 260
    ]

    for tag in tags:
        raw = " ".join(tag.stripped_strings)
        if not raw:
            continue
        ntext = _norm(raw)

        for key, count, digits, patterns in EXPECTED:
            if key in found:
                continue
            if not _matches_label(ntext, patterns):
                continue

            nums = re.findall(rf"(?<!\d)(\d{{{digits}}})(?!\d)", raw)
            if len(nums) >= count:
                found[key] = nums[-count:] if key == "G7" else nums[:count]

    if len(found) != len(EXPECTED):
        return None

    prizes = []
    for key, count, _, _ in EXPECTED:
        vals = found.get(key, [])
        if len(vals) != count:
            return None
        prizes.extend(vals)

    if len(prizes) != 27:
        return None

    return {
        "special": found["DB"][0],
        "all_prizes": prizes,
    }


def _extract_by_sequential_labels(text: str):
    """
    Fallback khi website không dùng table rows.
    Cắt nội dung giữa các nhãn giải theo đúng thứ tự DB -> G7.
    """
    ntext = _norm(text)

    label_spans = []
    cursor = 0
    for key, count, digits, patterns in EXPECTED:
        best = None
        for p in patterns:
            m = re.search(p, ntext[cursor:], re.I)
            if m:
                pos = cursor + m.start()
                end = cursor + m.end()
                if best is None or pos < best[0]:
                    best = (pos, end)
        if best is None:
            return None
        label_spans.append((key, count, digits, best[0], best[1]))
        cursor = best[1]

    found = {}
    for i, (key, count, digits, start, label_end) in enumerate(label_spans):
        end = label_spans[i + 1][3] if i + 1 < len(label_spans) else min(len(ntext), label_end + 400)
        seg = ntext[label_end:end]
        nums = re.findall(rf"(?<!\d)(\d{{{digits}}})(?!\d)", seg)
        if len(nums) < count:
            return None
        found[key] = nums[:count]

    prizes = []
    for key, count, _, _, _ in label_spans:
        prizes.extend(found[key])

    if len(prizes) != 27:
        return None

    return {"special": found["DB"][0], "all_prizes": prizes}


class FreeResultSource:
    def __init__(self, timeout=12):
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/152 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        })
        self.last_source = None
        self.last_errors = []

    def _urls(self, d: date):
        dd = d.strftime("%d")
        mm = d.strftime("%m")
        yyyy = d.strftime("%Y")

        return [
            (
                "minhngoc",
                f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/{dd}-{mm}-{yyyy}.html",
            ),
            (
                "xsmn_mobi",
                f"https://xsmn.mobi/xsmb-{d.day}-{d.month}-{d.year}.html",
            ),
            (
                "xoso_com_vn",
                f"https://xoso.com.vn/xsmb-{dd}-{mm}-{yyyy}.html",
            ),
        ]

    def _fetch_one(self, name, url):
        r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        for t in soup(["script", "style", "noscript", "svg", "iframe"]):
            t.decompose()

        # 1) DOM/table parser
        result = _extract_rows_from_tags(soup)
        if result:
            return result

        # 2) Sequential text parser
        text = " ".join(soup.stripped_strings)
        result = _extract_by_sequential_labels(text)
        if result:
            return result

        raise ValueError("chưa nhận diện đủ 27 giải MB")

    def fetch(self, region, d, stations):
        if region != "MB":
            raise ValueError("Bản này chỉ hỗ trợ MB")

        self.last_source = None
        self.last_errors = []

        for name, url in self._urls(d):
            try:
                entry = self._fetch_one(name, url)

                # Validation cứng.
                if (
                    not entry.get("special")
                    or len(entry.get("all_prizes", [])) != 27
                ):
                    raise ValueError("kết quả không đủ 27 giải")

                self.last_source = name
                return {
                    stations[0]: entry
                }

            except Exception as e:
                self.last_errors.append(
                    f"{name}: {type(e).__name__}: {str(e)[:180]}"
                )

        return {}
