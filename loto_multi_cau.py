from __future__ import annotations

"""STL V4.1: 27-prize structural signals, evaluated strictly one draw ahead.

The features here are hypotheses, NOT proven lottery laws. Each family is
validated against the same-day random-selection baseline using earlier draws.
Web/forum inputs are deliberately excluded from historical simulations because
there is no trustworthy time-stamped web archive in this project.

Input draws: oldest first, with {draw_date, prizes, counts}.
"""
from collections import Counter
from math import sqrt

NUMBERS = [f"{n:02d}" for n in range(100)]
PRIZE_LENGTHS = [5] * 10 + [4] * 10 + [3] * 3 + [2] * 4
FAMILIES = ('roi_27', 'db_g1_cross', 'g2_g3_cross', 'g4_g5_cross', 'two_day_cross')


def _last2(item):
    return str(item)[-2:]


def prepare_draws(rows):
    """Validate 27 ordered prizes; deduplicate by date; sort chronologically.

    Invalid/incomplete rows are ignored, never treated as structural samples.
    The historical caller must already restrict rows to dates before today.
    """
    valid = {}
    for row in rows or []:
        day = str(row.get('draw_date') or '')
        prizes = [str(x).strip() for x in (row.get('prizes') or [])]
        if not day or len(prizes) != 27:
            continue
        if any(not s.isdigit() or len(s) != need
               for s, need in zip(prizes, PRIZE_LENGTHS)):
            continue
        special = row.get('special')
        if special is not None and str(special) != prizes[0]:
            continue
        if day not in valid:
            valid[day] = {
                'draw_date': day,
                'prizes': prizes,
                'counts': Counter(_last2(s) for s in prizes),
            }
    return [valid[k] for k in sorted(valid)]


def family_candidates(draws, family):
    """Only use already-finalized draw(s) to make the NEXT draw's candidates."""
    if not draws:
        return set()
    current = [_last2(s) for s in draws[-1]['prizes']]
    if family == 'roi_27':
        return set(current)
    if family == 'db_g1_cross':
        a, b = current[0], current[1]
        return {a[0] + b[1], b[0] + a[1], a[1] + b[0], b[1] + a[0]}
    if family == 'g2_g3_cross':
        # G2 indices 2,3; G3 indices 4..9.
        lhs, rhs = current[2:4], current[4:7]
    elif family == 'g4_g5_cross':
        # G4 indices 10..13; G5 indices 14..19.
        lhs, rhs = current[10:13], current[14:17]
    elif family == 'two_day_cross':
        if len(draws) < 2:
            return set()
        prev = [_last2(s) for s in draws[-2]['prizes']]
        a, b = current[0], prev[0]
        c, d = current[1], prev[1]
        return {a[0] + b[1], b[0] + a[1], c[0] + d[1], d[0] + c[1]}
    else:
        raise ValueError(family)
    return {a[0]+b[1] for a in lhs for b in rhs} | {
        b[0]+a[1] for a in lhs for b in rhs
    }


def _family_quality(draws, family, tests=90):
    """Walk-forward validation for family from strictly earlier draws.

    Return conservative weight 0..1. Results are NOT calibrated odds.
    Use 30/60/90 windows; require >=30 settled historical trials.
    """
    end = len(draws)
    first = max(2, end - tests)
    results = []
    for i in range(first, end):
        candidates = family_candidates(draws[:i], family)
        if not candidates:
            continue
        outcome = draws[i]['counts']
        actual = sum(outcome.get(n, 0) for n in candidates)
        expected = sum(outcome.values()) * len(candidates) / 100.0
        # Normalize lift by candidate count, so a huge cover set is not favored.
        edge = (actual - expected) / max(2.0, sqrt(len(candidates)))
        results.append(edge)

    trials = len(results)
    def avg_tail(days):
        tail = results[-days:]
        return sum(tail) / len(tail) if tail else 0.0
    recent = avg_tail(30)
    medium = avg_tail(60)
    long = avg_tail(90)
    combined = .5*recent + .3*medium + .2*long
    # Deactivate unsupported / consistently failing hypotheses.
    if trials < 30 or combined <= 0.0:
        confidence = 0.0
    else:
        # High variance and overlapping windows -> strong shrink and hard cap.
        confidence = min(.85, .50*(trials/(trials+100.0)) * combined)
        if recent < 0.0:
            confidence *= .25
    return {
        'trials': trials,
        'edge_nhay': round(combined, 5),
        'edge_30': round(recent, 5),
        'edge_60': round(medium, 5),
        'edge_90': round(long, 5),
        'confidence': round(max(0.0, confidence), 5),
        'candidate_count': len(family_candidates(draws, family)),
    }


def structural_features(draws, pattern=None, calibrate=True):
    """Two outputs: structure (10%) and dynamic/structure consensus (5%).

    Neutral outputs when validation is weak; never hardcode a winning number.
    If calibrate=True, 90 historical draws of each family are assessed using
    only previous draws. Historical callers pass only the training prefix.
    """
    neutral = {n: .5 for n in NUMBERS}
    if len(draws) < 35:
        return neutral.copy(), neutral.copy(), {
            'available': False, 'history_rows': len(draws), 'families': {},
            'active_families': [], 'agreed_numbers': [],
        }
    quality = {}
    all_candidates = {}
    for name in FAMILIES:
        candidates = family_candidates(draws, name)
        all_candidates[name] = candidates
        quality[name] = _family_quality(draws, name) if calibrate else {
            'confidence': .1, 'trials': 0, 'edge_nhay': 0.0,
            'candidate_count': len(candidates),
        }
    weights = {name: float(quality[name]['confidence']) for name in FAMILIES}
    active = [name for name in FAMILIES if weights[name] >= .015 and all_candidates[name]]
    if not active:
        return neutral.copy(), neutral.copy(), {
            'available': True, 'history_rows': len(draws), 'families': quality,
            'active_families': [], 'agreed_numbers': [],
        }

    # Each family votes independently. Pooling uses weight per shortlisted
    # candidate to avoid 27-number "roi" dominating narrow crossing patterns.
    votes = Counter()
    supports = Counter()
    total = 0.0
    for name in active:
        candidates = all_candidates[name]
        weight = weights[name]
        total += weight
        for n in candidates:
            votes[n] += weight / sqrt(len(candidates))
            supports[n] += 1
    peak = max(votes.values()) if votes else 0.0
    # Strength is intentionally small until family performance is stable.
    trust = min(.65, total/1.5)
    structure = {
        n: .5 + .5*trust*(votes[n]/peak if peak else 0.0)
        for n in NUMBERS
    }

    # Agree with independent, validated structural templates AND a dynamic
    # pattern ranked in top quarter. This is only a minor (5%) component.
    if pattern:
        ranked = sorted(NUMBERS, key=lambda n:(-pattern.get(n,.5),n))[:25]
        dynamic_top = set(ranked)
    else:
        dynamic_top = set()
    agreed = {n for n in NUMBERS if supports[n] >= 2 and n in dynamic_top}
    consensus = {
        n: .5 + .5*trust*min(1.0, supports[n]/3.0)
        if n in agreed else .5
        for n in NUMBERS
    }
    return structure, consensus, {
        'available': True,
        'history_rows': len(draws),
        'families': quality,
        'active_families': active,
        'agreed_numbers': sorted(agreed),
    }
