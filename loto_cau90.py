from __future__ import annotations

from collections import Counter
from itertools import combinations

NUMBERS = [f"{i:02d}" for i in range(100)]


def last2(x):
    s = "".join(ch for ch in str(x or "") if ch.isdigit())
    return s[-2:].zfill(2) if s else "00"


def normalize(scores):
    if not scores:
        return {n: 0.0 for n in NUMBERS}
    mx = max(scores.values())
    mn = min(scores.values())
    if mx <= mn:
        return {n: 0.0 for n in NUMBERS}
    return {
        n: (float(scores.get(n, 0.0)) - mn) / (mx - mn)
        for n in NUMBERS
    }


def _actual_day(row):
    return [last2(x) for x in row.get("prizes", [])]


def _window_metric(rows, window):
    """
    Điểm nóng theo đúng dữ liệu lô:
    - 65% số ngày có xuất hiện;
    - 35% tổng số nháy.
    """
    subset = rows[:window]
    hit_days = Counter()
    occurrences = Counter()

    for r in subset:
        vals = _actual_day(r)
        occurrences.update(vals)
        hit_days.update(set(vals))

    hit_score = normalize({n: float(hit_days[n]) for n in NUMBERS})
    occ_score = normalize({n: float(occurrences[n]) for n in NUMBERS})

    return {
        n: 0.65 * hit_score[n] + 0.35 * occ_score[n]
        for n in NUMBERS
    }


def _trend_score(rows):
    """
    90 ngày nhưng đẩy trọng số về các kỳ gần:
    7d 28% · 14d 24% · 30d 20% · 60d 16% · 90d 12%.
    """
    windows = [
        (7, 0.28),
        (14, 0.24),
        (30, 0.20),
        (60, 0.16),
        (90, 0.12),
    ]

    out = {n: 0.0 for n in NUMBERS}
    details = {}

    for days, weight in windows:
        comp = _window_metric(rows, days)
        details[str(days)] = comp
        for n in NUMBERS:
            out[n] += weight * comp[n]

    return normalize(out), details


def _presence_series(rows):
    """
    Trả chuỗi oldest -> newest cho mỗi số.
    """
    chronological = list(reversed(rows))
    series = {n: [] for n in NUMBERS}

    for r in chronological:
        actual = set(_actual_day(r))
        for n in NUMBERS:
            series[n].append(1 if n in actual else 0)

    return series


def _pattern_score(rows):
    """
    Cầu nhịp động theo lịch sử 90 ngày.

    Với mỗi số, bot nhìn suffix 2..6 kỳ gần nhất (có/không về),
    tìm chính pattern đó đã từng xuất hiện trong 90 ngày và xem kỳ kế
    tiếp số đó về với tỷ lệ nào.

    Không hard-code 121/222/...; pattern tự sinh từ dữ liệu.
    """
    series = _presence_series(rows)
    raw = {}
    meta = {}

    for n in NUMBERS:
        s = series[n]
        if len(s) < 12:
            raw[n] = 0.0
            meta[n] = {"support": 0, "prob": 0.0}
            continue

        base = sum(s) / len(s)
        numerator = 0.0
        denominator = 0.0
        total_support = 0

        for k in range(2, 7):
            if len(s) <= k:
                continue

            ctx = tuple(s[-k:])
            hits = 0
            support = 0

            for i in range(k, len(s)):
                if tuple(s[i-k:i]) != ctx:
                    continue
                support += 1
                hits += int(s[i] == 1)

            # Mẫu quá hiếm thì không cho tác động.
            if support < 3:
                continue

            # Bayesian shrink về base-rate riêng của số.
            prob = (hits + 3.0 * base) / (support + 3.0)
            strength = min(1.0, support / 12.0) * (0.55 + 0.075 * k)

            numerator += prob * strength
            denominator += strength
            total_support += support

        if denominator <= 0:
            prob = base
        else:
            prob = numerator / denominator

        # Blend nhẹ với base-rate để pattern không lấn át khi mẫu ít.
        final_prob = 0.78 * prob + 0.22 * base
        raw[n] = final_prob
        meta[n] = {
            "support": total_support,
            "prob": final_prob,
            "base": base,
        }

    return normalize(raw), meta


def _gap_after(series, idx):
    """
    Khoảng cách sau khi đã quan sát tới idx.
    0 = vừa về ở kỳ idx; 1 = vắng 1 kỳ; ...
    """
    gap = 0
    j = idx
    while j >= 0 and series[j] == 0:
        gap += 1
        j -= 1
    return min(gap, 20)


def _gap_hazard_score(rows):
    """
    Cầu nhịp khoảng cách (hazard), nhưng KHÔNG dùng quy tắc
    'gan lâu chắc về'.

    Bot học từ toàn bộ 100 số trong 90 ngày:
    khi một số đang ở gap g, kỳ kế tiếp thực tế về bao nhiêu lần.
    """
    series = _presence_series(rows)
    trials = Counter()
    hits = Counter()

    for n in NUMBERS:
        s = series[n]
        for i in range(5, len(s) - 1):
            g = _gap_after(s, i)
            trials[g] += 1
            hits[g] += int(s[i + 1] == 1)

    hazard = {}
    for g in range(21):
        # Beta smoothing.
        hazard[g] = (hits[g] + 2.0) / (trials[g] + 4.0)

    raw = {}
    current_gaps = {}

    for n in NUMBERS:
        s = series[n]
        if not s:
            raw[n] = 0.0
            current_gaps[n] = None
            continue

        g = _gap_after(s, len(s) - 1)
        current_gaps[n] = g
        raw[n] = hazard.get(g, 0.0)

    return normalize(raw), {
        "hazard": hazard,
        "current_gaps": current_gaps,
    }


def _stability_score(window_details):
    """
    Ưu tiên số giữ sức ở 14/30/60/90 thay vì chỉ bùng 1 cửa sổ.
    """
    out = {}

    for n in NUMBERS:
        vals = [
            window_details["14"][n],
            window_details["30"][n],
            window_details["60"][n],
            window_details["90"][n],
        ]
        mean = sum(vals) / len(vals)
        spread = max(vals) - min(vals)
        out[n] = mean * (1.0 - 0.45 * spread)

    return normalize(out)


def _trusted_web_score(source_detail):
    """
    Song thủ chỉ dùng lớp web được coi là đủ tin cậy theo chính
    performance của bot.

    Không gắn nhãn 'uy tín tuyệt đối' cho website:
    - forum/community/data/statistics được phép tham gia;
    - nguồn đã có >=8 mẫu mà effective_loto <47% bị loại;
    - nguồn ít mẫu vẫn được dùng nhưng bị shrink bằng reliability.
    """
    allowed_kinds = {
        "forum": 1.15,
        "community_rank": 1.12,
        "data_model": 1.05,
        "statistics": 0.96,
    }

    raw = {n: 0.0 for n in NUMBERS}
    agreement = Counter()
    used = []
    total_weight = 0.0

    for rec in source_detail or []:
        kind = rec.get("kind")
        if kind not in allowed_kinds:
            continue

        rel = rec.get("reliability") or {}
        sample = int(rel.get("sample_loto", 0))
        effective = float(rec.get("effective_loto", 0.50))

        if sample >= 8 and effective < 0.47:
            continue

        picks = list(dict.fromkeys(rec.get("loto", [])))[:12]
        if not picks:
            continue

        sample_conf = min(1.0, sample / 24.0)
        rel_factor = 0.80 + 0.40 * effective
        conf_factor = 0.75 + 0.25 * sample_conf
        weight = allowed_kinds[kind] * rel_factor * conf_factor

        for rank, n in enumerate(picks):
            if n not in raw:
                continue
            rank_factor = max(0.30, 1.0 - rank * 0.065)
            raw[n] += weight * rank_factor
            agreement[n] += 1

        total_weight += weight
        used.append({
            "source": rec.get("source"),
            "kind": kind,
            "effective_loto": effective,
            "sample_loto": sample,
        })

    if total_weight > 0:
        for n in NUMBERS:
            raw[n] /= total_weight

            # Nhiều nguồn độc lập cùng chốt -> bonus vừa phải.
            a = agreement[n]
            if a >= 4:
                raw[n] *= 1.25
            elif a >= 3:
                raw[n] *= 1.17
            elif a >= 2:
                raw[n] *= 1.09

    score = normalize(raw)

    # Web chỉ là lớp hỗ trợ. 0..25%.
    active = len(used)
    table = {
        0: 0.00,
        1: 0.07,
        2: 0.12,
        3: 0.17,
        4: 0.21,
    }
    web_weight = table.get(active, 0.24)

    if used:
        avg_rel = sum(x["effective_loto"] for x in used) / len(used)
        quality_factor = max(
            0.80,
            min(1.08, 1.0 + (avg_rel - 0.50) * 1.2),
        )
        web_weight = min(0.25, web_weight * quality_factor)

    return score, dict(agreement), used, web_weight


def _pair_history_score(rows, a, b):
    """
    Đánh giá trực tiếp cặp song thủ trên lịch sử:
    ưu tiên gần đây hơn nhưng vẫn nhìn đủ 90 ngày.
    """
    windows = [
        (30, 0.50),
        (60, 0.30),
        (90, 0.20),
    ]

    total = 0.0

    for days, weight in windows:
        subset = rows[:days]
        if not subset:
            continue

        any_hits = 0
        both_hits = 0

        for r in subset:
            actual = set(_actual_day(r))
            ha = a in actual
            hb = b in actual
            any_hits += int(ha or hb)
            both_hits += int(ha and hb)

        any_rate = any_hits / len(subset)
        both_rate = both_hits / len(subset)

        # Mục tiêu chính: ít nhất một con về.
        total += weight * (0.88 * any_rate + 0.12 * both_rate)

    return total


def _choose_pair(rows, scores, web_agreement, top_n=24):
    candidates = sorted(
        NUMBERS,
        key=lambda n: scores.get(n, 0.0),
        reverse=True,
    )[:top_n]

    raw_pairs = []

    for a, b in combinations(candidates, 2):
        indiv = (scores[a] + scores[b]) / 2.0
        balance = 1.0 / (1.0 + abs(scores[a] - scores[b]))
        historical = _pair_history_score(rows, a, b)
        consensus = min(
            1.0,
            (web_agreement.get(a, 0) + web_agreement.get(b, 0)) / 5.0,
        )

        raw_pairs.append({
            "a": a,
            "b": b,
            "indiv": indiv,
            "balance": balance,
            "history": historical,
            "consensus": consensus,
        })

    if not raw_pairs:
        return candidates[:2], {}

    hist_vals = {
        f"{x['a']}-{x['b']}": x["history"]
        for x in raw_pairs
    }
    hist_norm = normalize_pair_map(hist_vals)

    ranked = []
    for x in raw_pairs:
        key = f"{x['a']}-{x['b']}"
        h = hist_norm.get(key, 0.0)

        # Cặp cuối cùng:
        # 76% sức 2 số + 8% cân bằng + 12% thực chiến cặp 90d + 4% đồng thuận web.
        pair_score = (
            0.76 * x["indiv"]
            + 0.08 * x["balance"]
            + 0.12 * h
            + 0.04 * x["consensus"]
        )
        ranked.append((pair_score, x, h))

    ranked.sort(key=lambda t: t[0], reverse=True)
    _, best, hnorm = ranked[0]

    return [best["a"], best["b"]], {
        "pair_score": round(ranked[0][0], 4),
        "history_pair_raw": round(best["history"], 4),
        "history_pair_norm": round(hnorm, 4),
        "web_sources_pair": (
            int(web_agreement.get(best["a"], 0))
            + int(web_agreement.get(best["b"], 0))
        ),
    }


def normalize_pair_map(values):
    if not values:
        return {}
    mx = max(values.values())
    mn = min(values.values())
    if mx <= mn:
        return {k: 0.5 for k in values}
    return {k: (v - mn) / (mx - mn) for k, v in values.items()}


def build_loto_cau90(rows, source_detail=None, max_web_weight=0.25):
    """
    Song thủ MB V3.9.

    rows: newest -> oldest, tối đa 90 ngày/kỳ gần nhất toàn MB.

    History core:
      38% xu hướng/tần suất đa cửa sổ
      32% cầu pattern động 2..6 kỳ
      15% gap-hazard học từ dữ liệu
      15% stability 14/30/60/90

    Sau đó mới trộn lớp web/forum có reliability, tối đa 25%.
    """
    rows = list(rows or [])[:90]

    zero = {n: 0.0 for n in NUMBERS}
    if not rows:
        return {
            "scores": zero.copy(),
            "history_scores": zero.copy(),
            "song_thu": ["00", "01"],
            "web_weight": 0.0,
            "trusted_sources": [],
            "web_agreement": {},
            "meta": {
                "history_rows": 0,
                "formula": "no_history",
            },
        }

    trend, windows = _trend_score(rows)
    pattern, pattern_meta = _pattern_score(rows)
    gap, gap_meta = _gap_hazard_score(rows)
    stability = _stability_score(windows)

    history = {}
    for n in NUMBERS:
        history[n] = (
            0.38 * trend[n]
            + 0.32 * pattern[n]
            + 0.15 * gap[n]
            + 0.15 * stability[n]
        )
    history = normalize(history)

    web, agreement, trusted_sources, web_weight = _trusted_web_score(
        source_detail or []
    )
    web_weight = min(float(max_web_weight), web_weight)

    final_scores = {}
    for n in NUMBERS:
        final_scores[n] = (
            (1.0 - web_weight) * history[n]
            + web_weight * web[n]
        )
    final_scores = normalize(final_scores)

    pair, pair_meta = _choose_pair(
        rows,
        final_scores,
        agreement,
        top_n=24,
    )

    return {
        "scores": final_scores,
        "history_scores": history,
        "song_thu": pair,
        "web_weight": web_weight,
        "trusted_sources": trusted_sources,
        "web_agreement": agreement,
        "pair_meta": pair_meta,
        "meta": {
            "history_rows": len(rows),
            "formula": {
                "trend": 0.38,
                "pattern": 0.32,
                "gap_hazard": 0.15,
                "stability": 0.15,
            },
            "windows": [7, 14, 30, 60, 90],
            "pattern_lengths": [2, 3, 4, 5, 6],
        },
    }
