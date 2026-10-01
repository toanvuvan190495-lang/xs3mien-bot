from __future__ import annotations
from collections import Counter
from itertools import combinations
from final_models import score_model, normalize

NUMBERS=[f"{i:02d}" for i in range(100)]

def _rank_scores(mentions):
    c=Counter(x for x in mentions if x in NUMBERS)
    mx=max(c.values()) if c else 1
    return {n:c.get(n,0)/mx for n in NUMBERS}

def _add(target,comp,weight):
    for n in NUMBERS: target[n]+=weight*comp.get(n,0)

def station_score_bundle(api_stats,history_scores=None,external_api=None,region="MN"):
    loto={n:0.0 for n in NUMBERS}; db={n:0.0 for n in NUMBERS}
    if history_scores:
        _add(loto,history_scores[0],{"MN":.30,"MT":.34,"MB":.42}.get(region,.30))
        _add(db,history_scores[1],{"MN":.32,"MT":.34,"MB":.38}.get(region,.32))
    return loto,db

def community_scores(source_records,reliability_lookup):
    raw_l={n:0.0 for n in NUMBERS}; raw_d={n:0.0 for n in NUMBERS}
    acl=Counter(); acd=Counter(); detail=[]; twl=twd=0.0
    active=[r for r in source_records if r.get("ok")]

    for rec in active:
        rel=reliability_lookup(rec["source"]); base=float(rec.get("base_weight",1.0))
        wl=base*(.45+.55*rel["loto"]); wd=base*(.45+.55*rel["db"])
        ls=list(dict.fromkeys(rec.get("loto",[])))[:30]
        ds=list(dict.fromkeys(rec.get("db",[])))[:70]

        for rank,n in enumerate(ls):
            if n in raw_l:
                raw_l[n]+=wl*max(.20,1-rank*.035); acl[n]+=1
        for rank,n in enumerate(ds):
            if n in raw_d:
                raw_d[n]+=wd*max(.15,1-rank*.018); acd[n]+=1

        twl+=wl; twd+=wd
        detail.append({"source":rec["source"],"kind":rec.get("kind"),
                       "reliability":rel,"loto":ls[:12],"db":ds[:20]})

    if twl:
        for n in NUMBERS:
            raw_l[n]/=twl
            a=acl[n]
            if a>=5: raw_l[n]*=1.45
            elif a>=4: raw_l[n]*=1.35
            elif a>=3: raw_l[n]*=1.22
            elif a>=2: raw_l[n]*=1.10

    if twd:
        for n in NUMBERS:
            raw_d[n]/=twd
            a=acd[n]
            if a>=5: raw_d[n]*=1.35
            elif a>=4: raw_d[n]*=1.28
            elif a>=3: raw_d[n]*=1.18
            elif a>=2: raw_d[n]*=1.08

    return raw_l,raw_d,detail,{
        "active_sources":len(active),
        "loto_agreement":dict(acl),
        "db_agreement":dict(acd),
    }

def _web_weight(active,region):
    table={0:0,1:.08,2:.14,3:.19,4:.23,5:.26}
    base=table.get(active,.29)
    return min(base,{"MN":.30,"MT":.30,"MB":.32}.get(region,.30))

def _choose_pair(scores,agreement,active,top_n=26):
    cand=sorted(NUMBERS,key=scores.get,reverse=True)[:top_n]
    allp=[]; gated=[]

    for a,b in combinations(cand,2):
        indiv=(scores[a]+scores[b])/2
        bal=1/(1+abs(scores[a]-scores[b]))
        aa=int(agreement.get(a,0)); bb=int(agreement.get(b,0))
        consensus=min(.10,.0175*(aa+bb))
        s=.90*indiv+.10*bal+consensus
        item=(s,a,b,aa,bb); allp.append(item)

        if active>=4:
            if max(aa,bb)>=2 or aa+bb>=2: gated.append(item)
        else:
            gated.append(item)

    pool=gated or allp
    pool.sort(reverse=True)
    if not pool: return cand[:2],{}
    _,a,b,aa,bb=pool[0]
    return [a,b],{"a_sources":aa,"b_sources":bb,"gate_used":active>=4 and bool(gated)}

def aggregate_region(station_bundles,community=None,community_max_weight=.32,
                     region="MN",selected_model="mean",community_meta=None):
    loto=score_model(selected_model,station_bundles)
    active=(community_meta or {}).get("active_sources",0)

    if community:
        cl,cd=community
        w=min(_web_weight(active,region),community_max_weight)
        cln=normalize(cl)
        for n in NUMBERS: loto[n]=(1-w)*loto[n]+w*cln.get(n,0)

    st,gate=_choose_pair(loto,(community_meta or {}).get("loto_agreement",{}),active)

    db={n:0.0 for n in NUMBERS}
    for n in NUMBERS:
        vals=[b[1][n] for b in station_bundles.values()]
        db[n]=sum(vals)/len(vals)

    if community:
        cdn=normalize(community[1]); dbw=min(.32,.10+.035*active)
        for n in NUMBERS: db[n]=(1-dbw)*db[n]+dbw*cdn.get(n,0)

    db50=sorted(NUMBERS,key=db.get,reverse=True)[:50]
    ln=normalize(loto); dn=normalize(db)

    return st,db50,{
        "loto":{n:round(ln[n]*100,1) for n in NUMBERS},
        "db":{n:round(dn[n]*100,1) for n in NUMBERS},
        "selected_model":selected_model,
        "web_weight":round(_web_weight(active,region),3),
        "active_sources":active,
        "consensus_gate":gate,
    }

def explain(song_thu,bundles,display):
    out=[]
    for n in song_thu:
        vals={st:round(b[0][n],3) for st,b in bundles.items()}
        out.append({"number":n,"region_score":display["loto"][n],
                    "stations_supporting":f"{sum(v>0 for v in vals.values())}/{len(vals)}",
                    "station_raw":vals})
    out.append({"selected_model":display.get("selected_model"),
                "web_weight":display.get("web_weight"),
                "active_sources":display.get("active_sources"),
                "consensus_gate":display.get("consensus_gate")})
    return out
