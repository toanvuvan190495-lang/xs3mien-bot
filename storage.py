from __future__ import annotations
import json, sqlite3
from pathlib import Path
from datetime import datetime

class Storage:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        with self.connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draw_date TEXT NOT NULL,
                region TEXT NOT NULL,
                stations_json TEXT NOT NULL,
                song_thu_json TEXT NOT NULL,
                db50_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                community_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                settled INTEGER NOT NULL DEFAULT 0,
                UNIQUE(draw_date, region)
            );

            CREATE TABLE IF NOT EXISTS settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draw_date TEXT NOT NULL,
                region TEXT NOT NULL,
                result_json TEXT NOT NULL,
                loto_hits_json TEXT NOT NULL,
                db_hits_json TEXT NOT NULL,
                settled_at TEXT NOT NULL,
                UNIQUE(draw_date, region)
            );

            CREATE TABLE IF NOT EXISTS source_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draw_date TEXT NOT NULL,
                region TEXT NOT NULL,
                source TEXT NOT NULL,
                loto_json TEXT NOT NULL,
                db_json TEXT NOT NULL,
                raw_excerpt TEXT,
                fetched_at TEXT NOT NULL,
                UNIQUE(draw_date, region, source)
            );

            CREATE TABLE IF NOT EXISTS source_performance (
                source TEXT NOT NULL,
                region TEXT NOT NULL,
                trials_loto INTEGER NOT NULL DEFAULT 0,
                hits_loto INTEGER NOT NULL DEFAULT 0,
                trials_db INTEGER NOT NULL DEFAULT 0,
                hits_db INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(source, region)
            );

            CREATE TABLE IF NOT EXISTS draw_history (
                draw_date TEXT NOT NULL,
                region TEXT NOT NULL,
                station TEXT NOT NULL,
                special TEXT,
                prizes_json TEXT NOT NULL,
                PRIMARY KEY(draw_date, region, station)
            );
            """)

    def save_prediction(self, p: dict):
        with self.connect() as con:
            con.execute("""
            INSERT INTO predictions(
                draw_date, region, stations_json, song_thu_json, db50_json,
                scores_json, reasons_json, community_json, created_at, settled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(draw_date, region) DO UPDATE SET
                stations_json=excluded.stations_json,
                song_thu_json=excluded.song_thu_json,
                db50_json=excluded.db50_json,
                scores_json=excluded.scores_json,
                reasons_json=excluded.reasons_json,
                community_json=excluded.community_json,
                created_at=excluded.created_at
            """, (
                p["draw_date"], p["region"], json.dumps(p["stations"], ensure_ascii=False),
                json.dumps(p["song_thu"]), json.dumps(p["db50"]),
                json.dumps(p["scores"], ensure_ascii=False),
                json.dumps(p["reasons"], ensure_ascii=False),
                json.dumps(p.get("community", {}), ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ))

    def _decode_pred(self, row):
        if not row: return None
        d = dict(row)
        for key in ("stations_json","song_thu_json","db50_json","scores_json","reasons_json","community_json"):
            d[key[:-5]] = json.loads(d[key])
        return d

    def get_prediction(self, draw_date: str, region: str):
        with self.connect() as con:
            row = con.execute("SELECT * FROM predictions WHERE draw_date=? AND region=?",
                              (draw_date, region)).fetchone()
        return self._decode_pred(row)

    def unsettled_today(self, draw_date: str):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM predictions WHERE draw_date=? AND settled=0",
                               (draw_date,)).fetchall()
        return [self._decode_pred(r) for r in rows]

    def save_settlement(self, draw_date, region, result, loto_hits, db_hits):
        with self.connect() as con:
            con.execute("""
            INSERT INTO settlements(draw_date, region, result_json, loto_hits_json, db_hits_json, settled_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(draw_date, region) DO UPDATE SET
                result_json=excluded.result_json,
                loto_hits_json=excluded.loto_hits_json,
                db_hits_json=excluded.db_hits_json,
                settled_at=excluded.settled_at
            """, (draw_date, region, json.dumps(result, ensure_ascii=False),
                  json.dumps(loto_hits, ensure_ascii=False), json.dumps(db_hits, ensure_ascii=False),
                  datetime.now().isoformat(timespec="seconds")))
            con.execute("UPDATE predictions SET settled=1 WHERE draw_date=? AND region=?",
                        (draw_date, region))

    def daily_summary(self, draw_date):
        with self.connect() as con:
            return [dict(r) for r in con.execute("""
            SELECT p.region,p.song_thu_json,p.db50_json,s.loto_hits_json,s.db_hits_json
            FROM predictions p LEFT JOIN settlements s
            ON p.draw_date=s.draw_date AND p.region=s.region
            WHERE p.draw_date=?
            ORDER BY CASE p.region WHEN 'MN' THEN 1 WHEN 'MT' THEN 2 ELSE 3 END
            """, (draw_date,)).fetchall()]

    # -------- community source tracking --------
    def save_source_signal(self, draw_date, region, source, loto, db, excerpt=""):
        with self.connect() as con:
            con.execute("""
            INSERT INTO source_signals(draw_date,region,source,loto_json,db_json,raw_excerpt,fetched_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(draw_date,region,source) DO UPDATE SET
                loto_json=excluded.loto_json, db_json=excluded.db_json,
                raw_excerpt=excluded.raw_excerpt, fetched_at=excluded.fetched_at
            """, (draw_date, region, source, json.dumps(loto), json.dumps(db),
                  excerpt[:1500], datetime.now().isoformat(timespec="seconds")))

    def source_reliability(self, source, region):
        with self.connect() as con:
            r = con.execute("""SELECT * FROM source_performance
                               WHERE source=? AND region=?""",(source,region)).fetchone()
        if not r:
            return {"loto": 0.50, "db": 0.50, "sample_loto": 0, "sample_db": 0}
        r = dict(r)
        # Bayesian smoothing Beta(2,2), tránh nguồn ít mẫu bị đẩy quá cao/thấp.
        return {
            "loto": (r["hits_loto"] + 2) / (r["trials_loto"] + 4),
            "db": (r["hits_db"] + 2) / (r["trials_db"] + 4),
            "sample_loto": r["trials_loto"],
            "sample_db": r["trials_db"],
        }

    def signals_for(self, draw_date, region):
        with self.connect() as con:
            rows = con.execute("""SELECT * FROM source_signals
                                  WHERE draw_date=? AND region=?""",(draw_date,region)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["loto"]=json.loads(d["loto_json"]); d["db"]=json.loads(d["db_json"]); out.append(d)
        return out

    def update_source_performance(self, draw_date, region, results):
        """Chấm tín hiệu nguồn sau khi có kết quả thực tế của cả miền."""
        signals = self.signals_for(draw_date, region)
        if not signals: return
        actual_loto = []
        actual_db = []
        for entry in results.values():
            actual_loto.extend([str(x)[-2:].zfill(2) for x in entry.get("all_prizes",[])])
            sp = entry.get("special")
            if sp is not None: actual_db.append(str(sp)[-2:].zfill(2))

        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as con:
            for s in signals:
                loto = list(dict.fromkeys(s["loto"]))[:20]  # cap tránh spam 100 số
                db = list(dict.fromkeys(s["db"]))[:64]
                if not loto and not db: continue
                loto_hit = int(any(n in actual_loto for n in loto)) if loto else 0
                db_hit = int(any(n in actual_db for n in db)) if db else 0
                con.execute("""
                INSERT INTO source_performance(source,region,trials_loto,hits_loto,trials_db,hits_db,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(source,region) DO UPDATE SET
                    trials_loto=trials_loto+excluded.trials_loto,
                    hits_loto=hits_loto+excluded.hits_loto,
                    trials_db=trials_db+excluded.trials_db,
                    hits_db=hits_db+excluded.hits_db,
                    updated_at=excluded.updated_at
                """, (s["source"], region, 1 if loto else 0, loto_hit,
                      1 if db else 0, db_hit, now))

    # -------- history cache --------
    def upsert_draw(self, draw_date, region, station, special, prizes):
        with self.connect() as con:
            con.execute("""
            INSERT INTO draw_history(draw_date,region,station,special,prizes_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(draw_date,region,station) DO UPDATE SET
                special=excluded.special, prizes_json=excluded.prizes_json
            """,(draw_date,region,station,special,json.dumps(prizes)))


    def get_region_history(self, region, before_date, limit=365):
        """
        Lấy lịch sử toàn miền, không khóa theo station.
        MB cần chuỗi ĐB liên tục từng ngày để soi chữ số thứ 4.
        """
        with self.connect() as con:
            rows = con.execute("""
            SELECT * FROM draw_history
            WHERE region=? AND draw_date<?
            ORDER BY draw_date DESC LIMIT ?
            """, (region, before_date, limit)).fetchall()

        out = []
        for r in rows:
            d = dict(r)
            d["prizes"] = json.loads(d["prizes_json"])
            out.append(d)
        return out

    def get_history(self, region, station, before_date, limit=365):
        with self.connect() as con:
            rows = con.execute("""
            SELECT * FROM draw_history
            WHERE region=? AND station=? AND draw_date<?
            ORDER BY draw_date DESC LIMIT ?
            """,(region,station,before_date,limit)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["prizes"]=json.loads(d["prizes_json"]); out.append(d)
        return out
