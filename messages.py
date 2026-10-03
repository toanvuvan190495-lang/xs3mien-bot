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
    rows = [" ".join(db64[i:i+10]) for i in range(0, len(db64), 10)]

    score = p["scores"]["song_thu"]
    comm = p.get("community", {})
    srcs = comm.get("sources", [])
    active = comm.get("active_sources", len(srcs))

    names = ", ".join(x["source"] for x in srcs) if srcs else "không có"
    agree = comm.get("loto_agreement", {})
    st_agree = " | ".join(
        f"{n}: {agree.get(n, 0)} nguồn" for n in p["song_thu"]
    )

    d4 = (p.get("scores") or {}).get("db_digit4", {})
    parity = d4.get("parity", {})
    size = d4.get("size", {})

    pp = parity.get("probabilities", {})
    sp = size.get("probabilities", {})

    picked_parity = d4.get("parity_pick_label", "-")
    picked_size = d4.get("size_pick_label", "-")
    digits = d4.get("candidate_digits_text", "-")

    d4_lines = [
        "🔢 <b>CẦU SỐ 4 GIẢI ĐB</b>",
        f"Chẵn {_pct(pp.get('C', 0.5))} | Lẻ {_pct(pp.get('L', 0.5))}",
        f"Xỉu {_pct(sp.get('X', 0.5))} | Tài {_pct(sp.get('T', 0.5))}",
        "",
        f"✅ Chọn: <b>{picked_parity} + {picked_size}</b>",
        f"🎯 Đầu số ưu tiên: <b>{digits}</b>",
        f"⚖️ Trong 50% cầu: "
        f"{picked_parity} {_pct(d4.get('parity_weight', 0.5))}"
        f" | {picked_size} {_pct(d4.get('size_weight', 0.5))}",
    ]

    p_lines = _pattern_lines(parity, 2)
    s_lines = _pattern_lines(size, 2)

    if p_lines:
        d4_lines += ["", f"🧬 <b>Cầu {picked_parity}</b>"] + p_lines

    if s_lines:
        d4_lines += ["", f"🧬 <b>Cầu {picked_size}</b>"] + s_lines

    formula = (
        "🧮 <b>ĐB64:</b> 25% lịch sử + 50% cầu số 4 "
        "+ 15% stability 30/60/90 + 10% web"
    )

    return (
        f"🔮 <b>MIỀN BẮC – CHỐT HÔM NAY</b>\n"
        f"📅 {p['draw_date']}\n"
        f"🏢 Đài: {', '.join(p['stations'])}\n\n"

        f"🔥 <b>SONG THỦ: {' – '.join(p['song_thu'])}</b>\n"
        f"📊 "
        + " | ".join(
            f"{n}: {score.get(n, 0):.1f}/100" for n in p["song_thu"]
        )
        + "\n"
        f"🌐 Đồng thuận web: {st_agree}\n"
        f"🧠 Model STL: {p['scores'].get('selected_model', '')}\n\n"

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
