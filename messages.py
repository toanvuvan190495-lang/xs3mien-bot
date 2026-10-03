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
        f"🧠 Model: {p['scores'].get('selected_model', '')}\n"
        f"⚖️ Trọng số web: {round((p['scores'].get('web_weight') or 0)*100)}%\n\n"

        f"🎯 <b>DÀN ĐB64 – 64 SỐ SCORE CAO NHẤT</b>\n"
        + "\n".join(rows)
        + f"\n\n🌐 Nguồn dùng được: <b>{active}</b>\n"
        f"🔎 {names}\n"
        f"<i>Score chỉ là điểm xếp hạng theo dữ liệu, không phải xác suất trúng.</i>"
    )
