from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

NUM_RE = re.compile(r"(?<!\d)(\d{2})(?!\d)")

REGION_TERMS = {
    "MN": ["miền nam", "mien nam", "xsmn"],
    "MT": ["miền trung", "mien trung", "xsmt"],
    "MB": ["miền bắc", "mien bac", "xsmb"],
}

LOTO_KEYS = [
    "song thủ", "song thu", "bạch thủ", "bach thu", "lô tô", "loto",
    "cặp lô", "cap lo", "stl", "btl", "chốt số", "chot so",
    "cao thủ", "cao thu", "lô gan", "lo gan", "cặp số đẹp", "cap so dep",
    "cầu nhiều nháy", "cau nhieu nhay", "cầu về cả cặp", "cau ve ca cap"
]

DB_KEYS = [
    "đặc biệt", "dac biet", "dàn đề", "dan de", "đề đặc biệt",
    "de dac biet", "gđb", "gdb", "chạm đề", "cham de",
    "bảng đb", "bang db", "giải đặc biệt"
]

LINK_KEYS = [
    "soi cầu", "soi cau", "dự đoán", "du doan", "song thủ", "song thu",
    "bạch thủ", "bach thu", "xổ số", "xo so", "thảo luận", "thao luan",
    "chăn nuôi", "chan nuoi", "cao thủ", "cao thu", "lô gan", "lo gan",
    "thống kê", "thong ke", "cầu", "cau"
]

SOURCES = [
    {
        "name": "forumketqua", "kind": "forum",
        "base": "https://forumketqua.net/",
        "regions": ["MN","MT","MB"],
        "entry": {
            "MB": "https://forumketqua.net/forums/xo-so-mien-bac/",
            "MT": "https://forumketqua.net/forums/xo-so-mien-trung.18/",
            "MN": "https://forumketqua.net/forums/xo-so-mien-nam.20/",
        },
        "crawl": 8, "base_weight": 1.20,
    },
    {
        "name": "soicauxsmb", "kind": "community_rank",
        "base": "https://soicauxsmb.me/",
        "regions": ["MB"],
        "entry": {"MB": "https://soicauxsmb.me/"},
        "crawl": 3, "base_weight": 1.15,
    },
    {
        "name": "caudesongthu", "kind": "data_model",
        "base": "https://caudesongthu.com/",
        "regions": ["MN","MT","MB"],
        "entry": {"MN":"https://caudesongthu.com/","MT":"https://caudesongthu.com/","MB":"https://caudesongthu.com/"},
        "crawl": 7, "base_weight": 1.05,
    },
    {
        "name": "xsmnmobi", "kind": "statistics",
        "base": "https://xsmn.mobi/",
        "regions": ["MN","MT","MB"],
        "entry": {
            "MN": "https://xsmn.mobi/lo-gan-mn.html",
            "MT": "https://xsmn.mobi/lo-gan-mt.html",
            "MB": "https://xsmn.mobi/lo-gan-mb.html",
        },
        "crawl": 5, "base_weight": 1.00,
    },
    {
        "name": "xskt", "kind": "statistics",
        "base": "https://xskt.com.vn/",
        "regions": ["MN","MT","MB"],
        "entry": {"MN":"https://xskt.com.vn/","MT":"https://xskt.com.vn/","MB":"https://xskt.com.vn/"},
        "crawl": 8, "base_weight": 1.00,
    },
    {
        "name": "soicaumiennamchinhxac", "kind": "editorial",
        "base": "https://soicaumiennamchinhxac.com/",
        "regions": ["MN","MT","MB"],
        "entry": {"MN":"https://soicaumiennamchinhxac.com/","MT":"https://soicaumiennamchinhxac.com/","MB":"https://soicaumiennamchinhxac.com/"},
        "crawl": 5, "base_weight": 0.90,
    },
    {
        "name": "soicau666", "kind": "editorial",
        "base": "https://soicau666.com/",
        "regions": ["MN","MT","MB"],
        "entry": {"MN":"https://soicau666.com/","MT":"https://soicau666.com/","MB":"https://soicau666.com/"},
        "crawl": 5, "base_weight": 0.90,
    },
]

def _clean_html(html):
    soup=BeautifulSoup(html,"lxml")
    for t in soup(["script","style","noscript","svg","iframe"]):
        t.decompose()
    return soup," ".join(soup.stripped_strings)

def _same_domain(base,u):
    return urlparse(base).netloc.replace("www.","")==urlparse(u).netloc.replace("www.","")

def _window(text,keywords,radius=450):
    low=text.lower()
    chunks=[]
    for kw in keywords:
        pos=0
        while True:
            i=low.find(kw.lower(),pos)
            if i<0: break
            chunks.append(text[max(0,i-radius):min(len(text),i+radius)])
            pos=i+len(kw)
    return "\n".join(chunks)

def _discover(base,soup,region,max_links):
    terms=LINK_KEYS+REGION_TERMS.get(region,[])
    scored=[]
    for a in soup.find_all("a",href=True):
        label=" ".join(a.stripped_strings).strip().lower()
        href=urljoin(base,a.get("href"))
        if not href.startswith("http") or not _same_domain(base,href):
            continue
        score=sum(1 for k in terms if k in label)
        h=href.lower()
        if "soi-cau" in h or "soi-cau" in h.replace("_","-"): score+=3
        if "lo-gan" in h or "thong-ke" in h: score+=2
        if region.lower() in h: score+=1
        if score: scored.append((score,href))
    out=[]; seen=set()
    for _,href in sorted(scored,reverse=True):
        if href in seen: continue
        seen.add(href); out.append(href)
        if len(out)>=max_links: break
    return out

def _rank(nums,limit):
    c=Counter(n for n in nums if len(n)==2)
    return [n for n,_ in c.most_common(limit)]

def _extract_generic(text,region):
    rf=_window(text,REGION_TERMS.get(region,[]),1200)
    src=rf or text
    lt=_window(src,LOTO_KEYS,450)
    dt=_window(src,DB_KEYS,550)
    return _rank(NUM_RE.findall(lt),30),_rank(NUM_RE.findall(dt),70),(lt+"\n"+dt)[:2800]

def _extract_forum(text,region):
    focus=_window(text,["song thủ","bạch thủ","chốt","cầu lotto","đặc biệt","dàn","btđ","stđ","loto"],350)
    loto=NUM_RE.findall(_window(focus,LOTO_KEYS+["chốt","cầu lotto"],280))
    db=NUM_RE.findall(_window(focus,DB_KEYS+["btđ","stđ"],340))
    return _rank(loto,30),_rank(db,70),focus[:2800]

def _extract_soicauxsmb(text):
    loto=[]; db=[]
    for key in ["song thủ lô","bạch thủ lô","lô tô","btl","lô:"]:
        loto+=NUM_RE.findall(_window(text,[key],360))
    for key in ["đặc biệt","đb:","dàn đề","chạm"]:
        db+=NUM_RE.findall(_window(text,[key],470))
    return _rank(loto,30),_rank(db,70),_window(text,LOTO_KEYS+DB_KEYS,650)[:2800]

class CommunityCollector:
    def __init__(self,timeout=18):
        self.timeout=timeout
        self.s=requests.Session()
        self.s.headers.update({
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
            "Accept-Language":"vi-VN,vi;q=0.9,en;q=0.8",
        })

    def _get(self,url):
        last=None
        for _ in range(2):
            try:
                r=self.s.get(url,timeout=self.timeout,allow_redirects=True)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last=e
        raise last

    def fetch_source(self,spec,region,draw_date):
        entry=spec["entry"][region]
        html=self._get(entry)
        soup,text=_clean_html(html)
        pages=[(entry,text)]

        for u in _discover(spec["base"],soup,region,spec.get("crawl",4)):
            try:
                _,t=_clean_html(self._get(u))
                pages.append((u,t))
            except Exception:
                pass

        all_loto=[]; all_db=[]; excerpts=[]; used=[]

        for u,t in pages:
            if spec["name"]=="soicauxsmb":
                loto,db,ex=_extract_soicauxsmb(t)
            elif spec["kind"]=="forum":
                loto,db,ex=_extract_forum(t,region)
            else:
                loto,db,ex=_extract_generic(t,region)

            if loto or db:
                used.append(u)
                all_loto.extend(loto)
                all_db.extend(db)
                excerpts.append(ex)

        return {
            "source":spec["name"],"kind":spec["kind"],"base_weight":spec["base_weight"],
            "url":used[0] if used else entry,"urls":used,
            "loto":_rank(all_loto,30),"db":_rank(all_db,70),
            "excerpt":"\n".join(excerpts)[:3200],"ok":bool(all_loto or all_db),
        }

    def collect(self,region,draw_date):
        out=[]
        for spec in SOURCES:
            if region not in spec["regions"]: continue
            try:
                out.append(self.fetch_source(spec,region,draw_date))
            except Exception as e:
                out.append({
                    "source":spec["name"],"kind":spec["kind"],"base_weight":spec["base_weight"],
                    "loto":[],"db":[],"excerpt":"","ok":False,
                    "error":f"{type(e).__name__}: {e}",
                })
        return out
