from __future__ import annotations
import requests, re
from typing import Any

class LotteryAPI:
    def __init__(self, base_url, api_key, timeout=20):
        self.base=base_url.rstrip("/")
        self.session=requests.Session()
        if api_key: self.session.headers.update({"X-API-Key":api_key})
        self.session.headers.update({"Content-Type":"application/json","User-Agent":"XS3MienBot/2.0"})
        self.timeout=timeout

    def get(self,path,params=None):
        r=self.session.get(self.base+path,params=params or {},timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def recent_draws(self,region=None,province=None,limit=120,date=None,from_date=None,to_date=None):
        p={"limit":limit}
        if region:p["region"]=region
        if province:p["province"]=province
        if date:p["date"]=date
        if from_date:p["from_date"]=from_date
        if to_date:p["to_date"]=to_date
        return self.get("/api/v1/vietnam/draws",p)

    def stat(self,endpoint,region,province=None,**kwargs):
        p={"region":region}
        if province:p["province"]=province
        p.update(kwargs)
        return self.get(endpoint,p)

    def region_signal_bundle(self,region,province=None):
        eps={
            "hot":"/api/stats/hot-numbers","gap":"/api/stats/gap",
            "frequency":"/api/stats/frequency","pair":"/api/stats/pair-frequency",
            "cycle":"/api/stats/loto-cycle","weekday":"/api/stats/weekday",
            "fall":"/api/stats/lo-roi","sum":"/api/stats/theo-tong",
            "head_tail":"/api/stats/head-tail",
        }
        out={}
        for k,p in eps.items():
            try:out[k]=self.stat(p,region,province=province)
            except Exception as e:out[k]={"_error":str(e)}
        return out

    def external_predictions(self,region,province=None):
        eps={
            "song_thu":"/api/soi-cau/song-thu","bach_thu":"/api/soi-cau/bach-thu",
            "dan_de":"/api/soi-cau/dan-de","de_db":"/api/soi-cau/de-dac-biet",
            "ai":"/api/soi-cau/ai-predict",
        }
        out={}
        for k,p in eps.items():
            try:out[k]=self.stat(p,region,province=province)
            except Exception as e:out[k]={"_error":str(e)}
        return out

def _flatten_strings(obj):
    if isinstance(obj,dict):
        for v in obj.values():yield from _flatten_strings(v)
    elif isinstance(obj,list):
        for v in obj:yield from _flatten_strings(v)
    elif obj is not None:yield str(obj)

def extract_two_digit_mentions(obj):
    out=[]
    for s in _flatten_strings(obj):
        out += re.findall(r"(?<!\d)(\d{2})(?!\d)",s)
    return out

def normalize_results(payload):
    """Tolerant adapter -> {station:{special,all_prizes}}."""
    out={}
    def walk(x):
        if isinstance(x,list):
            for i in x:walk(i)
            return
        if not isinstance(x,dict):return
        station=x.get("province_name") or x.get("province") or x.get("station") or x.get("name") or x.get("dai")
        prizes=x.get("results") or x.get("prizes") or x.get("result")
        special=x.get("special") or x.get("db") or x.get("dac_biet")
        if station and (prizes is not None or special is not None):
            nums=[]
            if isinstance(prizes,dict):
                for v in prizes.values():
                    if isinstance(v,list):nums += [str(i) for i in v]
                    elif v is not None:nums.append(str(v))
                special=special or prizes.get("special") or prizes.get("db") or prizes.get("ĐB")
            elif isinstance(prizes,list):nums += [str(i) for i in prizes]
            if special is not None and str(special) not in nums:nums.append(str(special))
            out[str(station)]={"special":None if special is None else str(special),"all_prizes":nums}
        for v in x.values():
            if isinstance(v,(dict,list)):walk(v)
    walk(payload)
    return out
