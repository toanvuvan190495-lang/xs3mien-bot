from __future__ import annotations

import json


class GPTReviewer:
    """
    Optional reviewer only.
    Không được thêm số ngoài candidate do scoring định lượng tạo ra.
    """
    def __init__(self, api_key, model):
        self.api_key = api_key
        self.model = model

    def review(self, region, stations, song_thu, db64, all_scores, reasons, community_detail):
        if not self.api_key:
            return {"song_thu": song_thu, "db64": db64, "note": "GPT disabled"}

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            top_loto = sorted(
                all_scores["loto"], key=all_scores["loto"].get, reverse=True
            )[:14]
            top_db = sorted(
                all_scores["db"], key=all_scores["db"].get, reverse=True
            )[:72]

            prompt = f"""
Bạn chỉ phản biện xếp hạng thống kê xổ số Miền Bắc.
Đây KHÔNG phải xác suất thắng và không được suy diễn quy luật chắc chắn.

Miền={region}; đài={stations}
Song thủ scoring={song_thu}
Top loto={[(n, all_scores['loto'][n]) for n in top_loto]}
Top DB={[(n, all_scores['db'][n]) for n in top_db]}
Reason={reasons}
Nguồn + reliability={community_detail}

Ràng buộc:
- Song thủ đúng 2 số, chỉ chọn trong top_loto.
- DB đúng 64 số, chỉ chọn trong top_db.
- Không thêm số ngoài candidate.
- Không dùng lập luận "gan lâu chắc về".
- Khi web xung đột history, ưu tiên dữ liệu đã có lịch sử reliability.
- Trả JSON thuần:
{{"song_thu":["00","00"],"db64":[...64...],"note":"<=180 ký tự"}}
"""
            resp = client.responses.create(model=self.model, input=prompt)
            data = json.loads(resp.output_text.strip())

            st = [str(x).zfill(2) for x in data.get("song_thu", [])]
            db = [str(x).zfill(2) for x in data.get("db64", [])]

            if not (
                len(st) == 2
                and len(set(st)) == 2
                and all(x in top_loto for x in st)
            ):
                st = song_thu

            if not (
                len(db) == 64
                and len(set(db)) == 64
                and all(x in top_db for x in db)
            ):
                db = db64

            return {
                "song_thu": st,
                "db64": db,
                "note": data.get("note", ""),
            }

        except Exception as e:
            return {
                "song_thu": song_thu,
                "db64": db64,
                "note": f"GPT fallback: {type(e).__name__}",
            }
