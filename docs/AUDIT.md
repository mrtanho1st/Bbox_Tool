# Audit công cụ cũ và thay đổi

## Phạm vi có thể truy cập

Workspace chứa file yêu cầu đính kèm; code LabelTool được cung cấp trong hội thoại. Không có bản repository tại `D:\Project\Tools` hoặc dataset thật trong môi trường này. Không thay đổi file gốc nào của người dùng; file yêu cầu được sao chép vào `reference`. Source mới được tạo trong thư mục riêng. Không tuyên bố đã backup hoặc chỉnh sửa ổ D: trên máy người dùng.

## Phát hiện ở code được cung cấp

1. Mapping phím là 1–9 nhưng lời nhắc ghi 1–6 hoặc 0–8.
2. Save bỏ qua box chưa có class; N/P/Q tự save có thể ghi lại nhãn khi chỉ xem và làm mất box chưa gán.
3. Tọa độ lưu theo ảnh hiển thị, ép int khi load, gây mất độ chính xác khi nhiều vòng load/save; zoom/resize dễ làm sai hệ tọa độ.
4. Click trong box luôn chọn box cũ, không có Draw Mode riêng nên khó vẽ box chồng nhau.
5. Undo chỉ xóa box cuối, không phục hồi chỉnh sửa/xóa/gán class; không có redo.
6. `iterdir()` bỏ sót thư mục con; cùng stem khác phần mở rộng ghi chung một file label.
7. Ghi trực tiếp `.txt` không backup/atomic; parser bỏ qua dòng sai số cột, nhưng có thể crash khi ID/float sai, không kiểm tra class ID vượt phạm vi.
8. Không có dữ liệu phân biệt ảnh chưa gán và ảnh âm đã xác nhận.
9. Không xử lý đóng cửa sổ bằng X trong vòng waitKey; thiếu entry point trong đoạn code gửi.
10. Class cố định tiền Việt Nam; không có project, metadata, EXIF policy hoặc báo lỗi giao dịch import.

## Phần kế thừa và tái cấu trúc

Giữ ý nghĩa công thức chuẩn hóa YOLO, quan hệ một ảnh/nhiều box, thứ tự class ID, chọn/gán/xóa, điều hướng N/P và kiểm tra kích thước box. Chuyển chúng thành model và parser độc lập Qt; không tái sử dụng vòng lặp OpenCV vì không đáp ứng chỉnh sửa/zoom/panel.

Chọn Pillow cho toàn bộ ảnh thay vì thêm dependency OpenCV không được sử dụng. Canvas QGraphicsView dùng scene theo pixel ảnh gốc; transform của view độc lập annotation. Tài liệu API tham khảo: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html

Chọn project JSON làm dữ liệu chuẩn thay vì chỉnh trực tiếp file `.txt` nguồn. Nhờ vậy các class mapping và annotation thay đổi trong một atomic replace duy nhất. YOLO/COCO là định dạng nhập/xuất. Cách này yêu cầu thêm dung lượng cho bản sao ảnh nhưng giảm nguy cơ sửa nhầm dataset gốc.
