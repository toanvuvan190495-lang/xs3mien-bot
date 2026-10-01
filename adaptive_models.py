from __future__ import annotations

from itertools import combinations

NUMBERS = [f"{i:02d}" for i in range(100)]

def _avg(vals):
    return sum(vals) / len(vals) if vals else 0.0

def build_model_scores(station_bundles, history_scores_by_station=None):
    """
    Tạo nhiều góc nhìn khác nhau trên cùng dữ liệu.
    Mỗi model trả điểm 00..99.
    """
    models = {
        "mean_strength": {n: 0.0 for n in NUMBERS},
        "coverage": {n: 0.0 for n in NUMBERS},
        "balanced": {n: 0.0 for n in NUMBERS},
        "history_focus": {n: 0.0 for n in NUMBERS},
        "contrarian": {n: 0.0 for n in NUMBERS},
    }

    station_names = list(station_bundles.keys())
    count = max(1, len(station_names))

    for n in NUMBERS:
        vals = [station_bundles[s][0][n] for s in station_names]
        mean = _avg(vals)
        mx = max(vals) if vals else 0.0
        mn = min(vals) if vals else 0.0
        spread = mx - mn
        support = sum(v >= mx * 0.60 and v > 0 for v in vals) / count if mx > 0 else 0.0

        models["mean_strength"][n] = mean
        models["coverage"][n] = 0.65 * support + 0.35 * mean
        models["balanced"][n] = 0.55 * mean + 0.25 * support + 0.20 * (1 / (1 + spread))

        # history_focus dùng trực tiếp history score nếu có
        hv = []
        if history_scores_by_station:
            for st in station_names:
                hs = history_scores_by_station.get(st)
                if hs:
                    hv.append(hs[0][n])
        hmean = _avg(hv) if hv else mean
        models["history_focus"][n] = 0.75 * hmean + 0.25 * mean

        # contrarian: ưu tiên số mạnh nhưng không quá "nóng" đồng loạt
        models["contrarian"][n] = 0.60 * mean + 0.25 * (1 - min(1.0, support)) + 0.15 * (1 / (1 + spread))

    return models

def normalize(score_map):
    mx = max(score_map.values()) if score_map else 1.0
    if mx <= 0:
        return {n: 0.0 for n in NUMBERS}
    return {n: score_map[n] / mx for n in NUMBERS}

def choose_pair(score_map, top_n=24):
    score_map = normalize(score_map)
    candidates = sorted(NUMBERS, key=score_map.get, reverse=True)[:top_n]
    ranked = []
    for a, b in combinations(candidates, 2):
        indiv = (score_map[a] + score_map[b]) / 2
        balance = 1 / (1 + abs(score_map[a] - score_map[b]))
        ranked.append((0.90 * indiv + 0.10 * balance, a, b))
    ranked.sort(reverse=True)
    return [ranked[0][1], ranked[0][2]] if ranked else candidates[:2]

def combine_models(model_scores, weights):
    out = {n: 0.0 for n in NUMBERS}
    total = 0.0
    for name, scores in model_scores.items():
        w = max(0.0, float(weights.get(name, 0.0)))
        if w <= 0:
            continue
        norm = normalize(scores)
        for n in NUMBERS:
            out[n] += w * norm[n]
        total += w

    if total <= 0:
        # fallback đều
        names = list(model_scores.keys())
        if not names:
            return out
        w = 1 / len(names)
        for name in names:
            norm = normalize(model_scores[name])
            for n in NUMBERS:
                out[n] += w * norm[n]
        return out

    for n in NUMBERS:
        out[n] /= total
    return out
