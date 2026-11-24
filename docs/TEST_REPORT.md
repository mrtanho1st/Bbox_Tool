# Báo cáo kiểm thử — Tools by hkhang17pls

Ngày thực hiện: 22/10/2026.

## Môi trường và kết quả thực tế

- Linux x86_64, Python 3.12.14.
- PySide6 6.12.0; Pillow 12.3.0; PyYAML 6.0.3; pytest 9.1.1.
- GUI chạy bằng Qt `offscreen`, có QTest gửi sự kiện chuột thực vào viewport.
- `python -m compileall -q app main.py`: đạt.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`: **48 passed**, khoảng 0,46 giây trong lần chạy trước đóng gói.
- `ruff check --select F`: không còn lỗi tên biến/import không dùng sau sửa tự động.
- Đã chụp và kiểm tra giao diện của cửa sổ thực, dùng ảnh hình học tự tạo làm fixture; không dùng dataset cá nhân.

## Đã kiểm chứng

- Project mới, mở lại, nhiều project có class độc lập, đường dẫn tiếng Việt/khoảng trắng.
- Không ghi lại dữ liệu khi chỉ mở/xem; không tự tạo `.txt` rỗng.
- Save chặn box chưa gán, box lỗi, ảnh rỗng chưa xác nhận.
- Phục hồi draft kể cả box chưa gán; chặn migration khi còn draft.
- YOLO round-trip độ chính xác float, dữ liệu sai cột/ID/NaN/box âm.
- COCO category ID không liên tục; import và export bounding boxes.
- Import nhãn cũ không thay đổi source; import ảnh hỏng rollback batch.
- Export staging rollback khi giả lập lỗi ổ đĩa; xuất ảnh rỗng khi xác nhận rõ ràng.
- Atomic write giữ file cũ khi giả lập lỗi replace; có backup.
- Đổi class đồng bộ annotation/backup; chặn xóa class đang sử dụng; hơn 9 class.
- Duplicate project mang theo ảnh với đường dẫn tương đối.
- Kiểm tra ảnh trùng/gần giống qua split, nhãn orphan và trùng tên nguồn.
- Split có seed tái lập, không sửa dữ liệu project.
- EXIF 1–8: toàn khung vẫn trong giới hạn; test ảnh JPEG xoay thực khi import.
- Undo/Redo, move chặn biên.
- GUI: vẽ nhiều box chồng, chọn luân phiên Alt+click, zoom/resize không đổi tọa độ, move/resize, save, draft và dialog tác vụ nền.
- Project 257 ảnh: mở metadata không gọi decoder để tải toàn bộ ảnh vào RAM. Đây không phải benchmark hàng triệu ảnh.

## Lỗi phát hiện và đã sửa

- Edit box đang chọn dưới box khác bị chọn lại box trên: giữ lựa chọn rõ ràng khi kéo trong Edit.
- Discard tại cùng ảnh có thể để canvas giữ thay đổi chưa lưu: khôi phục cả box/status/history từ dữ liệu đã lưu.
- Nhãn chữ trên canvas không cập nhật kích thước theo zoom: vẽ lại overlay khi zoom.
- Thay API Pillow bị deprecated bằng đọc bytes cho dHash.
- Lệnh tạo test ban đầu dùng nhầm prefix thư mục nên chưa có test được tạo; đã sửa đường dẫn và thực sự chạy pytest. Kết quả báo cáo chỉ tính lần chạy thành công.

## Giới hạn còn lại — không tuyên bố không có lỗi

1. Chưa chạy Windows 10/11, Python 3.13, màn hình DPI cao hoặc build/khởi chạy Windows EXE. Có script build kiểm thử trước PyInstaller.
2. Chưa kiểm thử HEIC/HEIF thực tế; cần pillow-heif tùy chọn.
3. Chưa hỗ trợ tất cả layout YOLO/Roboflow qua data.yaml. Import Folder là đường nhập linh hoạt; không tự xử lý manifest ảnh hoặc external path trong YAML.
4. EXIF nhãn đầu vào giả định pixel thô trước orientation; dataset có quy ước khác cần chuẩn hóa trước.
5. Class migration có backup và chặn class còn dùng; chưa có wizard gộp/xóa mọi annotation theo class hoặc nút rollback trong GUI.
6. Box undo/redo theo ảnh, không undo metadata/class trên toàn project. Phím tắt tùy biến chưa triển khai.
7. Ảnh đang xem được giải mã toàn bộ; thumbnail chỉ giữ các hàng đang hiển thị. Chưa có tile rendering cho ảnh siêu lớn. Import/validate/export chạy tác vụ nền nhưng chưa có hủy giữa tác vụ hoặc tiến độ % chính xác.
8. Gần giống dùng dHash đơn giản, có false positive/negative và phép so sánh có thể O(N²). Dataset rất lớn cần giải pháp indexing/group splitting tốt hơn.
9. JSON chứa toàn bộ annotation; mỗi Save sao lưu/ghi lại metadata, nên hiệu năng và dung lượng backup cần đo thêm với dataset cực lớn. Không có cộng tác đa tiến trình được hỗ trợ.
10. Chưa triển khai Pascal VOC, polygon, segmentation, keypoints, OBB, AI auto-label; không có nút giả cho các tính năng đó.
11. Dataset thiếu nhãn bị chặn xuất thay vì tự quyết định ảnh âm. Hãy xử lý tất cả ảnh hoặc tạo project chứa tập cần xuất.
12. Ứng dụng không tự động ghi nhãn YOLO `.txt` ngay tại Save: Save lưu project, Export sinh dataset. Không trực tiếp sửa dữ liệu nguồn.

Bản bàn giao đáp ứng luồng annotation Bounding Box đa project cốt lõi và phần lớn chức năng dataset; chưa phải nghiệm thu đầy đủ tất cả yêu cầu nâng cao trong master prompt.
