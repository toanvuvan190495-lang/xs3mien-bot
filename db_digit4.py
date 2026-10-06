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

    # Quy ước người dùng: chỉ >= 5 kỳ liên tiếp mới được gọi là "bệt".
    # Chuỗi 2-4 kỳ chỉ được xử lý như run/nhịp thông thường.
    if run_len < 5:
        return None

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
            "ready": False,
            "reason": f"chỉ có {len(states)} kỳ, cần tối thiểu 20 kỳ",
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
            "ready": False,
            "reason": "chưa có pattern đủ số mẫu",
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
        "ready": True,
        "reason": "",
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
        "ready": bool(core.get("ready", False)),
        "reason": core.get("reason", ""),
        "sample": len(states),
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

    sample = len(specials)

    # ------------------------------------------------------------
    # V3.10:
    # "Đủ dữ liệu" chỉ phụ thuộc số kỳ lịch sử.
    # Tín hiệu mạnh/yếu là chuyện khác.
    # ------------------------------------------------------------
    history_ready = sample >= 20

    # Luôn xác định bên đang nghiêng nếu đã đủ lịch sử.
    parity_pick = None
    size_pick = None

    if history_ready and pp:
        parity_pick = (
            "C"
            if pp.get("C", 0.5) >= pp.get("L", 0.5)
            else "L"
        )

    if history_ready and sp:
        size_pick = (
            "X"
            if sp.get("X", 0.5) >= sp.get("T", 0.5)
            else "T"
        )

    parity_pick_prob = (
        float(pp.get(parity_pick, 0.5))
        if parity_pick is not None
        else 0.5
    )
    size_pick_prob = (
        float(sp.get(size_pick, 0.5))
        if size_pick is not None
        else 0.5
    )

    # Strong = pattern có evidence và confidence walk-forward đủ tốt.
    # Weak/conflict vẫn được dùng nhẹ, chứ không bị loại.
    parity_strong = bool(
        history_ready
        and parity.get("ready")
        and parity.get("evidence")
        and float(parity.get("confidence", 0.0)) >= 0.03
    )
    size_strong = bool(
        history_ready
        and size.get("ready")
        and size.get("evidence")
        and float(size.get("confidence", 0.0)) >= 0.03
    )

    parity_status = (
        "strong" if parity_strong
        else "weak" if history_ready
        else "insufficient"
    )
    size_status = (
        "strong" if size_strong
        else "weak" if history_ready
        else "insufficient"
    )

    # ------------------------------------------------------------
    # Trọng số nội bộ của component 40% cầu số 4.
    #
    # - cả hai mạnh: chia động theo chất lượng tín hiệu;
    # - 1 mạnh + 1 yếu: nhánh mạnh 80%, yếu 20%;
    # - cả hai yếu: 50/50 nhưng từng nhánh bị shrink mạnh về neutral.
    # ------------------------------------------------------------
    parity_conf = float(parity.get("confidence", 0.0))
    size_conf = float(size.get("confidence", 0.0))

    parity_edge = abs(parity_pick_prob - 0.5) * 2.0
    size_edge = abs(size_pick_prob - 0.5) * 2.0

    if parity_strong and size_strong:
        qp = max(0.01, parity_edge * max(0.10, parity_conf))
        qs = max(0.01, size_edge * max(0.10, size_conf))
        total = qp + qs
        wp = qp / total
        ws = qs / total
    elif parity_strong and not size_strong:
        wp, ws = 0.80, 0.20
    elif size_strong and not parity_strong:
        wp, ws = 0.20, 0.80
    else:
        wp, ws = 0.50, 0.50

    # ------------------------------------------------------------
    # HARD PRIORITY HEADS:
    # - cả 2 mạnh => giao Chẵn/Lẻ với Tài/Xỉu;
    # - chỉ CL mạnh => 5 đầu theo CL;
    # - chỉ TX mạnh => 5 đầu theo TX;
    # - cả 2 yếu => không khóa đầu.
    # ------------------------------------------------------------
    candidate_digits = []

    for d in range(10):
        parity_match = (
            parity_pick is not None
            and (
                ((d % 2 == 0) and parity_pick == "C")
                or ((d % 2 == 1) and parity_pick == "L")
            )
        )
        size_match = (
            size_pick is not None
            and (
                ((d <= 4) and size_pick == "X")
                or ((d >= 5) and size_pick == "T")
            )
        )

        if parity_strong and size_strong:
            keep = parity_match and size_match
        elif parity_strong:
            keep = parity_match
        elif size_strong:
            keep = size_match
        else:
            keep = False

        if keep:
            candidate_digits.append(d)

    # ------------------------------------------------------------
    # SCORE 00–99:
    # Mỗi nhánh luôn độc lập. Nhánh yếu chỉ tác động nhẹ.
    # ------------------------------------------------------------
    scores = {}
    match_info = {}

    # Strong branch gets full directional effect.
    # Weak/conflicting branch gets only 25% directional effect.
    parity_effect = (
        1.0 if parity_strong
        else 0.25 if history_ready
        else 0.0
    )
    size_effect = (
        1.0 if size_strong
        else 0.25 if history_ready
        else 0.0
    )

    for n in NUMBERS:
        d = int(n[0])

        parity_match = (
            parity_pick is not None
            and (
                ((d % 2 == 0) and parity_pick == "C")
                or ((d % 2 == 1) and parity_pick == "L")
            )
        )
        size_match = (
            size_pick is not None
            and (
                ((d <= 4) and size_pick == "X")
                or ((d >= 5) and size_pick == "T")
            )
        )

        # Probability-based branch score.
        # Match gets P(picked); mismatch gets 1-P(picked).
        pp_branch = (
            parity_pick_prob
            if parity_match
            else 1.0 - parity_pick_prob
        )
        ps_branch = (
            size_pick_prob
            if size_match
            else 1.0 - size_pick_prob
        )

        # Weak branch pulled strongly toward neutral 0.5.
        pp_eff = 0.5 + (pp_branch - 0.5) * parity_effect
        ps_eff = 0.5 + (ps_branch - 0.5) * size_effect

        component = wp * pp_eff + ws * ps_eff

        # Small intersection bonus only when BOTH systems are strong.
        if (
            parity_strong
            and size_strong
            and parity_match
            and size_match
        ):
            component = min(1.0, component + 0.08)

        scores[n] = component
        match_info[n] = {
            "digit4": d,
            "parity_match": parity_match,
            "size_match": size_match,
        }

    chosen_factors = [
        {
            "code": parity_pick,
            "label": {
                "C": "Chẵn",
                "L": "Lẻ",
            }.get(parity_pick, "—"),
            "probability": parity_pick_prob,
            "confidence": parity_conf,
            "system": "parity",
            "status": parity_status,
            "weight": wp,
        },
        {
            "code": size_pick,
            "label": {
                "X": "Xỉu",
                "T": "Tài",
            }.get(size_pick, "—"),
            "probability": size_pick_prob,
            "confidence": size_conf,
            "system": "size",
            "status": size_status,
            "weight": ws,
        },
    ]

    return {
        "scores": scores,
        "parity": parity,
        "size": size,

        "history_ready": history_ready,
        "sample": sample,

        "parity_pick": parity_pick,
        "parity_pick_label": {
            "C": "Chẵn",
            "L": "Lẻ",
        }.get(parity_pick, "—"),
        "parity_pick_prob": parity_pick_prob,
        "parity_status": parity_status,
        "parity_strong": parity_strong,

        "size_pick": size_pick,
        "size_pick_label": {
            "X": "Xỉu",
            "T": "Tài",
        }.get(size_pick, "—"),
        "size_pick_prob": size_pick_prob,
        "size_status": size_status,
        "size_strong": size_strong,

        "chosen_factors": chosen_factors,
        "candidate_digits": candidate_digits,
        "candidate_digits_text": (
            "".join(str(x) for x in candidate_digits)
            if candidate_digits
            else "—"
        ),

        # ready giờ có nghĩa: history đủ để phân tích,
        # không còn nghĩa cả 2 nhánh đều phải mạnh.
        "ready": history_ready,

        "parity_weight": wp,
        "size_weight": ws,
        "match_info": match_info,
    }

