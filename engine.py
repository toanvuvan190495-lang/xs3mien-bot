from __future__ import annotations

from config import DRAW_SCHEDULE, REGION_NAMES, settings
from community_sources import CommunityCollector
from free_results import FreeResultSource
from history_features import build_history_scores
from scoring import station_score_bundle, community_scores, aggregate_region, explain
from selector import select_best_model
from loto_v4 import build_loto_v4
from gpt_layer import GPTReviewer
from db_digit4 import db_history_and_stability, analyze_digit4
from db45_combo import analyze_digit5, build_db45_combo


class PredictionEngine:
    def __init__(self, store):
        self.store = store
        self.community = CommunityCollector(settings.web_timeout)
        self.results = FreeResultSource(settings.web_timeout)
        self.gpt = GPTReviewer(settings.openai_api_key, settings.openai_model)

    def stations_today(self, region, d):
        if region != "MB":
            raise ValueError("Bản này chỉ chạy Miền Bắc")
        return DRAW_SCHEDULE[region][d.weekday()]

    def _collect_community(self, region, d):
        if not settings.use_web_sources:
            return []

        records = self.community.collect(region, d.isoformat())
        for r in records:
            if r.get("ok"):
                self.store.save_source_signal(
                    d.isoformat(),
                    region,
                    r["source"],
                    r.get("loto", []),
                    r.get("db", []),
                    r.get("excerpt", ""),
                )
        return records

    def predict_region(self, region, d):
        if region != "MB":
            raise ValueError("Bản này chỉ chạy Miền Bắc")

        stations = self.stations_today(region, d)

        # --------------------------------------------------------
        # 1) Thu thập forum/web trước để STL và ĐB cùng dùng,
        #    nhưng mỗi engine có weighting riêng.
        # --------------------------------------------------------
        records = self._collect_community(region, d)
        cl, cd, detail, meta = community_scores(
            records,
            lambda source: self.store.source_reliability(source, region),
        )

        # --------------------------------------------------------
        # 2) SONG THỦ MB V4.1: Multi-Cầu, walk-forward next-draw.
        #    Dùng 90 kỳ gần nhất làm feature window; lịch sử dài hơn
        #    (tối đa 365 kỳ) để kiểm chứng walk-forward không rò tương lai.
        #    Chỉ áp dụng chống lặp NGUYÊN CẶP hôm qua, không cấm từng số.
        # --------------------------------------------------------
        stl_history = self.store.get_region_history(
            region,
            d.isoformat(),
            min(365, settings.history_days),
        )
        from datetime import timedelta
        previous_date = (d - timedelta(days=1)).isoformat()
        previous = self.store.get_prediction(previous_date, region)
        previous_pair = previous.get("song_thu", []) if previous else []

        loto_context = build_loto_v4(
            stl_history,
            detail,
            max_web_weight=min(0.20, settings.community_max_weight),
            previous_pair=previous_pair,
        )

        selected = "stl_v41_multi_cau"
        model_stats = {
            "stl_v41_multi_cau": {
                "meta": loto_context.get("meta", {}),
                "pair_meta": loto_context.get("pair_meta", {}),
                "trusted_sources": loto_context.get(
                    "trusted_sources", []
                ),
                "web_weight": loto_context.get("web_weight", 0.0),
            }
        }

        # Bundle chỉ để explain/GPT reviewer tương thích.
        zero_db = {f"{i:02d}": 0.0 for i in range(100)}
        bundles = {
            "MB90": (
                loto_context.get("history_scores", {}),
                zero_db,
            )
        }

        # --------------------------------------------------------
        # 3) ĐB64 GIỮ NGUYÊN V3.8:
        #    lịch sử toàn MB tới settings.history_days (=365),
        #    cầu số 4 + stability + web.
        # --------------------------------------------------------
        region_history = self.store.get_region_history(
            region,
            d.isoformat(),
            settings.history_days,
        )
        db_history, db_stability = db_history_and_stability(
            region_history
        )
        digit4 = analyze_digit4(region_history)
        # Dàn ghép ĐB mới hoạt động độc lập; không thay đổi ĐB64.
        digit5 = analyze_digit5(region_history)
        db45_combo = build_db45_combo(digit4, digit5)

        song_thu, db64, scores = aggregate_region(
            bundles,
            (cl, cd),
            settings.community_max_weight,
            region,
            selected,
            meta,
            db_context={
                "history": db_history,
                "stability": db_stability,
                "digit4": digit4,
            },
            loto_context=loto_context,
        )

        reasons = explain(song_thu, bundles, scores)

        if settings.use_gpt:
            reviewed = self.gpt.review(
                region,
                stations,
                song_thu,
                db64,
                scores,
                reasons,
                detail,
            )
            reviewed_pair = list(reviewed["song_thu"])
            if (
                len(reviewed_pair) == 2
                and len(set(reviewed_pair)) == 2
                and (not previous_pair or set(reviewed_pair) != set(previous_pair))
            ):
                song_thu = reviewed_pair
            db64 = reviewed["db64"]

        return {
            "draw_date": d.isoformat(),
            "region": region,
            "region_name": REGION_NAMES[region],
            "stations": stations,
            "song_thu": song_thu,

            # Giữ key db50 để tương thích DB/storage cũ; thực tế chứa 64 số.
            "db50": db64,

            "scores": {
                "song_thu": {
                    n: scores["loto"][n]
                    for n in song_thu
                },
                "db_top10": {
                    n: scores["db"][n]
                    for n in db64[:10]
                },
                "selected_model": selected,
                "model_stats": model_stats,
                "web_weight": scores["web_weight"],
                "source_quality": scores.get(
                    "source_quality", 0.5
                ),
                "db_formula": scores.get("db_formula", {}),
                "db_digit4": scores.get("db_digit4", {}),
                "db_digit5": digit5,
                "db45_combo": db45_combo,
                "db_priority": scores.get("db_priority", {}),
                "loto_cau90": {
                    "history_rows": (
                        loto_context.get("meta") or {}
                    ).get("history_rows", 0),
                    "formula": (
                        loto_context.get("meta") or {}
                    ).get("formula", {}),
                    "trusted_sources": [
                        x.get("source")
                        for x in loto_context.get(
                            "trusted_sources", []
                        )
                    ],
                    "pair_meta": loto_context.get(
                        "pair_meta", {}
                    ),
                },
            },
            "reasons": reasons,
            "community": {
                "sources": detail,
                "active_sources": meta["active_sources"],
                "loto_agreement": meta["loto_agreement"],
                "db_agreement": meta["db_agreement"],
            },
        }

    def fetch_results(self, region, d):
        return self.results.fetch(region, d, self.stations_today(region, d))

    def ingest_results(self, region, d, results=None):
        results = results or self.fetch_results(region, d)
        for st, entry in results.items():
            self.store.upsert_draw(
                d.isoformat(),
                region,
                st,
                entry.get("special"),
                entry.get("all_prizes", []),
            )
        return results
