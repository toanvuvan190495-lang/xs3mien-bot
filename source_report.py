import argparse
from storage import Storage
from config import settings
ap=argparse.ArgumentParser();ap.add_argument("--region",choices=["MN","MT","MB"],required=True)
args=ap.parse_args();s=Storage(settings.db_path)
with s.connect() as con:
    rows=con.execute("""SELECT source,region,trials_loto,hits_loto,trials_db,hits_db
                        FROM source_performance WHERE region=? ORDER BY trials_loto DESC""",(args.region,)).fetchall()
for r in rows:
    rel=s.source_reliability(r["source"],args.region)
    print(r["source"],"loto_rel=",round(rel["loto"],3),"db_rel=",round(rel["db"],3),
          "samples=",rel["sample_loto"],rel["sample_db"])
