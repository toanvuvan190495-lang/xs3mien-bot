from __future__ import annotations

from collections import Counter

NUMBERS = [f"{i:02d}" for i in range(100)]


def last2(x):
    s = "".join(ch for ch in str(x) if ch.isdigit())
    return s[-2:].zfill(2) if s else "00"


def _normalize(values: dict[str, float]) -> dict[str, float]:
    mx = max(values.values()) if values else 0.0
    mn = min(values.values()) if values else 0.0
    if mx <= mn:
        return {n: 0.0 for n in NUMBERS}
    return {n: (values.get(n, 0.0) - mn) / (mx - mn) for n in NUMBERS}


def _loto_count(rows, window: int):
    c = Counter()
    hits = Counter()
    subset = rows[:window]
    for r in subset:
        nums = [last2(x) for x in r.get("prizes", [])]
        c.update(nums)
        hits.update(set(nums))
    return _normalize({n: float(c[n]) for n in NUMBERS}), _normalize(
        {n: float(hits[n]) for n in NUMBERS}
    )


def _db_count(rows, window: int):
    c = Counter()
    for r in rows[:window]:
        sp = r.get("special")
        if sp is not None:
            c[last2(sp)] += 1
    return _normalize({n: float(c[n]) for n in NUMBERS})


def build_history_scores(rows):
    """
    rows: newest first, chỉ gồm các kỳ TRƯỚC ngày cần dự đoán.

    MB được ưu tiên:
    - lô: tần suất + số kỳ xuất hiện ở cửa sổ 7/21/60 kỳ;
    - ĐB: tần suất giải đặc biệt 14/45/120 kỳ;
    - không dùng quy tắc "gan lâu chắc về".
    """
    if not rows:
        zero = {n: 0.0 for n in NUMBERS}
        return zero.copy(), zero.copy()

    f7, h7 = _loto_count(rows, 7)
    f21, h21 = _loto_count(rows, 21)
    f60, h60 = _loto_count(rows, 60)

    loto = {
        n: (
            0.22 * f7[n]
            + 0.18 * h7[n]
            + 0.26 * f21[n]
            + 0.20 * h21[n]
            + 0.08 * f60[n]
            + 0.06 * h60[n]
        )
        for n in NUMBERS
    }

    d14 = _db_count(rows, 14)
    d45 = _db_count(rows, 45)
    d120 = _db_count(rows, 120)

    db = {
        n: 0.20 * d14[n] + 0.38 * d45[n] + 0.42 * d120[n]
        for n in NUMBERS
    }

    return _normalize(loto), _normalize(db)
