from __future__ import annotations
import json, math
from datetime import timedelta

from config import DRAW_SCHEDULE
from history_features import build_history_scores
from scoring import station_score_bundle
from final_models import REGION_CANDIDATES, score_model, choose_pair

def last2(x):
    s = "".join(c for c in str(x) if c.isdigit())
    return s[-2:].zfill(2) if s else "00"

def baseline_prob(k):
    k = max(0, min(100, k))
    if k >= 99:
        return 1.0
    return 1 - math.comb(100-k, 2) / math.comb(100, 2)

def evaluate_model(store, region, model_name, asof_date, lookback_days=90):
    start = asof_date - timedelta(days=lookback_days)
    d = start
    hits = 0
    trials = 0
    baseline_sum = 0.0

    while d < asof_date:
        stations = DRAW_SCHEDULE[region][d.weekday()]
        bundles = {}
        actual = {}
        ok = True

        with store.connect() as con:
            for st in stations:
                hist = store.get_history(region, st, d.isoformat(), 365)
                if len(hist) < 12:
                    ok = False
                    break

                hs = build_history_scores(hist)
                bundles[st] = station_score_bundle({}, hs, None, region=region)

                row = con.execute(
                    "SELECT * FROM draw_history WHERE region=? AND station=? AND draw_date=?",
                    (region, st, d.isoformat())
                ).fetchone()

                if not row:
                    ok = False
                    break

                actual[st] = dict(row)

        if ok:
            scores = score_model(model_name, bundles)
            pair = choose_pair(scores, 24)

            actual_unique = set()
            for row in actual.values():
                prizes = json.loads(row["prizes_json"])
                actual_unique.update(last2(x) for x in prizes)

            hit = int(any(n in actual_unique for n in pair))
            hits += hit
            trials += 1
            baseline_sum += baseline_prob(len(actual_unique))

        d += timedelta(days=1)

    if trials == 0:
        return {"trials": 0, "hit_rate": 0.0, "baseline": 0.0, "edge": -999, "adjusted_edge": -999}

    hit_rate = hits / trials
    base = baseline_sum / trials
    edge = hit_rate - base
    shrink = min(1.0, trials / 45.0)

    return {
        "trials": trials,
        "hit_rate": hit_rate,
        "baseline": base,
        "edge": edge,
        "adjusted_edge": edge * shrink,
    }

def select_best_model(store, region, asof_date, lookback_days=90):
    stats = {}
    for name in REGION_CANDIDATES[region]:
        stats[name] = evaluate_model(store, region, name, asof_date, lookback_days)

    best = max(stats, key=lambda n: stats[n]["adjusted_edge"])
    if stats[best]["adjusted_edge"] < -0.03 and "mean" in stats:
        best = "mean"

    return best, stats
