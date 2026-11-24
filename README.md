# Tools by hkhang17pls

Ứng dụng desktop gán nhãn **Bounding Box**, nhiều project, class tùy chỉnh, dùng offline sau khi cài thư viện. Đây là bộ source chạy được; không phải bản EXE đã kiểm chứng trên Windows.

## Chạy nhanh trên Windows 10/11

1. Giải nén toàn bộ thư mục, ví dụ `D:\Project\Tools_by_hkhang17pls`.
2. Cài Python 3.13 64-bit và chọn **Add python.exe to PATH**. Không bắt buộc có Python Launcher (`py`).
3. Nhấp đúp **run_windows.bat**. Lần đầu cần Internet để tải thư viện; các lần sau dùng offline.
4. Không chạy trực tiếp bên trong file ZIP.

Nếu muốn chạy từ terminal tại thư mục vừa giải nén:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Nếu đã kích hoạt môi trường phù hợp, lệnh khởi động là `python main.py`.
Hai file BAT dùng `ensure_python.bat` để tìm Python: ưu tiên `.venv` hiện có, sau đó thử `python` và `py -3` (Python 3.11 trở lên, 64-bit).
Nếu không tìm thấy Python chạy được, cài Python với tùy chọn PATH rồi đóng cửa sổ terminal cũ và chạy lại.
Nếu `.venv` bị hỏng hoặc được sao chép từ máy khác, đổi tên thành `.venv_old` để chương trình tạo môi trường mới.
Không cần Jupyter, Colab, OpenCV hay tài khoản cloud. Phần xử lý ảnh dùng Pillow; giao diện dùng PySide6. Logic tọa độ và định dạng YOLO từ công cụ cũ được giữ về ý nghĩa, tái cấu trúc để không phụ thuộc cửa sổ OpenCV.

**Môi trường kiểm thử bàn giao:** Linux, Python 3.12.14, Qt offscreen. Windows/Python 3.13 và EXE cần chạy bộ kiểm thử lại tại máy đích. Chi tiết: `docs/TEST_REPORT.md`.

## Bắt đầu với ảnh của bạn

1. Chọn **New Project**, nhập tên, mô tả và mỗi dòng một class.
2. Chọn một thư mục project **rỗng**, tách khỏi dataset nguồn. Ứng dụng từ chối thư mục đã có dữ liệu.
3. Chọn **Dataset → Import Folder** để nhập toàn bộ thư mục con, hoặc **Import Images** để chọn ảnh riêng.
4. Nếu có nhãn YOLO cũ, chọn thư mục gốc nhãn có cấu trúc con tương ứng. Với dataset chuẩn, có thể dùng **Import YOLO Dataset** ngay từ Home.
5. Class phải theo **đúng thứ tự ID cũ**. Không đoán tên class từ tên folder.
6. Chọn class bên phải → Draw → kéo chuột tạo box. Edit để di chuyển hoặc kéo một trong bốn góc.
7. Chọn `Completed` sau khi hoàn thành ảnh rồi **Ctrl+S**.
8. **Dataset → Export YOLO** để lấy ảnh, các file `.txt`, `data.yaml`, và `source_map.json`.

Với công cụ tiền Việt Nam cũ, nhập class theo đúng thứ tự sau (chỉ là cấu hình tùy chọn, không hardcode trong ứng dụng):

```text
1000
2000
5000
10000
20000
50000
100000
200000
500000
```

ID là 0–8; phím nhanh là **1–9**. Đoạn code cũ có hướng dẫn 0–8 và 1–6 không khớp với mapping thực tế 1–9; bản này thống nhất 1–9.

## Cách lưu và bảo vệ dữ liệu

### Nhập dataset từ YAML

Chọn **Nhập từ YAML** ở màn hình đầu hoặc **Dataset → Import YAML Dataset**, rồi chọn file `.yaml` / `.yml` của dataset YOLO. Khi chưa có project, ứng dụng mở hộp tạo project với danh sách class lấy từ YAML.

```yaml
path: dataset
train: images/train
val: images/val
test: images/test
names:
  0: car
  1: bus
nc: 2
```

`path` tương đối được tính từ thư mục chứa YAML; nếu bỏ `path`, dùng thư mục chứa YAML. Đường dẫn train/val/test được tính từ `path`, hoặc có thể là đường dẫn tuyệt đối. Mỗi tập nhận thư mục ảnh, file danh sách `.txt` hoặc danh sách các đường dẫn; đường dẫn ảnh trong `.txt` tính từ thư mục chứa file danh sách. Chỉ khai báo các tập thực sự có dữ liệu.

Label được tìm bằng cách thay thư mục `images` bằng `labels` và đổi đuôi thành `.txt` (hỗ trợ cả `images/train` và `train/images`). Nếu đường dẫn không có thư mục `images`, tìm label cạnh ảnh. Ảnh thiếu label được cảnh báo và nhập ở trạng thái Unlabeled. Ứng dụng giữ tập train/val/test, sao chép ảnh vào project và không sửa dataset nguồn. YAML chỉ dùng để đọc dữ liệu cục bộ, không chạy lệnh tải dataset.

### Lưu dữ liệu

- Dataset nguồn chỉ được đọc. Ảnh được **sao chép** vào project, nhãn được đọc vào dữ liệu nội bộ.
- **Save lưu vào `project.json`**, không ghi đè `.txt` nguồn. **Export** mới tạo bộ nhãn YOLO/COCO riêng. Save All tương đương Save vì chỉ một ảnh có thay đổi chưa lưu trong một thời điểm.
- `project.json` chứa class, màu, annotation, trạng thái, split và đường dẫn tương đối. Chuyển cả thư mục project sang ổ khác vẫn mở được.
- Ghi JSON bằng file tạm, flush/fsync và replace. Mỗi lần ghi project có backup phiên bản trước trong `.backups`.
- Xem ảnh không ghi annotation. Box chưa gán class chặn Save/Export, không bị bỏ qua âm thầm.
- Ảnh không có đối tượng phải chọn **Confirmed Empty**, lưu và xác nhận. File YOLO rỗng nhập từ ngoài vẫn là Unlabeled vì chưa đủ thông tin để coi là ảnh âm đã kiểm tra.
- Bản nháp trong `.drafts`, mặc định mỗi **10 giây**. File → Settings chỉnh khoảng 2–300 giây. Bản nháp có thể giữ cả box chưa gán class.
- Mở lại đúng ảnh có bản nháp sẽ hỏi khôi phục. Chọn No sẽ xóa bản nháp và dùng bản lưu. Tối đa khoảng thời gian giữa hai lần autosave có thể chưa được lưu khi mất điện/kill process.
- Khi chuyển ảnh/đóng: Save, Discard hoặc Cancel. **Discard thực sự bỏ thay đổi và bản nháp**.
- Đổi class cần xử lý hết bản nháp trước. Backup không tự dọn để tránh mất lịch sử; cần theo dõi dung lượng với project nhiều annotation.
- Có phát hiện project bị sửa bên ngoài trước khi ghi. **Không mở cùng một project để chỉnh sửa đồng thời bằng nhiều tiến trình**; đây chưa phải ứng dụng cộng tác nhiều người.

### Phục hồi backup

Đóng ứng dụng; sao chép cả project để dự phòng. Trong `.backups`, tìm file `project.json.<id>.bak` theo thời gian sửa đổi. Sao chép phiên bản cần phục hồi thành `project.json`. Ảnh trong `images/` được giữ nguyên, nên backup metadata có thể tham chiếu lại ảnh. Không xóa thư mục ảnh khi phục hồi.

## Phím tắt và thao tác

| Phím/thao tác | Chức năng |
|---|---|
| B / V / E / G | Draw / Select / Edit / Pan |
| Kéo chuột trái trong Draw | Tạo box, kể cả chồng box cũ |
| Kéo trong Edit | Di chuyển box đã chọn |
| Kéo góc trong Edit | Resize box |
| Alt + click | Luân phiên chọn các box chồng nhau |
| Danh sách box bên phải | Chọn trực tiếp box nằm dưới |
| 1–9 | Chọn class, đồng thời gán vào box đang chọn |
| Class Panel + nút Gán class | Dùng mọi class, kể cả từ class thứ 10 trở đi |
| Ctrl+Z / Ctrl+Y | Undo / Redo, tối đa 100 bước trong ảnh hiện tại |
| Delete / Ctrl+D | Xóa / nhân đôi box |
| Cuộn chuột / + / - | Zoom |
| F | Fit ảnh |
| N / P | Ảnh tiếp / ảnh trước |
| Ctrl+S / Ctrl+Shift+S | Save / Save All |
| Ctrl+N / Ctrl+O / Ctrl+Q | Tạo / mở / thoát |

Undo/Redo áp dụng annotation, không áp dụng thay đổi class toàn dataset, split hoặc metadata project. Các thao tác đó có xác nhận/backup riêng.

## Quản lý project và class

- Home: tạo/mở, nhập YOLO/COCO, danh sách gần đây, bỏ khỏi danh sách (không xóa dataset).
- Project Settings: sửa tên và mô tả.
- Duplicate Project: sao chép ảnh + nhãn sang thư mục mới, không sao chép bản nháp/backup.
- Manage Classes: thêm, đổi tên, màu, xóa class chưa sử dụng, sắp xếp, nhập/xuất TXT.
- Nhập TXT trong Class Manager **thêm vào** danh sách; không tự thay thế danh sách cũ.
- Sau khi sắp xếp/xóa, bảng trước/sau hiện để xác nhận. Tất cả annotation đổi ID cùng một lần ghi `project.json` có backup.
- Không xóa class đang có annotation; hãy chuyển các box sang class khác trước.
- Thống kê có số box/class, số ảnh/class, ảnh nhiều đối tượng/nhiều class, trạng thái, split và biểu đồ thanh; xuất CSV. Thống kê dùng bản **đã lưu**.

## Nhập/xuất dataset

**YOLO chuẩn:** `images/train`, `images/valid` hoặc `images/val`, `images/test`; `labels/` tương ứng; `data.yaml` chứa `names`. Import YOLO không tự thực thi/chạy nội dung YAML, dùng `safe_load`.

Với cấu trúc khác, dùng Import Folder và chọn label root tương ứng. Bản này chưa diễn giải toàn bộ biến thể `path/train/val` trong YAML, file danh sách ảnh `.txt`, hoặc layout Roboflow `train/images`. Các trường hợp đó nhập từng cặp thư mục bằng Import Folder; gán split thủ công nếu không có tên split trong đường dẫn tương đối.

**COCO:** chọn JSON và gốc ảnh khớp `file_name`; category IDs tùy ý được ánh xạ theo ID tăng dần sang 0…N-1. Xuất COCO dùng IDs 1…N. Chỉ chuyển Bounding Box; không bảo toàn segmentation, keypoints hay metadata mở rộng. Từ chối `iscrowd=1` để tránh âm thầm làm mất ngữ nghĩa.

**Định hướng EXIF:** ảnh có EXIF xoay/lật được tạo thành bản PNG đúng chiều trong project; ảnh nguồn không thay đổi. Nhãn đầu vào được hiểu theo **pixel thô trước EXIF** và chuyển cùng ảnh. Nếu phần mềm cũ đã gán nhãn theo ảnh sau xoay, cần chuẩn hóa ảnh/nhãn trước khi nhập để tránh xoay tọa độ hai lần. Không có cách tự suy ra chắc chắn quy ước của mọi dataset.

Ảnh JPEG/PNG/BMP/WEBP được hỗ trợ. HEIC/HEIF là tùy chọn: cài `python -m pip install pillow-heif`; chưa kiểm thử với ảnh HEIC thực tế trong lần bàn giao này. Không đọc MOV/Live Photo video.

**Export:** chọn thư mục cha và tên thư mục mới; không ghi đè đích cũ. Xuất từng ảnh, ghi vào staging rồi đổi tên khi thành công. `source_map.json` ánh xạ ID nội bộ với tên ảnh nguồn. Tên nội bộ dùng ID để tránh trùng stem hoặc hoa/thường trên Windows.

Mặc định giữ split; ảnh chưa được phân tập nằm trong `unassigned`. **Split & Export YOLO** nhận tỷ lệ và seed, xem trước, kiểm tra trùng/gần giống theo split đề xuất, rồi xuất bản sao. Không thay đổi split của project khi chỉ chia để export. Nếu chưa có train/valid thì dataset xuất chưa đủ cấu hình để train trực tiếp.

Export chặn ảnh chưa có box mà chưa Confirmed Empty, và chặn khi còn bản nháp. Box đã gán class ở trạng thái In Progress vẫn có thể xuất; hãy tự review chất lượng nhãn trước khi train.

Validate dùng SHA-256 cho ảnh trùng file và dHash (khoảng cách ≤4) cho nghi gần giống giữa các tập. Đây là cảnh báo hỗ trợ review, **không bảo đảm phát hiện mọi rò rỉ dữ liệu**. Ảnh cùng cảnh chụp liên tiếp nên được chia theo nhóm người chụp/phiên chụp thay vì chia ảnh ngẫu nhiên.

## Kiểm thử và đóng gói

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall app main.py
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:QT_QPA_PLATFORM
```

Đóng gói Windows: chạy `build_windows.bat`. Script dừng khi kiểm thử lỗi, sau đó mới gọi PyInstaller. Thành phẩm dự kiến là **toàn bộ** `dist\Tools by hkhang17pls\`, không chỉ riêng `.exe`. Chưa build EXE từ Linux và không gọi source ZIP là EXE.

## Cấu trúc

- `app/core`: Box, Undo/Redo, project, class migration.
- `app/formats`: YOLO và COCO.
- `app/dataset`: đọc ảnh, EXIF, scan, validation, thống kê, chia/xuất.
- `app/services`: ghi file an toàn, backup, kiểm soát đường dẫn.
- `app/gui`: canvas Qt, cửa sổ chính, các dialog, theme.
- `tests`: unit, integration và Qt mouse/smoke tests.
- `docs`: audit và kết quả kiểm thử/giới hạn.
- `reference/requirements_original.txt`: yêu cầu gốc đã cung cấp.

Chưa triển khai Pascal VOC, segmentation/polygon/keypoints/OBB, AI tự gán nhãn, cộng tác mạng, phím tắt tùy biến, hoặc bộ cache tile cho ảnh cực lớn. Giao diện không quảng cáo các chức năng này là đã hỗ trợ.
