# XS Miền Bắc FINAL

Bot Telegram chỉ chạy **Miền Bắc**.

## Hoạt động
- 17:15: tự chốt Song thủ + ĐB64.
- 18:00–19:58: tự kiểm tra kết quả mỗi 2 phút.
- Có kết quả MB đầy đủ: báo kết quả ngay.
- 19:15: tổng kết ngày.
- Chủ nhật 20:00: tổng kết tuần.
- Nếu Railway restart trong khoảng 17:15–17:40 và chưa có dự đoán, bot tự chạy bù.

## Lệnh
- `/mb` chốt MB ngay.
- `/result` xem dự đoán hôm nay.
- `/today` tổng kết hôm nay.
- `/week` tổng kết tuần hiện tại.
- `/status` trạng thái.
- `/test` kiểm tra Telegram.

## Cách xếp hạng
- History MB: cửa sổ gần + trung hạn.
- Song thủ: selector walk-forward 30/60/90 ngày.
- Web/forum: reliability từng nguồn + confidence theo số mẫu.
- Consensus: ưu tiên nhiều nguồn độc lập đồng thuận.
- Web được giới hạn trọng số tối đa 28% để giảm nhiễu.
- ĐB64: lấy đúng **64 số có DB score cao nhất**.
- GPT chỉ là reviewer tùy chọn; mặc định OFF.

Không có mô hình nào bảo đảm trúng. `Score` là điểm xếp hạng nội bộ, không phải xác suất thắng.

## Quy ước tài chính
### Song thủ
- 270.000đ / số / ngày.
- 2 số = 540.000đ/ngày.
- Mỗi nháy trúng nhận 990.000đ.

### ĐB64
- Vốn 640.000đ/ngày.
- Nếu ĐB 2 số cuối nằm trong dàn 64: nhận 990.000đ.

### Tổng
- Nếu chơi cả hai: vốn 1.180.000đ/ngày.
- Bot báo lãi/lỗ ngày và tuần riêng cho STL, ĐB64 và tổng.

## Railway Variables
Bắt buộc:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TIMEZONE=Asia/Ho_Chi_Minh`

Khuyến nghị:
- `DB_PATH=data/lottery_v2.sqlite3`

Nếu Railway Volume của bạn mount vào `/app/data`, có thể đặt:
- `DB_PATH=/app/data/lottery_v2.sqlite3`

## Deploy
Start command:
```bash
python main.py
```

Build:
```bash
pip install -r requirements.txt
```

## Lịch sử
Nếu database mới/trống, có thể đồng bộ MB:
```bash
python history_sync_mb.py 180
```


## Result fallback V1
Kết quả MB được thử tuần tự:
1. Minh Ngọc
2. xsmn.mobi
3. xoso.com.vn

Chỉ nhận kết quả khi parser đọc đủ đúng 27 số giải MB.
Lệnh `/settle` dùng để ép kiểm tra và hiển thị lỗi từng nguồn khi cần.


## ĐB64 V3 - Cầu số 4 GĐB

Chữ số thứ 4 từ trái của GĐB 5 số chính là hàng chục của 2 số cuối.

Công thức ĐB64:
- 25% model ĐB lịch sử
- 50% cầu số 4 Chẵn/Lẻ + Tài/Xỉu
- 15% stability 30/60/90 kỳ
- 10% web/source reliability

Pattern KHÔNG hard-code.
Bot tự khai thác:
- chuỗi trạng thái gần đây;
- nhịp độ dài các đoạn liên tiếp: 1-2-1, 2-2, 3-3, 1-3-1-3, 1-1-1-1...;
- cầu bệt Chẵn/Lẻ/Tài/Xỉu chỉ khi có >=5 kỳ liên tiếp, rồi tính xác suất tiếp tục/gãy;
- nhiều độ dài context;
- support tối thiểu;
- recency weighting;
- walk-forward tự kiểm tra 90 kỳ gần nhất.

Nếu một pattern không có đủ mẫu hoặc walk-forward kém, xác suất bị co về 50/50,
nên dù component "cầu số 4" có trọng số 50%, tín hiệu yếu sẽ gần như trung tính.


### Quy ước bệt
Chỉ gọi là bệt khi cùng trạng thái xuất hiện liên tiếp từ 5 kỳ trở lên.
Ví dụ: X-X-X-X-X = bệt Xỉu 5 kỳ. Chuỗi 2-4 kỳ chỉ là run/nhịp ngắn.


## V3.2 - Chọn 2 yếu tố cầu số 4

Bot chọn:
1. Một trạng thái mạnh hơn trong Chẵn/Lẻ.
2. Một trạng thái mạnh hơn trong Xỉu/Tài.

Hai trạng thái này được suy ra từ pattern lịch sử động, không hard-code.

Giao của 2 trạng thái tạo nhóm đầu số ưu tiên:
- Chẵn + Xỉu -> 0,2,4
- Lẻ + Xỉu -> 1,3
- Chẵn + Tài -> 6,8
- Lẻ + Tài -> 5,7,9

Nhóm đầu số ưu tiên được cộng điểm trong component 50% cầu số 4.
Nếu confidence của cầu thấp, điểm bị co về trung tính để tránh ép sai.


## V3.3 - Tổng kết tháng

- `/month`: xem tổng kết tháng hiện tại.
- 20:15 ngày cuối cùng của mỗi tháng: bot tự gửi tổng kết tháng.
- Nếu ngày cuối tháng rơi vào Chủ nhật:
  - 20:00 gửi tổng kết tuần.
  - 20:15 gửi tổng kết tháng.

Tổng kết tháng gồm:
- tổng nháy song thủ;
- số ngày ĐB64 trúng;
- vốn STL;
- vốn ĐB64;
- tổng tiền nhận;
- lãi/lỗ STL;
- lãi/lỗ ĐB64;
- lãi/lỗ tổng.


## V3.4 - Sửa trường hợp 50/50

Nguyên nhân thường gặp: Railway Volume mới chưa có đủ lịch sử MB.

- `/history`: kiểm tra số kỳ đang có.
- `/sync_history`: đồng bộ khoảng 240 ngày.
- Nếu startup thấy <120 kỳ, bot tự backfill ở background.
- Khi chưa đủ dữ liệu, bot KHÔNG chọn mặc định Chẵn + Xỉu.
- Cầu số 4 chỉ được dùng khi có dữ liệu/pattern thực tế.


## V3.5 - Bảo đảm đầy đủ đầu số ưu tiên

Sửa hai vấn đề:

1. "Bệt" chỉ được gọi khi có >=5 kỳ liên tiếp cùng trạng thái.
   Chuỗi 2-4 kỳ chỉ là run/nhịp.

2. Khi cầu số 4 chọn tổ hợp:
   - Chẵn + Xỉu -> đầu 0,2,4 -> bảo đảm đủ 00-09,20-29,40-49.
   - Lẻ + Xỉu -> đầu 1,3 -> bảo đảm đủ 10-19,30-39.
   - Chẵn + Tài -> đầu 6,8 -> bảo đảm đủ 60-69,80-89.
   - Lẻ + Tài -> đầu 5,7,9 -> bảo đảm đủ 50-59,70-79,90-99.

Các số đầu ưu tiên được giữ trước trong DB64.
Các slot còn lại được điền theo tổng score:
25% history + 50% digit4 + 15% stability + 10% web.


## V3.6 - Result Guard

Fix lỗi parser có thể lấy MB ngày hôm qua hoặc trộn bảng miền khác:

- Chỉ chấp nhận trang có marker Miền Bắc/XSMB đúng ngày yêu cầu.
- Phải đúng cấu trúc 27 giải MB và đúng số chữ số từng giải.
- `all_prizes[0]` phải chính là giải ĐB.
- Với kết quả cùng ngày đang live: cần ít nhất 2 nguồn độc lập trả về đúng cùng bộ 27 giải.
- Scheduler vẫn re-check tới 19:58 kể cả đã settle.
- Nếu settlement cũ sai, settlement + history + mb_performance của ngày đó được ghi đè bằng kết quả đã xác minh.
- `/resettle` là alias của `/settle` để ép xác minh lại hôm nay.

Mục tiêu: chậm vài phút còn hơn settle nhầm ngày/trộn miền.


## V3.7 - Multi-source result parser

Mở rộng nguồn xác minh kết quả MB:
- Minh Ngọc
- xoso.com.vn trang ngày cụ thể
- xoso.com.vn trang 1 ngày
- ketqua.vn
- sxmb.com
- xsmn.mobi

Parser mới hỗ trợ:
- hàng bảng kiểu `ĐB / 1 / 2 / ... / 7`;
- hàng `G1 / G2 / ...`;
- nhãn `Giải Nhất / Giải Nhì / ...`;
- kiểm tra đúng cấu trúc 27 giải;
- kiểm tra đúng ngày MB;
- với ngày hiện tại: vẫn bắt buộc ít nhất 2 nguồn trùng khớp 100%.

Không hạ chuẩn xác minh về 1 nguồn.


## V3.8 - History Maintenance

Fix lịch sử bị đứng sau khi đã có 120/240 kỳ:

- Khi settlement thành công: vẫn lưu kết quả ngày hiện tại ngay vào `draw_history`.
- Startup: luôn kiểm tra 10 ngày gần nhất và tự vá ngày nào thiếu.
- 00:10 mỗi ngày: tự chạy job vá 10 ngày gần nhất.
- Full backfill 240 ngày chỉ dùng khi tổng history còn ít.
- `/history`: hiển thị coverage 10 ngày gần nhất bằng ✅/❌.
- `/repair_history`: ép vá 10 ngày gần nhất.
- `/sync_history`: vẫn dùng để quét khoảng 240 ngày.

Nhờ đó tổng số history có thể >240 và tiếp tục tăng theo từng ngày,
thay vì dừng ở đúng số kỳ của lần bootstrap ban đầu.


## V3.9 - 365-day history + Song thủ Cầu 90

Chỉ thay đổi 3 phần so với V3.8:

### 1. Full history sync = 365 ngày
- `/sync_history` quét/bổ sung 365 ngày gần nhất.
- Startup nếu history còn dưới khoảng 330 kỳ sẽ backfill 365 ngày.
- Không xóa dữ liệu cũ.
- `draw_history` không bị giới hạn 365 dòng; mỗi ngày tiếp tục tăng thêm.

### 2. Kết quả mới tự lưu vào data
Sau khi kết quả MB đúng ngày được Result Guard xác minh:
`_settle_prediction -> engine.ingest_results -> store.upsert_draw`
sẽ ghi ngay kỳ mới vào SQLite/Volume.
Job 00:10 vẫn giữ nguyên để vá 10 ngày gần nhất nếu có ngày bị bỏ lỡ.

### 3. Song thủ MB = Cầu 90 toàn miền
Không còn chia lịch sử theo station/thứ.

Dùng đúng 90 kỳ/ngày MB gần nhất trong SQLite/Volume:
- 38% xu hướng lô đa cửa sổ 7/14/30/60/90, ưu tiên gần đây;
- 32% pattern/cầu nhịp động 2..6 kỳ, tự học pattern đã từng xuất hiện;
- 15% gap-hazard thực nghiệm, không dùng tư duy "gan lâu chắc về";
- 15% stability 14/30/60/90.

Sau history core mới kết hợp forum/web:
- chỉ forum/community/data/statistics;
- nguồn được cân theo reliability do bot tự chấm qua kết quả thật;
- nguồn có đủ mẫu nhưng performance thấp bị loại khỏi lớp Song thủ;
- nhiều nguồn độc lập cùng chốt được cộng consensus;
- web/forum tối đa 25%, history vẫn là nền chính.

Cặp song thủ cuối còn được đánh giá lại theo hiệu quả của chính cặp
trên 30/60/90 ngày, ưu tiên 30 ngày gần nhất.

ĐB64, cầu số 4, Result Guard, lịch tự động, daily/weekly/monthly summary,
các lệnh và cách tính tiền giữ nguyên V3.8.


## V3.10 - Partial Digit4 Signals

Chỉ thay phần ĐB64/cầu số 4 so với V3.9.

### Trạng thái dữ liệu
- >=20 kỳ: coi là ĐỦ DỮ LIỆU để phân tích.
- Tín hiệu mạnh/yếu được đánh giá riêng.
- Có 242/365 kỳ nhưng pattern xung đột sẽ báo:
  `ĐỦ DỮ LIỆU - tín hiệu yếu/xung đột`, không báo thiếu dữ liệu.

### Hai nhánh hoạt động độc lập
Ví dụ:
- Chẵn/Lẻ yếu/xung đột;
- Tài/Xỉu mạnh, nghiêng Tài.

Bot vẫn dùng Tài bình thường.
Nhánh Chẵn/Lẻ chỉ giảm trọng số, không làm vô hiệu cả 40% cầu số 4.

Phân bổ nội bộ:
- cả hai mạnh: chia động theo chất lượng/confidence;
- một mạnh, một yếu: mạnh 80%, yếu 20%;
- cả hai yếu: 50/50 nhưng mỗi nhánh bị shrink mạnh về neutral.

Hard priority:
- cả 2 mạnh -> giao hai điều kiện;
- chỉ Chẵn/Lẻ mạnh -> khóa 5 đầu theo Chẵn hoặc Lẻ;
- chỉ Tài/Xỉu mạnh -> khóa 5 đầu theo Tài hoặc Xỉu;
- cả 2 yếu -> không khóa cứng đầu.

### Công thức ĐB64 mới
- 20% lịch sử ĐB
- 40% cầu số 4
- 20% stability 30/60/90
- 20% web/source reliability

Song thủ Cầu 90, history 365, Result Guard, lịch tự động,
tổng kết ngày/tuần/tháng và cách tính tiền giữ nguyên V3.9.


## V4 - Chỉ nâng cấp Song thủ Miền Bắc

- `engine.py`: riêng block Song thủ sử dụng `loto_v4.build_loto_v4`.
- `loto_v4.py`: 90 kỳ gần nhất làm feature window, tối đa 365 kỳ
  để kiểm tra 30/60/90 kỳ theo walk-forward không nhìn trước.
- Công thức mục tiêu: 30% conditional patterns + 25% WF-validated mix
  + 15% trend + tối đa 20% nguồn web + 10% rhythm/stability.
- Nếu có ít nguồn web, trọng số còn lại tự quay về điểm lịch sử.
- Kết quả walk-forward chấm theo TỔNG NHÁY, không phải chỉ hit/miss.
- Không chọn lại đúng cặp hôm trước (thứ tự đảo không thành cặp mới),
  nhưng từng số vẫn có thể được dùng lại khi phù hợp.
- Nếu GPT reviewer bật, output Song thủ vẫn không được trùng nguyên
  cặp ngày hôm trước.
- `scores.selected_model` là `stl_v4_wf90`.
- Không đổi công thức ĐB64, data, lịch sử, parser, Result Guard,
  lệnh Telegram, giờ chốt, đối soát, tổng kết và cách tính vốn.
- Không ngụ ý cầu tạo ra xác suất trúng cao hơn ngẫu nhiên.

LƯU Ý: Các file `main.py`, `storage.py`, `scoring.py`, `loto_cau90.py`,
`messages.py` chưa nằm trong đợt tải lên riêng lẻ của người dùng; bản
đóng gói này bổ sung chúng từ gói V3.10 đã có trước đó. Nếu bản trên
GitHub có sửa đổi riêng ở các file ấy, cần so sánh trước khi ghi đè.


## V4.1 – STL Multi-Cầu (2026-10-08)

CHỈ đổi Song thủ: `engine.py`, `loto_v4.py`, thêm `loto_multi_cau.py`.
Không đổi `scoring.py`, `db_digit4.py`, `messages.py`, `main.py`,
`settlement.py`, `storage.py`, `mb_performance.py`, hay lịch tự động.

- 15% cầu động 2–4 trạng thái xuất hiện / không xuất hiện.
- 10% cấu trúc 27 giải ngày trước: cầu rơi 27 giải, ghép GĐB–G1,
  G2–G3, G4–G5, và ghép GĐB/G1 hai ngày.
- 5% đồng thuận **giữa các họ cầu có kiểm định**, không đếm web lần nữa.
- 25% trộn tính năng dựa vào kiểm định walk-forward 30/60/90 lượt.
- 15% xu hướng, 10% nhịp và ổn định, tối đa 20% web.
- Cầu cấu trúc bị vô hiệu nếu chưa có đủ 30 kỳ thử hay không vượt mức
  tham chiếu ngẫu nhiên; các nhánh yếu giữ trung tính.
- Tính chất chỉ là tín hiệu thống kê, không có bằng chứng đảm bảo lợi thế.
- Cấm lặp **nguyên cặp** hôm trước, nhưng có thể chọn lại từng số.
- `/mb` báo `Model STL: stl_v41_multi_cau`.
- Trong trường hợp chưa đủ lịch sử, bot không tạo cầu giả.

**Quan trọng:** Walk-forward không sử dụng dữ liệu web hiện tại để giả
làm tín hiệu web của các ngày quá khứ. Hệ thống giữ bảng nguồn web
hiện tại và đánh giá reliability theo code cũ.

## V4.2 — Dàn ĐB ghép chữ số 4 × chữ số 5 (bổ sung, không thay ĐB64)

- V4.1 Multi-Cầu Song thủ và **ĐB64 công thức 20/40/20/20** giữ nguyên.
- Chữ số thứ 4 từ trái của GĐB 5 chữ số = hàng chục của 2 số cuối;
  chữ số thứ 5 = hàng đơn vị của 2 số cuối.
- ĐB số 5 dùng cùng engine `analyze_property` từ `db_digit4.py`:
  C/L, T/X, raw/run/bệt, min support, reliability walk-forward, ngưỡng strong.
- Chữ số 4 không được tính lại: dùng kết quả `analyze_digit4` đã có; `db_digit4.py` và `scoring.py` **không sửa**.
- Tạo dàn bằng tích Descartes (hàng chục từ số 4 × đơn vị từ số 5),
  loại số trùng, mỗi số là 2 chữ số bao gồm cả số 0 đầu.
- Nếu 2 yếu tố một chữ số cùng mạnh: giao của C/L và T/X.
  Nếu một mạnh: 5 chữ số thuộc yếu tố mạnh. Nếu cả hai yếu:
  chọn giao dự kiến từ các pick tạm, có cảnh báo yếu (không tự nhận mạnh).
  Nếu lịch sử ít hơn 20 kỳ: không tạo dàn, vốn bằng 0.
- Ví dụ chữ số 4 là Chẵn+Tài -> 6,8; chữ số 5 là Lẻ+Xỉu -> 1,3;
  dàn mới -> 61,63,81,83. Vốn 4×10.000=40.000đ/ngày.
- Mỗi số trong dàn 10.000đ; nếu 2 số cuối GĐB thuộc dàn,
  nhận 990.000đ **một lần**, không nhân 990.000đ với số lượng số đánh.
- Nếu không trúng, nhận 0đ. Lãi/lỗ riêng = nhận - vốn.
- Vốn/ngày cả ba sản phẩm = 540.000 (STL) + 640.000 (ĐB64)
  + 10.000×số lượng số dàn ghép của kỳ đó.
- Dàn được lưu trong `predictions.scores_json.db45_combo` và
  thông tin phân tích số 5 trong `scores_json.db_digit5`.
  Không thay bảng, khóa, kiểu dữ liệu hoặc cấu trúc SQLite đang chạy.
- Ngày quá khứ trước V4.2 không tự truy thu vốn, không tự đánh dấu trượt,
  kể cả khi chạy lại `/settle`.
- `/mb` và `/result`: hiển thị dàn ghép cùng STL, ĐB64.
- `/db45`: xem riêng dàn dự đoán ngày hiện tại.
- `/db45_today`: kết quả/tổng kết riêng dàn ghép ngày hiện tại.
- `/db45_week`, `/db45_month`: thống kê riêng tuần/tháng.
- `/today`, `/week`, `/month`, và tin tự động: thêm mục ĐB ghép.
- Lịch tự động 00:10, 17:15, kiểm tra KQ, 19:15, CN 20:00,
  cuối tháng 20:15 giữ nguyên.

**Lưu ý:** Bộ máy dự báo không chứng minh được ưu thế so với lựa chọn ngẫu nhiên.
Kết quả mẫu/sức mạnh tín hiệu không phải xác suất thắng đã kiểm định độc lập.
