from __future__ import annotations

from collections import Counter
from itertools import combinations

from final_models import score_model, normalize

NUMBERS = [f"{i:02d}" for i in range(100)]


def _add(target, comp, weight):
    for n in NUMBERS:
        target[n] += weight * comp.get(n, 0.0)


def station_score_bundle(api_stats, history_scores=None, external_api=None, region="MB"):
    """
    MB-only: history là nền chính. Giữ tuple (loto, db) để tương thích engine/selector.
    """
    loto = {n: 0.0 for n in NUMBERS}
    db = {n: 0.0 for n in NUMBERS}

    if history_scores:
        _add(loto, history_scores[0], 1.0)
        _add(db, history_scores[1], 1.0)

    return loto, db


def _effective_reliability(rel: dict, key: str):
    """
    Reliability đã có Beta smoothing trong storage.
    Tiếp tục co về 0.5 nếu số mẫu còn thấp.
    """
    raw = float(rel.get(key, 0.50))
    sample = int(rel.get(f"sample_{key}", 0))
    confidence = min(1.0, sample / 24.0)
    effective = 0.50 + (raw - 0.50) * confidence
    return effective, confidence


def community_scores(source_records, reliability_lookup):
    raw_l = {n: 0.0 for n in NUMBERS}
    raw_d = {n: 0.0 for n in NUMBERS}

    agree_l = Counter()
    agree_d = Counter()
    weighted_l = Counter()
    weighted_d = Counter()

    detail = []
    active = [r for r in source_records if r.get("ok")]

    total_l_weight = 0.0
    total_d_weight = 0.0
    source_quality = []

    for rec in active:
        rel = reliability_lookup(rec["source"])
        base = float(rec.get("base_weight", 1.0))

        rel_l, conf_l = _effective_reliability(rel, "loto")
        rel_d, conf_d = _effective_reliability(rel, "db")

        # Nguồn ít mẫu vẫn được dùng, nhưng không được tự động quá mạnh.
        wl = base * (0.65 + 0.70 * rel_l)
        wd = base * (0.65 + 0.70 * rel_d)

        ls = list(dict.fromkeys(rec.get("loto", [])))[:30]
        ds = list(dict.fromkeys(rec.get("db", [])))[:70]

        for rank, n in enumerate(ls):
            if n not in raw_l:
                continue
            rank_factor = max(0.18, 1.0 - rank * 0.034)
            raw_l[n] += wl * rank_factor
            agree_l[n] += 1
            weighted_l[n] += wl

        for rank, n in enumerate(ds):
            if n not in raw_d:
                continue
            rank_factor = max(0.15, 1.0 - rank * 0.017)
            raw_d[n] += wd * rank_factor
            agree_d[n] += 1
            weighted_d[n] += wd

        total_l_weight += wl
        total_d_weight += wd
        source_quality.append((rel_l + rel_d) / 2)

        detail.append({
            "source": rec["source"],
            "kind": rec.get("kind"),
            "reliability": rel,
            "effective_loto": round(rel_l, 3),
            "effective_db": round(rel_d, 3),
            "loto": ls[:12],
            "db": ds[:20],
        })

    if total_l_weight:
        for n in NUMBERS:
            raw_l[n] /= total_l_weight
            a = agree_l[n]
            if a >= 5:
                raw_l[n] *= 1.38
            elif a >= 4:
                raw_l[n] *= 1.30
            elif a >= 3:
                raw_l[n] *= 1.20
            elif a >= 2:
                raw_l[n] *= 1.10

    if total_d_weight:
        for n in NUMBERS:
            raw_d[n] /= total_d_weight
            a = agree_d[n]
            if a >= 5:
                raw_d[n] *= 1.30
            elif a >= 4:
                raw_d[n] *= 1.24
            elif a >= 3:
                raw_d[n] *= 1.16
            elif a >= 2:
                raw_d[n] *= 1.08

    quality = sum(source_quality) / len(source_quality) if source_quality else 0.50

    return raw_l, raw_d, detail, {
        "active_sources": len(active),
        "loto_agreement": dict(agree_l),
        "db_agreement": dict(agree_d),
        "loto_weighted_agreement": dict(weighted_l),
        "db_weighted_agreement": dict(weighted_d),
        "source_quality": quality,
    }


def _web_weight(active: int, meta: dict | None = None):
    # Sau khi bot trước cho thấy web có thể gây nhiễu, web được giới hạn chặt hơn.
    table = {
        0: 0.00,
        1: 0.05,
        2: 0.09,
        3: 0.13,
        4: 0.17,
        5: 0.20,
        6: 0.22,
    }
    base = table.get(active, 0.24)

    quality = float((meta or {}).get("source_quality", 0.50))
    # reliability 0.50 => giữ nguyên; tốt/xấu mới điều chỉnh nhẹ.
    factor = max(0.80, min(1.15, 1.0 + (quality - 0.50) * 1.5))
    return min(0.28, base * factor)


def _choose_pair(scores, agreement, weighted_agreement, active, top_n=24):
    candidates = sorted(NUMBERS, key=scores.get, reverse=True)[:top_n]
    ranked_all = []
    ranked_gate = []

    for a, b in combinations(candidates, 2):
        indiv = (scores[a] + scores[b]) / 2
        balance = 1 / (1 + abs(scores[a] - scores[b]))

        aa = int(agreement.get(a, 0))
        bb = int(agreement.get(b, 0))
        wa = float(weighted_agreement.get(a, 0.0))
        wb = float(weighted_agreement.get(b, 0.0))

        consensus = min(0.09, 0.014 * (aa + bb) + 0.004 * (wa + wb))
        pair_score = 0.91 * indiv + 0.09 * balance + consensus

        item = (pair_score, a, b, aa, bb, wa, wb)
        ranked_all.append(item)

        if active >= 4:
            # Ít nhất một số được ≥2 nguồn nhắc hoặc tổng cặp có ≥2 nguồn độc lập.
            if max(aa, bb) >= 2 or aa + bb >= 2:
                ranked_gate.append(item)
        else:
            ranked_gate.append(item)

    pool = ranked_gate or ranked_all
    pool.sort(reverse=True)

    if not pool:
        return candidates[:2], {}

    _, a, b, aa, bb, wa, wb = pool[0]
    return [a, b], {
        "a_sources": aa,
        "b_sources": bb,
        "a_weighted": round(wa, 3),
        "b_weighted": round(wb, 3),
        "gate_used": active >= 4 and bool(ranked_gate),
    }


def aggregate_region(
    station_bundles,
    community=None,
    community_max_weight=0.28,
    region="MB",
    selected_model="mean",
    community_meta=None,
):
    meta = community_meta or {}
    active = int(meta.get("active_sources", 0))

    # SONG THỦ
    loto = score_model(selected_model, station_bundles)
    web_w = min(_web_weight(active, meta), community_max_weight)

    if community and web_w > 0:
        cl = normalize(community[0])
        for n in NUMBERS:
            loto[n] = (1 - web_w) * loto[n] + web_w * cl.get(n, 0.0)

    song_thu, gate = _choose_pair(
        loto,
        meta.get("loto_agreement", {}),
        meta.get("loto_weighted_agreement", {}),
        active,
    )

    # ĐB64: history exact-DB + web DB reliability/consensus.
    db = {n: 0.0 for n in NUMBERS}
    for n in NUMBERS:
        vals = [bundle[1][n] for bundle in station_bundles.values()]
        db[n] = sum(vals) / max(1, len(vals))

    if community and web_w > 0:
        cd = normalize(community[1])

        # DB web weight thấp hơn/cùng mức song-thủ để tránh forum lấn át history.
        db_w = min(community_max_weight, web_w)

        for n in NUMBERS:
            db[n] = (1 - db_w) * db[n] + db_w * cd.get(n, 0.0)

            # Agreement bonus nhỏ, chỉ dùng để phân hạng các số sát nhau.
            a = int(meta.get("db_agreement", {}).get(n, 0))
            db[n] += min(0.07, 0.011 * a)

    loto_norm = normalize(loto)
    db_norm = normalize(db)

    # 64 số có score ĐB cao nhất.
    db64 = sorted(NUMBERS, key=db_norm.get, reverse=True)[:64]

    return song_thu, db64, {
        "loto": {n: round(loto_norm[n] * 100, 1) for n in NUMBERS},
        "db": {n: round(db_norm[n] * 100, 1) for n in NUMBERS},
        "selected_model": selected_model,
        "web_weight": round(web_w, 3),
        "active_sources": active,
        "source_quality": round(float(meta.get("source_quality", 0.50)), 3),
        "consensus_gate": gate,
    }


def explain(song_thu, bundles, display):
    out = []
    for n in song_thu:
        vals = {st: round(b[0][n], 3) for st, b in bundles.items()}
        out.append({
            "number": n,
            "region_score": display["loto"][n],
            "stations_supporting": f"{sum(v > 0 for v in vals.values())}/{len(vals)}",
            "station_raw": vals,
        })

    out.append({
        "selected_model": display.get("selected_model"),
        "web_weight": display.get("web_weight"),
        "active_sources": display.get("active_sources"),
        "source_quality": display.get("source_quality"),
        "consensus_gate": display.get("consensus_gate"),
    })
    return out
