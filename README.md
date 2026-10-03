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
