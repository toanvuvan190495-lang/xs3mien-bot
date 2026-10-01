from __future__ import annotations
from config import DRAW_SCHEDULE,REGION_NAMES,settings
from community_sources import CommunityCollector
from free_results import FreeResultSource
from history_features import build_history_scores
from scoring import station_score_bundle,community_scores,aggregate_region,explain
from selector import select_best_model
from gpt_layer import GPTReviewer

class PredictionEngine:
    def __init__(self,store):
        self.store=store
        self.community=CommunityCollector(settings.web_timeout)
        self.results=FreeResultSource(settings.web_timeout)
        self.gpt=GPTReviewer(settings.openai_api_key,settings.openai_model)

    def stations_today(self,region,d):
        return DRAW_SCHEDULE[region][d.weekday()]

    def _collect_community(self,region,d):
        records=self.community.collect(region,d.isoformat())
        for r in records:
            if r.get("ok"):
                self.store.save_source_signal(
                    d.isoformat(),region,r["source"],
                    r.get("loto",[]),r.get("db",[]),r.get("excerpt",""))
        return records

    def predict_region(self,region,d):
        stations=self.stations_today(region,d)
        bundles={}
        for station in stations:
            history=self.store.get_history(region,station,d.isoformat(),settings.history_days)
            hs=build_history_scores(history) if history else None
            bundles[station]=station_score_bundle({},hs,None,region=region)

        selected,model_stats=select_best_model(self.store,region,d,90)

        records=self._collect_community(region,d)
        cl,cd,detail,meta=community_scores(
            records,lambda source:self.store.source_reliability(source,region))

        st,db50,scores=aggregate_region(
            bundles,(cl,cd),.32,region,selected,meta)

        reasons=explain(st,bundles,scores)

        if settings.use_gpt:
            reviewed=self.gpt.review(region,stations,st,db50,scores,reasons,detail)
            st=reviewed["song_thu"]; db50=reviewed["db50"]

        return {
            "draw_date":d.isoformat(),"region":region,"region_name":REGION_NAMES[region],
            "stations":stations,"song_thu":st,"db50":db50,
            "scores":{
                "song_thu":{n:scores["loto"][n] for n in st},
                "db_top10":{n:scores["db"][n] for n in db50[:10]},
                "selected_model":selected,"model_stats":model_stats,
                "web_weight":scores["web_weight"],
            },
            "reasons":reasons,
            "community":{
                "sources":detail,"active_sources":meta["active_sources"],
                "loto_agreement":meta["loto_agreement"],
                "db_agreement":meta["db_agreement"],
            },
        }

    def fetch_results(self,region,d):
        return self.results.fetch(region,d,self.stations_today(region,d))

    def ingest_results(self,region,d,results=None):
        results=results or self.fetch_results(region,d)
        for st,e in results.items():
            self.store.upsert_draw(d.isoformat(),region,st,e.get("special"),e.get("all_prizes",[]))
        return results
