from __future__ import annotations

from collections import Counter
from math import exp, sqrt

NUMBERS = [f"{i:02d}" for i in range(100)]


def _last2(value) -> str:
    s = "".join(ch for ch in str(value or "") if ch.isdigit())
    return s[-2:].zfill(2) if s else "00"


def _digit4(value) -> int:
    # GĐB MB 5 chữ số: chữ số thứ 4 từ trái = hàng chục của 2 số cuối.
    return int(_last2(value)[0])


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {n: 0.0 for n in NUMBERS}
    mx = max(scores.values())
    mn = min(scores.values())
    if mx <= mn:
        return {n: 0.0 for n in NUMBERS}
    return {n: (scores.get(n, 0.0) - mn) / (mx - mn) for n in NUMBERS}


def _chronological_specials(rows):
    # Storage trả newest -> oldest. Pattern cần oldest -> newest.
    ordered = sorted(
        [r for r in rows if r.get("special") is not None],
        key=lambda r: r.get("draw_date", ""),
    )
    return [str(r["special"]) for r in ordered]


def _state_series(specials, mode: str):
    out = []
    for sp in specials:
        d = _digit4(sp)
        if mode == "parity":
            out.append("C" if d % 2 == 0 else "L")
        elif mode == "size":
            out.append("X" if d <= 4 else "T")
        else:
            raise ValueError(mode)
    return out


def _runs(states):
    if not states:
        return []

    out = []
    cur = states[0]
    length = 1

    for s in states[1:]:
        if s == cur:
            length += 1
        else:
            out.append((cur, length))
            cur = s
            length = 1

    out.append((cur, length))
    return out


def _bayes_prob(weight_a, weight_b, alpha=2.0):
    total = weight_a + weight_b
    return (weight_a + alpha) / (total + 2 * alpha)


def _weighted_next_from_raw(states, suffix_len):
    if len(states) <= suffix_len:
        return None

    ctx = tuple(states[-suffix_len:])
    a = b = 0.0
    support = 0

    # Recency weighted historical matches.
    for i in range(suffix_len, len(states)):
        if tuple(states[i-suffix_len:i]) != ctx:
            continue

        age = len(states) - i
        w = 0.35 + 0.65 * exp(-age / 90.0)

        if states[i] == states[-1]:
            a += w
        else:
            b += w
        support += 1

    if support < 5:
        return None

    p_same = _bayes_prob(a, b)
    strength = min(1.0, support / 18.0) * min(1.0, suffix_len / 6.0)

    return {
        "type": "raw",
        "pattern": "".join(ctx),
        "support": support,
        "p_same": p_same,
        "strength": strength,
    }


def _run_signature(states, k):
    rr = _runs(states)
    if len(rr) < k:
        return None
    return tuple(length for _, length in rr[-k:])


def _weighted_next_from_runs(states, k):
    current_sig = _run_signature(states, k)
    if not current_sig:
        return None

    same_w = flip_w = 0.0
    support = 0

    # At each historical prediction point i, compare run-length suffix of states[:i].
    for i in range(3, len(states)):
        prev = states[:i]
        sig = _run_signature(prev, k)
        if sig != current_sig:
            continue

        age = len(states) - i
        w = 0.35 + 0.65 * exp(-age / 90.0)

        if states[i] == prev[-1]:
            same_w += w
        else:
            flip_w += w
        support += 1

    if support < 5:
        return None

    p_same = _bayes_prob(same_w, flip_w)
    pattern = "-".join(str(x) for x in current_sig)

    # Longer run-patterns only get high weight when support is adequate.
    strength = min(1.0, support / (8.0 + 2.5 * k)) * min(1.0, 0.45 + 0.14 * k)

    return {
        "type": "run",
        "pattern": pattern,
        "support": support,
        "p_same": p_same,
        "strength": strength,
    }


def _blet_model(states):
    if len(states) < 8:
        return None

    current = states[-1]
    run_len = 1
    for s in reversed(states[:-1]):
        if s == current:
            run_len += 1
        else:
            break

    same_w = flip_w = 0.0
    support = 0

    # Find moments with same current state and same current run length.
    for i in range(run_len, len(states)):
        prev = states[:i]
        if not prev or prev[-1] != current:
            continue

        r = 1
        for s in reversed(prev[:-1]):
            if s == current:
                r += 1
            else:
                break

        if r != run_len:
            continue

        age = len(states) - i
        w = 0.35 + 0.65 * exp(-age / 80.0)

        if states[i] == current:
            same_w += w
        else:
            flip_w += w
        support += 1

    if support < 5:
        return None

    return {
        "type": "blet",
        "pattern": f"bệt {current} {run_len} kỳ",
        "support": support,
        "p_same": _bayes_prob(same_w, flip_w),
        "strength": min(1.0, support / 16.0) * min(1.0, 0.55 + 0.08 * run_len),
        "run_len": run_len,
    }


def _predict_property_core(states):
    """
    Dynamic pattern mining:
    - raw suffix patterns 2..8 kỳ;
    - run-length patterns 2..5 đoạn: tự bắt 1-2-1, 3-3, 1-3-1-3...;
    - bệt hiện tại.
    Không có pattern hard-coded.
    """
    if len(states) < 20:
        return {
            "p_same": 0.5,
            "confidence": 0.0,
            "evidence": [],
        }

    evidence = []

    for L in range(2, 9):
        e = _weighted_next_from_raw(states, L)
        if e:
            evidence.append(e)

    for k in range(2, 6):
        e = _weighted_next_from_runs(states, k)
        if e:
            evidence.append(e)

    blet = _blet_model(states)
    if blet:
        evidence.append(blet)

    if not evidence:
        return {
            "p_same": 0.5,
            "confidence": 0.0,
            "evidence": [],
        }

    num = den = 0.0
    for e in evidence:
        # Evidence gần 50/50 tự giảm tác động.
        directional = abs(e["p_same"] - 0.5) * 2
        w = e["strength"] * (0.35 + 0.65 * directional)
        num += e["p_same"] * w
        den += w

    p_same = num / den if den else 0.5

    # Confidence vừa phụ thuộc độ lệch khỏi 50%, vừa phụ thuộc lượng evidence.
    total_strength = sum(e["strength"] for e in evidence)
    confidence = min(
        1.0,
        abs(p_same - 0.5) * 2.0
        * min(1.0, total_strength / 3.0),
    )

    evidence = sorted(
        evidence,
        key=lambda e: e["strength"] * abs(e["p_same"] - 0.5),
        reverse=True,
    )

    return {
        "p_same": p_same,
        "confidence": confidence,
        "evidence": evidence[:5],
    }


def _walkforward_reliability(states, max_tests=90):
    """
    Tự kiểm tra pattern trên phần lịch sử gần nhất.
    Nếu pattern gần đây không hơn 50/50, confidence hiện tại bị co xuống.
    """
    if len(states) < 45:
        return {
            "accuracy": 0.5,
            "trials": 0,
            "factor": 0.35,
        }

    start = max(25, len(states) - max_tests)
    wins = trials = 0
    weighted_wins = weighted_trials = 0.0

    for i in range(start, len(states)):
        pred = _predict_property_core(states[:i])
        conf = pred["confidence"]

        if conf < 0.08:
            continue

        current = states[i - 1]
        p_same = pred["p_same"]
        predicted = current if p_same >= 0.5 else ("L" if current == "C" else "C")

        # For size labels X/T instead of C/L.
        if current in {"X", "T"} and p_same < 0.5:
            predicted = "T" if current == "X" else "X"

        age = len(states) - i
        w = 0.40 + 0.60 * exp(-age / 45.0)

        trials += 1
        weighted_trials += w

        if predicted == states[i]:
            wins += 1
            weighted_wins += w

    if not trials or weighted_trials <= 0:
        return {
            "accuracy": 0.5,
            "trials": 0,
            "factor": 0.35,
        }

    accuracy = weighted_wins / weighted_trials

    # 50% => rất ít tin cậy; 62%+ => gần full.
    edge = max(0.0, accuracy - 0.50)
    sample_factor = min(1.0, trials / 30.0)
    factor = min(1.0, (edge / 0.12) * sample_factor)

    # Không cho về 0 hoàn toàn để pattern hiện tại vẫn được ghi nhận,
    # nhưng yếu thì gần như trung tính.
    factor = 0.20 + 0.80 * factor

    return {
        "accuracy": accuracy,
        "trials": trials,
        "factor": factor,
    }


def analyze_property(states, labels):
    """
    labels = (same-readable mapping supplied by caller)
    """
    core = _predict_property_core(states)
    wf = _walkforward_reliability(states)

    current = states[-1] if states else None
    other = None
    if current in {"C", "L"}:
        other = "L" if current == "C" else "C"
    elif current in {"X", "T"}:
        other = "T" if current == "X" else "X"

    # Shrink current probability toward 50% according to walk-forward quality.
    raw_p_same = core["p_same"]
    p_same = 0.5 + (raw_p_same - 0.5) * wf["factor"]
    confidence = core["confidence"] * wf["factor"]

    probs = {current: p_same, other: 1 - p_same} if current and other else {}

    pretty_evidence = []
    for e in core["evidence"]:
        next_state = current if e["p_same"] >= 0.5 else other
        pretty_evidence.append({
            "type": e["type"],
            "pattern": e["pattern"],
            "support": e["support"],
            "prediction": next_state,
            "prediction_label": labels.get(next_state, next_state),
            "rate": max(e["p_same"], 1 - e["p_same"]),
        })

    return {
        "current": current,
        "current_label": labels.get(current, current),
        "probabilities": probs,
        "confidence": confidence,
        "wf_accuracy": wf["accuracy"],
        "wf_trials": wf["trials"],
        "evidence": pretty_evidence[:4],
    }


def _window_frequency(rows, window):
    c = Counter()
    subset = rows[:window]
    for r in subset:
        if r.get("special") is not None:
            c[_last2(r["special"])] += 1

    mx = max(c.values()) if c else 0
    if mx <= 0:
        return {n: 0.0 for n in NUMBERS}

    return {n: c[n] / mx for n in NUMBERS}


def db_history_and_stability(rows):
    """
    rows newest -> oldest.
    History model và stability 30/60/90 là riêng cho 2 số cuối ĐB.
    """
    f30 = _window_frequency(rows, 30)
    f60 = _window_frequency(rows, 60)
    f90 = _window_frequency(rows, 90)
    f180 = _window_frequency(rows, 180)

    history = {
        n: (
            0.34 * f30[n]
            + 0.28 * f60[n]
            + 0.22 * f90[n]
            + 0.16 * f180[n]
        )
        for n in NUMBERS
    }

    stability = {}
    for n in NUMBERS:
        vals = [f30[n], f60[n], f90[n]]
        mean = sum(vals) / 3
        spread = max(vals) - min(vals)
        consistency = max(0.0, 1.0 - spread)

        # Một số phải vừa có strength vừa ổn định; all-zero không được thưởng.
        stability[n] = mean * (0.65 + 0.35 * consistency)

    return _normalize(history), _normalize(stability)



def analyze_digit4(rows):
    specials = _chronological_specials(rows)

    parity_states = _state_series(specials, "parity")
    size_states = _state_series(specials, "size")

    parity = analyze_property(
        parity_states,
        {"C": "Chẵn", "L": "Lẻ"},
    )
    size = analyze_property(
        size_states,
        {"X": "Xỉu", "T": "Tài"},
    )

    pp = parity.get("probabilities", {})
    sp = size.get("probabilities", {})

    # Mỗi hệ nhị phân chọn đúng 1 trạng thái mạnh hơn theo cầu lịch sử.
    parity_pick = "C" if pp.get("C", 0.5) >= pp.get("L", 0.5) else "L"
    size_pick = "X" if sp.get("X", 0.5) >= sp.get("T", 0.5) else "T"

    parity_pick_prob = float(pp.get(parity_pick, 0.5))
    size_pick_prob = float(sp.get(size_pick, 0.5))

    # Xếp độ mạnh hai yếu tố để hiển thị.
    chosen_factors = [
        {
            "code": parity_pick,
            "label": {"C": "Chẵn", "L": "Lẻ"}[parity_pick],
            "probability": parity_pick_prob,
            "confidence": parity.get("confidence", 0.0),
            "system": "parity",
        },
        {
            "code": size_pick,
            "label": {"X": "Xỉu", "T": "Tài"}[size_pick],
            "probability": size_pick_prob,
            "confidence": size.get("confidence", 0.0),
            "system": "size",
        },
    ]
    chosen_factors.sort(
        key=lambda x: (x["probability"] - 0.5) * max(0.05, x["confidence"]),
        reverse=True,
    )

    # Giao của 2 điều kiện => đầu số chữ số thứ 4.
    candidate_digits = []
    for d in range(10):
        parity_ok = (d % 2 == 0) if parity_pick == "C" else (d % 2 == 1)
        size_ok = (d <= 4) if size_pick == "X" else (d >= 5)
        if parity_ok and size_ok:
            candidate_digits.append(d)

    # 50% cầu số 4:
    # - số khớp CẢ HAI trạng thái được điểm mạnh nhất;
    # - khớp 1 trạng thái vẫn có điểm phụ;
    # - không khớp trạng thái nào gần như không được điểm.
    #
    # Độ mạnh từng hệ được điều chỉnh theo xác suất + confidence walk-forward.
    parity_strength = max(
        0.0,
        (parity_pick_prob - 0.5) * 2
        * max(0.15, parity.get("confidence", 0.0)),
    )
    size_strength = max(
        0.0,
        (size_pick_prob - 0.5) * 2
        * max(0.15, size.get("confidence", 0.0)),
    )

    # Khi cả hai tín hiệu đều yếu, vẫn giữ neutral chứ không ép đầu.
    total_strength = parity_strength + size_strength
    if total_strength <= 1e-9:
        wp = ws = 0.5
    else:
        wp = parity_strength / total_strength
        ws = size_strength / total_strength

    scores = {}
    match_info = {}

    for n in NUMBERS:
        d = int(n[0])

        parity_match = ((d % 2 == 0) and parity_pick == "C") or (
            (d % 2 == 1) and parity_pick == "L"
        )
        size_match = ((d <= 4) and size_pick == "X") or (
            (d >= 5) and size_pick == "T"
        )

        # Base score theo từng yếu tố thắng.
        component = 0.0
        component += wp * (1.0 if parity_match else 0.0)
        component += ws * (1.0 if size_match else 0.0)

        # Intersection bonus: đúng cả 2 điều kiện là nhóm đầu ưu tiên nhất.
        if parity_match and size_match:
            component = min(1.0, component + 0.22)

        # Khi confidence rất thấp, co component về 0.5 để tránh ép cầu yếu.
        combined_conf = min(
            1.0,
            0.5 * float(parity.get("confidence", 0.0))
            + 0.5 * float(size.get("confidence", 0.0)),
        )
        component = 0.5 + (component - 0.5) * combined_conf

        scores[n] = component
        match_info[n] = {
            "digit4": d,
            "parity_match": parity_match,
            "size_match": size_match,
        }

    return {
        "scores": scores,
        "parity": parity,
        "size": size,

        "parity_pick": parity_pick,
        "parity_pick_label": {"C": "Chẵn", "L": "Lẻ"}[parity_pick],
        "parity_pick_prob": parity_pick_prob,

        "size_pick": size_pick,
        "size_pick_label": {"X": "Xỉu", "T": "Tài"}[size_pick],
        "size_pick_prob": size_pick_prob,

        "chosen_factors": chosen_factors,
        "candidate_digits": candidate_digits,
        "candidate_digits_text": "".join(str(x) for x in candidate_digits),

        "parity_weight": wp,
        "size_weight": ws,
        "sample": len(specials),
        "match_info": match_info,
    }
