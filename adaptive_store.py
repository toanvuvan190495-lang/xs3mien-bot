from __future__ import annotations
import json
from datetime import datetime

def ensure_adaptive_tables(store):
    with store.connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS model_performance (
            region TEXT NOT NULL,
            model_name TEXT NOT NULL,
            window_name TEXT NOT NULL,
            trials INTEGER NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            edge_sum REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(region, model_name, window_name)
        );

        CREATE TABLE IF NOT EXISTS model_daily_results (
            draw_date TEXT NOT NULL,
            region TEXT NOT NULL,
            model_name TEXT NOT NULL,
            pair_json TEXT NOT NULL,
            hit INTEGER NOT NULL,
            baseline REAL NOT NULL,
            edge REAL NOT NULL,
            PRIMARY KEY(draw_date, region, model_name)
        );
        """)

def save_daily_model_result(store, draw_date, region, model_name, pair, hit, baseline):
    edge = float(hit) - float(baseline)
    with store.connect() as con:
        con.execute("""
        INSERT INTO model_daily_results(draw_date,region,model_name,pair_json,hit,baseline,edge)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(draw_date,region,model_name) DO UPDATE SET
            pair_json=excluded.pair_json,
            hit=excluded.hit,
            baseline=excluded.baseline,
            edge=excluded.edge
        """, (draw_date, region, model_name, json.dumps(pair), int(hit), float(baseline), edge))

def rolling_model_stats(store, region, before_date, limit_days=60):
    with store.connect() as con:
        rows = con.execute("""
        SELECT model_name, hit, baseline, edge
        FROM model_daily_results
        WHERE region=? AND draw_date<?
        ORDER BY draw_date DESC
        """, (region, before_date)).fetchall()

    grouped = {}
    seen_dates = {}
    for r in rows:
        name = r["model_name"]
        grouped.setdefault(name, [])
        if len(grouped[name]) < limit_days:
            grouped[name].append(dict(r))

    out = {}
    for name, items in grouped.items():
        if not items:
            continue
        trials = len(items)
        hit_rate = sum(x["hit"] for x in items) / trials
        baseline = sum(x["baseline"] for x in items) / trials
        edge = sum(x["edge"] for x in items) / trials
        out[name] = {
            "trials": trials,
            "hit_rate": hit_rate,
            "baseline": baseline,
            "edge": edge,
        }
    return out

def adaptive_weights(stats, model_names):
    """
    Trọng số mềm:
    - model mới/ít mẫu không bị loại
    - edge âm bị giảm mạnh
    - edge dương được tăng dần
    """
    weights = {}
    for name in model_names:
        s = stats.get(name)
        if not s:
            weights[name] = 1.0
            continue

        trials = s["trials"]
        edge = s["edge"]

        sample_factor = min(1.0, trials / 30.0)
        adjusted = edge * sample_factor

        if adjusted <= -0.05:
            w = 0.15
        elif adjusted < 0:
            w = 0.45
        elif adjusted < 0.02:
            w = 0.85
        elif adjusted < 0.05:
            w = 1.25
        else:
            w = 1.60

        weights[name] = w
    return weights
