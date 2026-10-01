from __future__ import annotations
from itertools import combinations

NUMBERS = [f"{i:02d}" for i in range(100)]

def normalize(scores):
    mx = max(scores.values()) if scores else 1.0
    mn = min(scores.values()) if scores else 0.0
    if mx <= mn:
        return {n: 0.0 for n in NUMBERS}
    return {n: (scores.get(n, 0.0)-mn)/(mx-mn) for n in NUMBERS}

def _station_values(station_bundles, n):
    return [bundle[0][n] for bundle in station_bundles.values()]

def model_mean(station_bundles):
    out = {}
    for n in NUMBERS:
        vals = _station_values(station_bundles, n)
        out[n] = sum(vals) / len(vals)
    return normalize(out)

def model_balanced(station_bundles):
    out = {}
    for n in NUMBERS:
        vals = _station_values(station_bundles, n)
        mean = sum(vals) / len(vals)
        spread = max(vals) - min(vals) if vals else 0
        out[n] = 0.60*mean + 0.20*min(vals) + 0.20*(1/(1+spread))
    return normalize(out)

def model_coverage(station_bundles):
    out = {}
    count = len(station_bundles)
    for n in NUMBERS:
        vals = _station_values(station_bundles, n)
        mean = sum(vals) / count
        mx = max(vals) if vals else 0
        support = sum(v >= mx*0.60 and v > 0 for v in vals) / count if mx else 0
        spread = max(vals) - min(vals) if vals else 0
        out[n] = 0.50*mean + 0.30*support + 0.20*(1/(1+spread))
    return normalize(out)

def model_rank_borda(station_bundles):
    out = {n: 0.0 for n in NUMBERS}
    count = len(station_bundles)
    for _, bundle in station_bundles.items():
        ranked = sorted(NUMBERS, key=bundle[0].get, reverse=True)
        for rank, n in enumerate(ranked):
            if rank < 10:
                pts = 1.0 - rank*0.05
            elif rank < 25:
                pts = 0.5 - (rank-10)*0.02
            else:
                pts = 0.0
            out[n] += max(0.0, pts)
    for n in NUMBERS:
        out[n] /= count
    return normalize(out)

def model_v24_mt(station_bundles):
    out = {}
    count = len(station_bundles)
    for n in NUMBERS:
        vals = _station_values(station_bundles, n)
        mean = sum(vals) / count
        mx = max(vals) if vals else 0
        support = sum(v >= mx*0.60 and v > 0 for v in vals) / count if mx else 0
        spread = max(vals) - min(vals) if vals else 0
        out[n] = 0.50*mean + 0.24*support + 0.16*min(vals) + 0.10*(1/(1+spread))
    return normalize(out)

def model_v24_mb(station_bundles):
    out = {}
    for n in NUMBERS:
        vals = _station_values(station_bundles, n)
        mean = sum(vals) / len(vals)
        spread = max(vals) - min(vals) if vals else 0
        out[n] = 0.70*mean + 0.18*min(vals) + 0.12*(1/(1+spread))
    return normalize(out)

MODEL_FUNCS = {
    "mean": model_mean,
    "balanced": model_balanced,
    "coverage": model_coverage,
    "rank_borda": model_rank_borda,
    "v24_mt": model_v24_mt,
    "v24_mb": model_v24_mb,
}

REGION_CANDIDATES = {
    "MN": ["mean", "balanced", "coverage", "rank_borda"],
    "MT": ["v24_mt", "mean", "balanced", "rank_borda"],
    "MB": ["v24_mb", "mean", "balanced", "rank_borda"],
}

def score_model(name, station_bundles):
    return MODEL_FUNCS[name](station_bundles)

def choose_pair(score_map, top_n=24):
    candidates = sorted(NUMBERS, key=score_map.get, reverse=True)[:top_n]
    ranked = []
    for a, b in combinations(candidates, 2):
        indiv = (score_map[a] + score_map[b]) / 2
        balance = 1 / (1 + abs(score_map[a] - score_map[b]))
        ranked.append((0.92*indiv + 0.08*balance, a, b))
    ranked.sort(reverse=True)
    return [ranked[0][1], ranked[0][2]] if ranked else candidates[:2]
