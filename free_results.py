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


def _date_variants(d: date):
    return [
        d.strftime("%d/%m/%Y"),
        f"{d.day}/{d.month}/{d.year}",
        d.strftime("%d-%m-%Y"),
        f"{d.day}-{d.month}-{d.year}",
    ]


def _has_exact_mb_date_marker(text: str, d: date) -> bool:
    """
    Chỉ chấp nhận trang có marker Miền Bắc/XSMB gắn gần đúng ngày yêu cầu.
    Tránh trang "hôm nay" nhưng block MB thực tế vẫn là ngày hôm qua.
    """
    n = _norm(text)
    dates = [re.escape(x.lower()) for x in _date_variants(d)]
    ds = "(?:" + "|".join(dates) + ")"

    patterns = [
        rf"ket qua xo so mien bac.{{0,90}}{ds}",
        rf"xo so mien bac.{{0,90}}{ds}",
        rf"xsmb.{{0,90}}{ds}",
        rf"{ds}.{{0,90}}(?:xo so mien bac|xsmb)",
    ]
    return any(re.search(p, n, re.I) for p in patterns)


def _valid_mb_entry(entry) -> bool:
    if not entry:
        return False

    prizes = list(entry.get("all_prizes", []))
    special = str(entry.get("special") or "")

    if len(prizes) != 27:
        return False

    expected_lengths = (
        [5] * 1
        + [5] * 1
        + [5] * 2
        + [5] * 6
        + [4] * 4
        + [4] * 6
        + [3] * 3
        + [2] * 4
    )

    vals = [str(x).strip() for x in prizes]

    if any(not v.isdigit() for v in vals):
        return False

    if [len(v) for v in vals] != expected_lengths:
        return False

    # all_prizes phải bắt đầu bằng chính giải ĐB.
    if not special.isdigit() or len(special) != 5:
        return False

    if vals[0] != special:
        return False

    return True


def _entry_signature(entry):
    return (
        str(entry.get("special") or ""),
        tuple(str(x) for x in entry.get("all_prizes", [])),
    )


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

    def _fetch_one(self, name, url, d):
        r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        for t in soup(["script", "style", "noscript", "svg", "iframe"]):
            t.decompose()

        page_text = " ".join(soup.stripped_strings)

        # CỰC KỲ QUAN TRỌNG:
        # Không parse nếu page chỉ có MB ngày hôm qua hoặc block miền khác.
        if not _has_exact_mb_date_marker(page_text, d):
            raise ValueError(
                f"không thấy block Miền Bắc đúng ngày {d.strftime('%d/%m/%Y')}"
            )

        # DOM/table parser.
        result = _extract_rows_from_tags(soup)
        if result and _valid_mb_entry(result):
            return result

        # Sequential fallback.
        result = _extract_by_sequential_labels(page_text)
        if result and _valid_mb_entry(result):
            return result

        raise ValueError("chưa nhận diện đúng bộ 27 giải MB của ngày yêu cầu")

    def fetch(self, region, d, stations):
        if region != "MB":
            raise ValueError("Bản này chỉ hỗ trợ MB")

        self.last_source = None
        self.last_errors = []
        candidates = []

        for name, url in self._urls(d):
            try:
                entry = self._fetch_one(name, url, d)

                if not _valid_mb_entry(entry):
                    raise ValueError("kết quả không hợp lệ")

                candidates.append((name, entry))

            except Exception as e:
                self.last_errors.append(
                    f"{name}: {type(e).__name__}: {str(e)[:180]}"
                )

        if not candidates:
            return {}

        # Với ngày hiện tại: cần 2 nguồn độc lập có đúng cùng 27 giải.
        # Điều này tránh parser trộn miền/ngày trong giai đoạn live.
        if d == date.today():
            groups = {}
            for name, entry in candidates:
                sig = _entry_signature(entry)
                groups.setdefault(sig, []).append((name, entry))

            best_sig, best_group = max(
                groups.items(),
                key=lambda kv: len(kv[1]),
            )

            if len(best_group) < 2:
                names = ", ".join(name for name, _ in candidates)
                self.last_errors.append(
                    f"đã có {len(candidates)} nguồn ({names}) nhưng chưa đủ 2 nguồn trùng khớp"
                )
                return {}

            names = [name for name, _ in best_group]
            self.last_source = "+".join(names)
            entry = best_group[0][1]
            return {stations[0]: entry}

        # Ngày lịch sử: marker ngày + cấu trúc 27 giải hợp lệ là đủ.
        self.last_source = candidates[0][0]
        return {stations[0]: candidates[0][1]}

