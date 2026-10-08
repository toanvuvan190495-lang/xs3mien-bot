from __future__ import annotations

"""Song thủ V4: causal one-step-ahead scoring with walk-forward validation.

Only MB Song thủ uses this module. No changes to ĐB64, result parsing,
settlement, report scheduling or existing database schemas.

All arrays (rows) are newest-first. Only rows with draw_date < prediction date
are supplied by engine and each historical evaluation uses strictly earlier rows.
Scores are RELATIVE RANKS, never claimed to be calibrated probabilities.
"""
from collections import Counter
from itertools import combinations
from math import exp

NUMBERS = [f"{i:02d}" for i in range(100)]


def _last2(x):
    v = ''.join(c for c in str(x or '') if c.isdigit())
    return v[-2:].zfill(2) if v else '00'


def _norm(a):
    lo, hi = min(a.values()), max(a.values())
    if hi <= lo: return {n: 0.5 for n in NUMBERS}
    return {n: max(0.0, min(1.0, (a[n]-lo)/(hi-lo))) for n in NUMBERS}


def _prepare(rows):
    """Newest first -> oldest first counts, only validated 27-prize draws."""
    data = []
    used = set()
    for r in reversed(rows):
        day = str(r.get('draw_date', ''))
        if day in used: continue
        prizes = list(r.get('prizes', []))
        if len(prizes) != 27: continue
        cnt = Counter(_last2(x) for x in prizes)
        data.append((day, cnt))
        used.add(day)
    data.sort(key=lambda x:x[0])
    return [x[1] for x in data]


def _estimate_features(counts90):
    """For the NEXT day using at most 90 previous days, not today's results."""
    data = counts90[-90:]
    length = len(data)
    neutral = {n: 0.5 for n in NUMBERS}
    if length < 14:
        return {k:neutral.copy() for k in ('pattern','trend','rhythm','stability')}

    # Historical per-number count/27 day baseline, shrunk toward pooled avg.
    pooled_rate = sum(sum(c.values()) for c in data) / (100.0*length)
    pooled_rate = max(0.01, pooled_rate)
    historical = {n: sum(row[n] for row in data)/length for n in NUMBERS}
    shrunk_base = {
        n: (length*historical[n] + 22*pooled_rate)/(length+22)
        for n in NUMBERS
    }

    # Short-window trend must not dominate: 7d gets only 12%.
    windows=((7,.12),(14,.20),(30,.26),(60,.24),(90,.18))
    trend_rate = {n: 0.0 for n in NUMBERS}
    stability_rate = {n: 0.0 for n in NUMBERS}
    for w,weight in windows:
        subset=data[-w:]
        days=len(subset)
        rate={n:sum(row[n] for row in subset)/days for n in NUMBERS}
        for n in NUMBERS:
            smooth=(days*rate[n]+18*pooled_rate)/(days+18)
            trend_rate[n]+=weight*smooth
        if w in (14,30,60,90):
            for n in NUMBERS:
                stability_rate[n]+=smooth/4

    # Conditional next-day patterns from 2,3,4 prior-day presence states.
    # Each historical match has the FULL next day observable in the past.
    # Do not reward a recent hit automatically; learn what followed it.
    pattern_rate={}
    series={n:[int(row[n]>0) for row in data] for n in NUMBERS}
    for n in NUMBERS:
        s=series[n]
        numer=denom=0.0
        for k in (2,3,4):
            context=s[-k:]
            hits=total=0.0
            support=0
            for i in range(k,length):
                if s[i-k:i]!=context: continue
                age=length-i
                w=.40+.60*exp(-age/32.0)
                hits += data[i][n]*w
                total += w
                support+=1
            if support<5 or total<=0: continue
            # Bayesian shrink makes rare patterns less influential.
            p=(hits+16*shrunk_base[n])/(total+16)
            w=(0.85 if k==2 else 1.0 if k==3 else 1.05)*min(1.0,support/12.0)
            numer+=p*w
            denom+=w
        conditional=numer/denom if denom else shrunk_base[n]
        pattern_rate[n] = .78*conditional+.22*shrunk_base[n]

    # Pooled empirical gap hazard (not the fallacy 'overdue must appear').
    trial=Counter(); nxt_hits=Counter()
    for n in NUMBERS:
        gap=0
        s=series[n]
        for i in range(length-1):
            if s[i]: gap=0
            else: gap=min(16,gap+1)
            trial[gap]+=1
            nxt_hits[gap]+=data[i+1][n]
    rhythm_rate={}
    for n in NUMBERS:
        s=series[n]
        gap=0
        for v in reversed(s):
            if v: break
            gap+=1
        gap=min(16,gap)
        conditional=(nxt_hits[gap]+80*pooled_rate)/(trial[gap]+80)
        rhythm_rate[n]=.65*conditional+.35*pooled_rate

    # Historical stability: 14/30/60/90 rates and dispersion, not absolute frequency alone.
    stable={}
    for n in NUMBERS:
        spread=abs(trend_rate[n]-stability_rate[n])
        stable[n]=stability_rate[n]-0.25*spread

    # Normalize within features. Bounded 0..1 ranking is NOT a probability.
    return {
        'pattern': _norm(pattern_rate),
        'trend': _norm(trend_rate),
        'rhythm': _norm(rhythm_rate),
        'stability': _norm(stable),
    }


def _walkforward(counts, tests=90):
    """Simulate ranking before each day using ONLY earlier 90 days.

    Fixed component candidates are evaluated on total nháy, against a
    same-day random-two baseline. Market/web features are deliberately
    excluded from historical simulation (no archived timestamps of web
    snapshots -> including current web would leak future information).
    """
    keys=('pattern','trend','rhythm','stability','hybrid')
    results={k:[] for k in keys}
    first=max(90,len(counts)-tests)
    for i in range(first,len(counts)):
        past=counts[max(0,i-90):i]
        features=_estimate_features(past)
        hybrid={n:(.40*features['pattern'][n]+.30*features['trend'][n]
                   +.15*features['rhythm'][n]+.15*features['stability'][n])
                for n in NUMBERS}
        by_strategy={**features,'hybrid':hybrid}
        outcome=counts[i]
        day_baseline=sum(outcome.values())*2.0/100.0
        for k in keys:
            candidates=sorted(NUMBERS,key=lambda n:(-by_strategy[k][n],n))[:2]
            nhay=sum(outcome[n] for n in candidates)
            results[k].append((nhay,day_baseline))
    stats={}
    for k,values in results.items():
        by_window={}
        for days,wt in ((30,.50),(60,.30),(90,.20)):
            vals=values[-days:]
            if not vals: continue
            edge=sum(a-b for a,b in vals)/len(vals)
            # Conservative shrink: not enough days to conclude an edge.
            edge*=len(vals)/(len(vals)+80.0)
            by_window[str(days)]={'trials':len(vals),'edge_nhay':round(edge,4)}
        edge=(.5*by_window.get('30',{}).get('edge_nhay',0)
              +.3*by_window.get('60',{}).get('edge_nhay',0)
              +.2*by_window.get('90',{}).get('edge_nhay',0))
        stats[k]={'trials':len(values),'edge_nhay':round(edge,4),'windows':by_window}
    return stats


def _validated_component(features, stats):
    """25% walk-forward component chooses feature mix with modest caps."""
    weights={}
    for k in ('pattern','trend','rhythm','stability'):
        s=stats.get(k,{})
        if s.get('trials',0)<25:
            weights[k]=1.0
        else:
            edge=float(s.get('edge_nhay',0.0))
            weights[k]=max(.70,min(1.30,1+1.5*edge))
    total=sum(weights.values())
    return {n:sum(features[k][n]*weights[k] for k in weights)/total
            for n in NUMBERS},weights


def _trusted_web(source_detail):
    """Historical source reliability is used, not claims of 'guaranteed' tips."""
    types={'forum':1.10,'community_rank':1.08,'data_model':1.04,
           'statistics':1.00,'editorial':.75}
    raw={n:0.0 for n in NUMBERS}
    agreement=Counter()
    used=[]
    weightsum=0.0
    for rec in source_detail or []:
        kind=rec.get('kind')
        if kind not in types: continue
        rel=rec.get('reliability') or {}
        sample=int(rel.get('sample_loto',0))
        effective=float(rec.get('effective_loto',.50))
        if sample>=20 and effective<.47: continue
        picks=[n for n in dict.fromkeys(rec.get('loto',[])) if n in raw][:12]
        if not picks: continue
        confidence=min(1.0,sample/30.0)
        strength=types[kind]*(.75+.50*(effective-.50))*(.65+.35*confidence)
        strength=max(.05,strength)
        for rank,n in enumerate(picks):
            raw[n]+=strength*max(.30,1-.07*rank)
            agreement[n]+=1
        weightsum+=strength
        used.append({'source':rec.get('source'),'effective_loto':effective,
                     'sample_loto':sample})
    if not weightsum: return {n:.5 for n in NUMBERS},{},[],0.0
    for n in NUMBERS:
        raw[n]=raw[n]/weightsum*(1+.06*min(4,max(0,agreement[n]-1)))
    # Max 20%, adapt to independent source count; low-sample shrink in feature.
    web_weight=min(.20,.045+.035*len(used))
    return _norm(raw),dict(agreement),used,web_weight


def _choose_pair(scores, agreement, previous_pair):
    """Compare scored pairs; never repeat exact pair from yesterday.

    Each individual number remains eligible. No penalty for a draw being
    positive yesterday (that would impose gambler's fallacy).
    """
    top=sorted(NUMBERS,key=lambda n:(-scores[n],n))[:24]
    prohibited=set(previous_pair or []) if len(previous_pair or [])==2 else set()
    ranked=[]
    for a,b in combinations(top,2):
        if {a,b}==prohibited: continue
        base=(scores[a]+scores[b])/2.0
        balance=1-abs(scores[a]-scores[b])
        confirm=min(1.0,(agreement.get(a,0)+agreement.get(b,0))/5.0)
        value=.93*base+.03*balance+.04*confirm
        ranked.append((value,a,b))
    if not ranked:
        pairs=[(a,b) for a,b in combinations(NUMBERS,2)
               if {a,b}!=prohibited]
        pairs.sort(key=lambda pair:-(scores[pair[0]]+scores[pair[1]]))
        return list(pairs[0]),{'candidate_pairs':len(pairs),'no_repeat_pair':True}
    ranked.sort(key=lambda t:(-t[0],t[1],t[2]))
    _,a,b=ranked[0]
    return [a,b],{
        'candidate_pairs':len(ranked),
        'pair_score':round(ranked[0][0],4),
        'no_repeat_pair':bool(prohibited),
        'previous_pair':sorted(prohibited),
        'web_sources_pair':agreement.get(a,0)+agreement.get(b,0),
    }


def build_loto_v4(rows, source_detail=None, max_web_weight=.20, previous_pair=None):
    """Return the same context interface expected by unchanged scoring.py."""
    counts=_prepare(list(rows or [])[:365])
    recent=counts[-90:]
    neutral={n:.5 for n in NUMBERS}
    if len(recent)<30:
        # Conservative cold-start; web still available if there is any.
        web,agreement,used,web_w=_trusted_web(source_detail)
        web_w=min(max_web_weight,web_w)
        result={n:((1-web_w)*.5+web_w*web[n]) for n in NUMBERS}
        result=_norm(result)
        pair,detail=_choose_pair(result,agreement,previous_pair)
        return {'scores':result,'history_scores':neutral,'song_thu':pair,
                'web_weight':web_w,'trusted_sources':used,
                'web_agreement':agreement,'pair_meta':detail,
                'meta':{'history_rows':len(recent),'wf_trials':0,
                        'formula':'cold_start','walkforward':{}}}

    features=_estimate_features(recent)
    stats=_walkforward(counts,tests=90)
    validated,weights=_validated_component(features,stats)
    web,agreement,used,web_w=_trusted_web(source_detail)
    web_w=max(0.0,min(.20,float(max_web_weight),web_w))

    # Recipe: 30% conditional patterns, 25% validated mix, 15% trend,
    # 20% max web, 10% rhythm/stability. Reallocate unused web share
    # proportionally to history rather than giving 0.5 to all numbers.
    core={n:(.30*features['pattern'][n]
             +.25*validated[n]
             +.15*features['trend'][n]
             +.05*features['rhythm'][n]
             +.05*features['stability'][n])/.80 for n in NUMBERS}
    raw={n:(1-web_w)*core[n]+web_w*web[n] for n in NUMBERS}
    scores=_norm(raw)
    pair,pair_meta=_choose_pair(scores,agreement,previous_pair)
    return {
        'scores':scores,'history_scores':core,'song_thu':pair,
        'web_weight':web_w,'trusted_sources':used,
        'web_agreement':agreement,'pair_meta':pair_meta,
        'meta':{
            'history_rows':len(recent),
            'long_history_rows':len(counts),
            'wf_trials':stats.get('hybrid',{}).get('trials',0),
            'formula':{'conditional_pattern':.30,'walkforward':.25,
                       'trend':.15,'web_cap':.20,'rhythm_stability':.10},
            'feature_walkforward':stats,
            'validated_feature_weights':weights,
            'note':'Điểm xếp hạng, không phải xác suất trúng',
        },
    }
