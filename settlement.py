def last2(x):
    s="".join(ch for ch in str(x) if ch.isdigit())
    return s[-2:].zfill(2) if s else "00"

def _match_station(station,results):
    for k,v in results.items():
        a=station.lower().replace(".","").strip();b=k.lower().replace(".","").strip()
        if a in b or b in a:return v
    return None

def settle(prediction,results):
    song=prediction["song_thu"];db50=set(prediction["db50"])
    loto={n:{"total":0,"stations":{}} for n in song}
    db={"hits":0,"total_stations":0,"stations":{}}
    matched=0
    for station in prediction["stations"]:
        e=_match_station(station,results)
        if not e:continue
        matched+=1
        last=[last2(x) for x in e.get("all_prizes",[])]
        for n in song:
            c=last.count(n);loto[n]["stations"][station]=c;loto[n]["total"]+=c
        sp=e.get("special");hit=sp is not None and last2(sp) in db50
        db["stations"][station]={"special":sp,"last2":last2(sp) if sp is not None else None,"hit":hit}
        db["hits"]+=int(hit);db["total_stations"]+=1
    return matched==len(prediction["stations"]) and matched>0,loto,db
