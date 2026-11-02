# PDF House Local

Bản dựng lại (clone) bộ công cụ của pdfhouse.com, chạy **hoàn toàn trên máy** — không upload lên cloud,
không giới hạn lượt dùng, không cần tài khoản.

## Chạy

```bash
cd ~/03_Projects_Personal/pdfhouse-clone
./run.sh              # http://127.0.0.1:8077
PORT=8090 ./run.sh    # đổi cổng
```

Lần đầu `run.sh` tự tạo `.venv` và cài `requirements.txt`.

## 22 công cụ

Tổ chức trang
- Hợp nhất PDF (bookmark, giữ metadata, đặt tên file ra)
- Chia PDF (theo dải trang / mỗi trang một file / N phần đều nhau → zip)
- Trích xuất trang
- Xoá trang
- Xoay trang (90/180/270, chọn dải trang)
- Sắp xếp trang (đổi thứ tự, lặp trang)

Chỉnh sửa & ký
- **Sửa PDF (editor)**: kéo vùng trên trang để thêm chữ (font Việt có dấu, cỡ, màu, căn lề), chèn ảnh,
  highlight, vẽ khung / mũi tên, xoá vùng nội dung (redact); hoàn tác, xoá hết, chuyển trang
- Thêm số trang (6 vị trí, 4 định dạng, số bắt đầu)
- Dấu nước (chữ tiếng Việt có dấu, độ đậm, góc xoay, lặp kín trang)
- Ký PDF (ảnh chữ ký PNG, chọn trang + vị trí theo %)
- Thêm ảnh vào PDF (logo, con dấu)
- Nén PDF (3 mức, tuỳ chọn đen trắng)
- Đặt mật khẩu (AES-256, tuỳ chọn cho copy)
- Gỡ mật khẩu

Chuyển đổi
- PDF → JPG / PNG (chọn dpi, dải trang, xuất zip)
- Ảnh → PDF (JPG/PNG/WEBP, khổ A4/Letter/theo ảnh, lề)
- PDF → TXT
- PDF → Word (.docx, giữ đoạn + ảnh)
- PDF → Excel (.xlsx, bóc bảng bằng `find_tables`, mỗi trang một sheet)
- PDF → PowerPoint (.pptx, mỗi trang một slide)
- Office → PDF (Word/Excel/PowerPoint/ODF qua LibreOffice)

Không có: OCR (chưa cài tesseract), 300+ biểu mẫu Mỹ (W-9, DS-11…) vì đó là nội dung bản quyền của họ, không phải công cụ.

## Kiến trúc

```
app/main.py          FastAPI: upload, run, download, preview; 1 endpoint cho mọi tool
app/registry.py      khai báo tool + form field (frontend tự dựng UI từ đây)
app/context.py       Ctx: session dir, sources, image, options
app/handlers/
  pages.py           merge, split, extract, delete-pages, rotate, organize
  edit.py            page-numbers, watermark, sign, add-image
  secure.py          compress, protect, unlock
  convert.py         pdf→jpg/png/txt/word/excel/pptx, images→pdf, office→pdf
static/              UI 1 trang, không build step
tests/test_tools.py  25 test: mỗi tool chạy thật trên fixture + assert output
data/sessions/       file tạm theo phiên, tự xoá sau 2 giờ
```

Thêm tool mới: 1 entry trong `registry.py` (id, group, accept, fields, needs_image) + 1 hàm
`handler(ctx) -> (list[Path], tên_file)` trong `app/handlers/` + đăng ký vào `HANDLERS`.

## API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/tools` | danh sách group + tool + form field |
| POST | `/api/upload` | multipart `files[]`, form `accept` (pdf/image/office), `slot`, `token?` |
| POST | `/api/run/{tool}` | `{token, fileIds, options, imageId}` → `{url, filename, size, count, elapsed, meta}` |
| GET | `/api/download/{token}/out/{folder}/{name}` | tải kết quả |
| GET | `/api/preview/{token}/{file_id}` | xem file gốc |
| GET | `/api/page-image/{token}/{file_id}/{page}` | render 1 trang thành PNG (dùng cho editor) |
| POST | `/api/edit` | `{token, fileId, ops[]}` → áp thao tác editor, trả `{url, filename, size}` |
| DELETE | `/api/session/{token}` | xoá phiên |
| GET | `/api/health` | trạng thái + giới hạn |

Ví dụ:

```bash
TOKEN=$(curl -s -F "files=@bao-cao.pdf" -F "accept=pdf" \
  http://127.0.0.1:8077/api/upload | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -s -X POST http://127.0.0.1:8077/api/run/watermark \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"fileIds\":[],\"options\":{\"text\":\"BẢN NHÁP\",\"opacity\":0.2}}"
```

## Editor: định dạng `ops`

Toạ độ tính theo % kích thước trang (`x`, `y`, `w`, `h`), `page` đánh số từ 1.

```json
[
  {"type": "text", "page": 1, "rect": {"x": 12, "y": 42, "w": 60, "h": 8},
   "text": "Đã kiểm tra", "size": 16, "color": "#1d4ed8", "align": "left"},
  {"type": "image", "page": 1, "rect": {"x": 60, "y": 75, "w": 25, "h": 10}, "imageId": "ab12cd34.png"},
  {"type": "highlight", "page": 1, "rect": {"x": 10, "y": 9, "w": 48, "h": 5}, "color": "#ffe066", "opacity": 0.45},
  {"type": "rect",    "page": 2, "rect": {"x": 10, "y": 30, "w": 60, "h": 12}, "color": "#e11d48", "width": 2},
  {"type": "arrow",   "page": 2, "rect": {"x": 10, "y": 60, "w": 30, "h": 10}, "color": "#0f766e"},
  {"type": "ellipse", "page": 2, "rect": {"x": 55, "y": 20, "w": 20, "h": 8}, "color": "#2563eb"},
  {"type": "redact",  "page": 2, "rect": {"x": 10, "y": 13, "w": 52, "h": 6}, "fill": "#ffffff"}
]
```

Thứ tự áp dụng cố định: redact (xoá nội dung) → ảnh/hình → highlight → chữ.
Redact xoá vĩnh viễn chữ và ảnh nằm dưới vùng chọn.

## Giới hạn & ghi chú

- 30 file/lần, 100 MB/file, 400 MB tổng; phiên giữ 2 giờ rồi tự xoá.
- Upload chặn PDF có mật khẩu (dùng tool "Gỡ mật khẩu" với file gốc trước).
- `pdf-to-excel` cần bảng có kẻ ô; bản scan không bóc được (cần OCR).
- `pdf-to-word` giữ text theo block + ảnh, không giữ layout chính xác như Adobe.
- `office-to-pdf` cần LibreOffice (đã có sẵn tại /Applications/LibreOffice.app).
- Server chỉ nghe `127.0.0.1`. Muốn mở LAN thì sửa `run.sh` và thêm auth.

## Test

```bash
./.venv/bin/python -m pytest -q     # 25 passed
```
