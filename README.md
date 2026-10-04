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
