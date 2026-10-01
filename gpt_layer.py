from __future__ import annotations
import json

class GPTReviewer:
    def __init__(self,api_key,model):
        self.api_key=api_key;self.model=model

    def review(self,region,stations,song_thu,db50,all_scores,reasons,community_detail):
        if not self.api_key:return {"song_thu":song_thu,"db50":db50,"note":"GPT disabled"}
        try:
            from openai import OpenAI
            client=OpenAI(api_key=self.api_key)
            top_loto=sorted(all_scores["loto"],key=all_scores["loto"].get,reverse=True)[:14]
            top_db=sorted(all_scores["db"],key=all_scores["db"].get,reverse=True)[:65]
            prompt=f"""
Bạn phản biện kết quả xếp hạng thống kê xổ số. Đây KHÔNG phải xác suất thắng.
Miền={region}; đài={stations}
Song thủ scoring={song_thu}
Top loto={[(n,all_scores['loto'][n]) for n in top_loto]}
Top DB={[(n,all_scores['db'][n]) for n in top_db]}
Đồng thuận đài={reasons}
Nguồn cộng đồng + độ tin cậy lịch sử={community_detail}

Ràng buộc:
- Không thêm số ngoài candidate.
- Song thủ đúng 2 số, ưu tiên số có đồng thuận nhiều đài và nhiều loại feature.
- DB đúng 50 số từ top_db.
- Không suy diễn "gan lâu chắc về".
- Nếu cộng đồng xung đột thống kê, ưu tiên dữ liệu thống kê có lịch sử.
- JSON thuần:
{{"song_thu":["00","00"],"db50":[...50...],"note":"<=180 ký tự"}}
"""
            resp=client.responses.create(model=self.model,input=prompt)
            data=json.loads(resp.output_text.strip())
            st=[str(x).zfill(2) for x in data.get("song_thu",[])]
            db=[str(x).zfill(2) for x in data.get("db50",[])]
            if not(len(st)==2 and len(set(st))==2 and all(x in top_loto for x in st)):st=song_thu
            if not(len(db)==50 and len(set(db))==50 and all(x in top_db for x in db)):db=db50
            return {"song_thu":st,"db50":db,"note":data.get("note","")}
        except Exception as e:
            return {"song_thu":song_thu,"db50":db50,"note":f"GPT fallback: {type(e).__name__}"}
