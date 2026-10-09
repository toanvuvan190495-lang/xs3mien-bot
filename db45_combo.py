"""Independent DB fourth+fifth digit analysis; never modifies legacy DB64 scoring.

The fourth digit (from the left) is the tens digit of the special prize's last two
characters. The fifth digit is the units digit. All source rows must precede
prediction day; the caller already enforces that condition.
"""
from __future__ import annotations

from db_digit4 import analyze_property, _chronological_specials

DB45_STAKE_PER_NUMBER = 10_000
DB45_PAYOUT_IF_HIT = 990_000


def _labels(pick, kind):
    if kind == 'parity':
        return {'C': 'Chẵn', 'L': 'Lẻ'}.get(pick, '—')
    return {'X': 'Xỉu', 'T': 'Tài'}.get(pick, '—')


def _digits_for(parity_pick, size_pick, parity_strong, size_strong, history_ready):
    if not history_ready:
        return []
    # With no strong signal use the provisional intersection, clearly marked weak.
    # A strong single factor must not be overridden by the other weak factor.
    constrain_parity = parity_strong or not size_strong
    constrain_size = size_strong or not parity_strong
    digits = []
    for d in range(10):
        pm = (d % 2 == 0) if parity_pick == 'C' else (d % 2 == 1)
        sm = (d <= 4) if size_pick == 'X' else (d >= 5)
        if (not constrain_parity or pm) and (not constrain_size or sm):
            digits.append(d)
    return digits


def analyze_digit5(rows):
    """Use exactly the same pattern/min-support and walk-forward as digit4."""
    specials = _chronological_specials(rows)
    last_digits = [int(str(sp)[-1]) for sp in specials if str(sp)[-1:].isdigit()]
    parity_states = ['C' if d % 2 == 0 else 'L' for d in last_digits]
    size_states = ['X' if d <= 4 else 'T' for d in last_digits]
    parity = analyze_property(parity_states, {'C': 'Chẵn', 'L': 'Lẻ'})
    size = analyze_property(size_states, {'X': 'Xỉu', 'T': 'Tài'})

    sample = len(last_digits)
    ready = sample >= 20
    pp = parity.get('probabilities', {})
    sp = size.get('probabilities', {})
    parity_pick = ('C' if pp.get('C', 0.5) >= pp.get('L', 0.5) else 'L') if ready and pp else None
    size_pick = ('X' if sp.get('X', 0.5) >= sp.get('T', 0.5) else 'T') if ready and sp else None
    parity_strong = bool(ready and parity.get('ready') and parity.get('evidence') and float(parity.get('confidence', 0.0)) >= 0.03)
    size_strong = bool(ready and size.get('ready') and size.get('evidence') and float(size.get('confidence', 0.0)) >= 0.03)

    digits = _digits_for(parity_pick, size_pick, parity_strong, size_strong, ready)
    return {
        'sample': sample, 'history_ready': ready,
        'parity': parity, 'size': size,
        'parity_pick': parity_pick, 'size_pick': size_pick,
        'parity_pick_label': _labels(parity_pick, 'parity'),
        'size_pick_label': _labels(size_pick, 'size'),
        'parity_pick_prob': float(pp.get(parity_pick, 0.5)) if parity_pick else 0.5,
        'size_pick_prob': float(sp.get(size_pick, 0.5)) if size_pick else 0.5,
        'parity_status': 'strong' if parity_strong else 'weak' if ready else 'insufficient',
        'size_status': 'strong' if size_strong else 'weak' if ready else 'insufficient',
        'parity_strong': parity_strong, 'size_strong': size_strong,
        'candidate_digits': digits, 'candidate_digits_text': ''.join(map(str, digits)) if digits else '—',
        'provisional': bool(ready and not parity_strong and not size_strong),
    }


def build_db45_combo(digit4, digit5):
    """Cross-product (tens digit4 x units digit5), unique and sorted."""
    tens = [int(x) for x in digit4.get('candidate_digits', [])]
    # DB64 keeps no hard-locked tens if both branches weak. For this separate
    # combo only, generate provisional tens from digit4's stated picks.
    if not tens and digit4.get('history_ready'):
        tens = _digits_for(
            digit4.get('parity_pick'), digit4.get('size_pick'),
            bool(digit4.get('parity_strong')), bool(digit4.get('size_strong')),
            True,
        )
    units = [int(x) for x in digit5.get('candidate_digits', [])]

    numbers = sorted({f'{d4}{d5}' for d4 in tens for d5 in units})
    stake = DB45_STAKE_PER_NUMBER * len(numbers)
    return {
        'numbers': numbers, 'count': len(numbers),
        'tens': tens, 'units': units,
        'digit4_provisional': bool(tens and not digit4.get('candidate_digits')),
        'digit5_provisional': bool(digit5.get('provisional', False)),
        'stake_per_number': DB45_STAKE_PER_NUMBER,
        'capital': stake, 'payout_if_hit': DB45_PAYOUT_IF_HIT,
        'available': bool(numbers),
    }


def prediction_combo(prediction):
    """Single persistence accessor; scores_json already saved by old Storage."""
    scores = prediction.get('scores') or {}
    combo = scores.get('db45_combo')
    return combo if isinstance(combo, dict) else {}
