# XS 3 miền V2

V2 giữ nguyên mục tiêu: **mỗi miền chỉ chốt 1 song thủ + 1 dàn ĐB50 áp dụng cho tất cả đài mở thưởng của miền đó**.

## V2 thêm gì?

1. **History cache 365 ngày** trong SQLite.
2. Feature lịch sử tự tính, độc lập với endpoint dự đoán.
3. **Nhiều nguồn web công khai** và API prediction.
4. Mỗi nguồn được lưu dự đoán và **tự chấm uy tín sau khi có kết quả**.
5. Bayesian smoothing để nguồn mới/ít mẫu không bị đánh giá cực đoan.
6. Community chỉ chiếm tối đa `COMMUNITY_MAX_WEIGHT` (mặc định 18%).
7. GPT là lớp phản biện cuối, bị khóa trong candidate do thuật toán tạo.
8. **Backtest theo thời gian**, ngày D chỉ được nhìn dữ liệu < D.
9. Tool `source_report.py` xem nguồn nào đang hoạt động tốt hơn.

## Lịch tự động

- 15:15 Miền Nam
- 16:15 Miền Trung
- 17:15 Miền Bắc
- kiểm tra kết quả mỗi 5 phút
- 19:00 tổng kết 3 miền

## Cài

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Điền token/key vào `.env`, không ghi trực tiếp vào source.

## Nạp lịch sử

Ví dụ 1 năm:

```bash
python history_sync.py --from-date 2025-10-01 --to-date 2026-09-29
```

Nếu API giới hạn request/ngày, chia thành nhiều khoảng ngày.

## Backtest

```bash
python backtest.py --from-date 2026-01-01 --to-date 2026-09-29 --region MN
python backtest.py --from-date 2026-01-01 --to-date 2026-09-29 --region MT
python backtest.py --from-date 2026-01-01 --to-date 2026-09-29 --region MB
```

Backtest mặc định chỉ dùng lịch sử local để tránh data leakage.

## Xem uy tín nguồn

```bash
python source_report.py --region MN
```

## Chạy bot

```bash
python main.py
```

## File chính

- `community_sources.py`: scraper nhiều nguồn.
- `history_features.py`: feature lịch sử.
- `scoring.py`: chấm từng đài + đồng thuận toàn miền + community.
- `storage.py`: dự đoán, kết quả, lịch sử, độ tin cậy nguồn.
- `backtest.py`: backtest không nhìn tương lai.
- `source_report.py`: báo cáo nguồn.
- `gpt_layer.py`: lớp phản biện GPT.
- `main.py`: scheduler Telegram.

## Lưu ý

Không có thuật toán nào bảo đảm kết quả xổ số. Điểm 0–100 của bot là **điểm xếp hạng tín hiệu**, không phải xác suất trúng. Dùng backtest và thống kê out-of-sample để đánh giá thay vì dựa vào vài ngày trúng liên tiếp.
