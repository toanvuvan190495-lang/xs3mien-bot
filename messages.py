from config import REGION_NAMES
import json

def format_prediction(p):
    rows=[" ".join(p["db50"][i:i+10]) for i in range(0,50,10)]
    score=p["scores"]["song_thu"]
    comm=p.get("community",{})
    srcs=comm.get("sources",[])
    active=comm.get("active_sources",len(srcs))
    names=", ".join(x["source"] for x in srcs) if srcs else "không có"
    agree=comm.get("loto_agreement",{})
    st_agree=" | ".join(f"{n}: {agree.get(n,0)} nguồn" for n in p["song_thu"])

    return (
        f"🔮 <b>{p['region_name']} – CHỐT TOÀN MIỀN</b>\n"
        f"📅 {p['draw_date']}\n"
        f"🏢 Áp dụng chung: {', '.join(p['stations'])}\n\n"
        f"🔥 <b>SONG THỦ: {' – '.join(p['song_thu'])}</b>\n"
        f"📊 " + " | ".join(f"{n}: {score.get(n,0):.1f}/100" for n in p["song_thu"]) + "\n"
        f"🌐 Đồng thuận web: {st_agree}\n"
        f"🧠 Model lịch sử: {p['scores'].get('selected_model','')}\n"
        f"⚖️ Trọng số web hôm nay: {round((p['scores'].get('web_weight') or 0)*100)}%\n\n"
        f"🎯 <b>DÀN ĐB 50 SỐ</b>\n" + "\n".join(rows) +
        f"\n\n🌐 Nguồn web dùng được: <b>{active}</b>\n"
        f"🔎 {names}\n"
        f"<i>Score là điểm xếp hạng/đồng thuận, không phải xác suất trúng.</i>"
    )

def format_settlement(region,date,loto,db):
    lines=[f"✅ <b>ĐỐI SOÁT {REGION_NAMES[region]}</b>",f"📅 {date}","","🔥 <b>SONG THỦ</b>"]
    for n,i in loto.items():
        det=", ".join(f"{st}: {c} nháy" for st,c in i["stations"].items())
        lines.append(f"{n}: <b>{i['total']} nháy</b> ({det})")
    lines+=["","🎯 <b>DÀN ĐB50</b>"]
    for st,i in db["stations"].items():
        lines.append(f"{st}: {i['special']} → {i['last2']} {'✅' if i['hit'] else '❌'}")
    lines.append(f"➡️ <b>{db['hits']}/{db['total_stations']} đài</b>")
    return "\n".join(lines)

def format_daily_summary(date,rows):
    lines=[f"📊 <b>TỔNG KẾT 3 MIỀN</b>",f"📅 {date}",""]
    tl=dh=dt=settled=0
    for r in rows:
        lines.append(f"━━ <b>{REGION_NAMES[r['region']]}</b> ━━")
        if not r.get("loto_hits_json"):
            lines.append("Chưa đủ kết quả."); continue
        settled+=1
        l=json.loads(r["loto_hits_json"]); d=json.loads(r["db_hits_json"])
        for n,i in l.items():
            lines.append(f"{n}: {i['total']} nháy"); tl+=i["total"]
        lines.append(f"ĐB50: {d['hits']}/{d['total_stations']} đài")
        dh+=d["hits"]; dt+=d["total_stations"]; lines.append("")
    lines+=["━━━━━━━━━━━━━━",f"🎯 Tổng nháy STL: <b>{tl}</b>",
            f"🎯 ĐB50: <b>{dh}/{dt}</b> đài" if dt else "🎯 ĐB50: chưa có dữ liệu",
            f"✅ Đối soát: {settled}/3 miền"]
    return "\n".join(lines)
