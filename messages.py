def _pct(v):
    try:
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return "-"


def _pattern_lines(info, max_items=2):
    rows = []
    for e in (info or {}).get("evidence", [])[:max_items]:
        kind = e.get("type", "")

        if kind == "run":
            label = f"nhịp {e.get('pattern')}"
        elif kind == "blet":
            label = e.get("pattern", "bệt")
        else:
            label = f"chuỗi {e.get('pattern')}"

        rows.append(
            f"• {label} → {e.get('prediction_label', '?')} "
            f"{_pct(e.get('rate', 0.5))} ({e.get('support', 0)} mẫu)"
        )
    return rows


def format_prediction(p):
    db64 = list(p.get("db50", []))[:64]
    rows = [
        " ".join(db64[i:i+10])
        for i in range(0, len(db64), 10)
    ]

    score = p["scores"]["song_thu"]
    comm = p.get("community", {})
    srcs = comm.get("sources", [])
    active = comm.get("active_sources", len(srcs))

    names = (
        ", ".join(x["source"] for x in srcs)
        if srcs
        else "không có"
    )
    agree = comm.get("loto_agreement", {})
    st_agree = " | ".join(
        f"{n}: {agree.get(n, 0)} nguồn"
        for n in p["song_thu"]
    )

    d4 = (p.get("scores") or {}).get("db_digit4", {})
    parity = d4.get("parity", {})
    size = d4.get("size", {})

    pp = parity.get("probabilities", {})
    sp = size.get("probabilities", {})

    sample = int(d4.get("sample", 0))
    history_ready = bool(d4.get("history_ready", False))

    picked_parity = d4.get("parity_pick_label", "—")
    picked_size = d4.get("size_pick_label", "—")

    parity_prob = float(d4.get("parity_pick_prob", 0.5))
    size_prob = float(d4.get("size_pick_prob", 0.5))

    parity_status = d4.get("parity_status", "insufficient")
    size_status = d4.get("size_status", "insufficient")

    digits = d4.get("candidate_digits_text", "—")

    d4_lines = [
        "🔢 <b>CẦU SỐ 4 GIẢI ĐB</b>",
        f"📚 Lịch sử: <b>{sample} kỳ</b> → "
        + (
            "<b>ĐỦ DỮ LIỆU</b>"
            if history_ready
            else "<b>CHƯA ĐỦ DỮ LIỆU</b>"
        ),
        "",
    ]

    if not history_ready:
        d4_lines += [
            "⚠️ Chưa đủ lịch sử để phân tích Chẵn/Lẻ và Tài/Xỉu.",
            "Cầu số 4 giữ trung tính, không khóa đầu.",
        ]
    else:
        # Chẵn/Lẻ
        d4_lines += [
            "<b>Chẵn/Lẻ:</b>",
            f"Chẵn {_pct(pp.get('C', 0.5))}"
            f" | Lẻ {_pct(pp.get('L', 0.5))}",
        ]

        if parity_status == "strong":
            d4_lines.append(
                f"✅ Nghiêng <b>{picked_parity} "
                f"{_pct(parity_prob)}</b>"
            )
        else:
            d4_lines.append(
                f"⚠️ Tín hiệu yếu / xung đột cầu"
                f" → tạm nghiêng <b>{picked_parity} "
                f"{_pct(parity_prob)}</b>"
            )

        d4_lines += ["", "<b>Tài/Xỉu:</b>"]
        d4_lines.append(
            f"Xỉu {_pct(sp.get('X', 0.5))}"
            f" | Tài {_pct(sp.get('T', 0.5))}"
        )

        if size_status == "strong":
            d4_lines.append(
                f"✅ Nghiêng <b>{picked_size} "
                f"{_pct(size_prob)}</b>"
            )
        else:
            d4_lines.append(
                f"⚠️ Tín hiệu yếu / xung đột cầu"
                f" → tạm nghiêng <b>{picked_size} "
                f"{_pct(size_prob)}</b>"
            )

        d4_lines += [
            "",
            "⚖️ <b>Phân bổ trong 40% cầu số 4:</b>",
            f"{picked_parity}: "
            f"{_pct(d4.get('parity_weight', 0.5))}"
            f" | {picked_size}: "
            f"{_pct(d4.get('size_weight', 0.5))}",
        ]

        if digits != "—":
            strong_labels = []
            if d4.get("parity_strong"):
                strong_labels.append(picked_parity)
            if d4.get("size_strong"):
                strong_labels.append(picked_size)

            d4_lines += [
                f"🎯 Yếu tố mạnh dùng để khóa đầu: "
                f"<b>{' + '.join(strong_labels)}</b>",
                f"🔒 Đầu số ưu tiên: <b>{digits}</b>",
            ]
        else:
            d4_lines += [
                "📌 Cả hai nhánh hiện đều yếu/xung đột.",
                "Không khóa cứng đầu; chỉ dùng cầu như điểm mềm.",
            ]

    p_lines = _pattern_lines(parity, 2)
    s_lines = _pattern_lines(size, 2)

    if p_lines:
        d4_lines += [
            "",
            "🧬 <b>Cầu Chẵn/Lẻ</b>",
        ] + p_lines

    if s_lines:
        d4_lines += [
            "",
            "🧬 <b>Cầu Tài/Xỉu</b>",
        ] + s_lines

    formula = (
        "🧮 <b>ĐB64:</b> 20% lịch sử ĐB"
        " + 40% cầu số 4"
        " + 20% stability 30/60/90"
        " + 20% web\n"
        "📌 Nhánh cầu mạnh được ưu tiên; nhánh yếu chỉ giảm trọng số, "
        "không làm mất tín hiệu của nhánh còn lại."
    )

    return (
        f"🔮 <b>MIỀN BẮC – CHỐT HÔM NAY</b>\n"
        f"📅 {p['draw_date']}\n"
        f"🏢 Đài: {', '.join(p['stations'])}\n\n"

        f"🔥 <b>SONG THỦ: {' – '.join(p['song_thu'])}</b>\n"
        f"📊 "
        + " | ".join(
            f"{n}: {score.get(n, 0):.1f}/100"
            for n in p["song_thu"]
        )
        + "\n"
        f"🌐 Đồng thuận web: {st_agree}\n"
        f"🧠 Model STL: "
        f"{p['scores'].get('selected_model', '')}\n\n"

        + "\n".join(d4_lines)
        + "\n\n"
        + formula
        + "\n\n"

        f"🎯 <b>DÀN ĐB64 – 64 SỐ SCORE CAO NHẤT</b>\n"
        + "\n".join(rows)
        + f"\n\n🌐 Nguồn dùng được: <b>{active}</b>\n"
        f"🔎 {names}\n"
        f"<i>Chẵn/Lẻ và Tài/Xỉu được quyết định từ pattern lịch sử; "
        f"không có mẫu cố định. Bệt chỉ tính từ 5 kỳ liên tiếp.</i>"
    )
