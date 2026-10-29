# Mô tả tập dữ liệu - Nhóm 07

Tập ảnh gồm 3 lớp: `lua`, `khoi`, `binh_thuong`. Ảnh gốc **không** đưa vào kho mã nguồn
(dung lượng lớn); thư mục này chỉ chứa mô tả và thống kê.

## Cấu trúc thư mục khi huấn luyện

```
data/raw/<lop>/<ma_nguon>__<so_khung>.jpg   # ảnh tách từ video (extract_frames.py)
data/raw/<lop>/<ten_anh>.jpg                # ảnh lẻ từ tập công khai
data/split/{train,val,test}/<lop>/          # tạo bởi split_dataset.py (chia theo nguồn)
```

## Nguồn A - Ảnh/video nhóm tự quay

Quay trong điều kiện an toàn: nến, bật lửa, nhang đặt trên bề mặt không cháy, có bình
nước/bình chữa cháy mini, có người thứ hai giám sát, không quay trong phòng kín.

| Mã nguồn (video) | Lớp | Nội dung | Điều kiện sáng | Số ảnh tách |
|---|---|---|---|---|
| `nen_01` | lua | <điền> | <điền> | <điền> |
| `nhang_01` | khoi | <điền> | <điền> | <điền> |
| `den_do_01` | binh_thuong | đèn đỏ cam (ảnh dễ gây nhầm) | <điền> | <điền> |
| ... | | | | |

## Nguồn B - Tập dữ liệu công khai

Ghi đủ: tên tập, tác giả, nền tảng lưu trữ, giấy phép, đường dẫn thật (không ghi theo trí nhớ).

| Tên tập dữ liệu | Tác giả | Nền tảng | Giấy phép | Đường dẫn | Số ảnh dùng / lớp |
|---|---|---|---|---|---|
| <điền> | <điền> | <điền> | <điền> | <điền> | <điền> |

## Thống kê sau khi chia (dán từ `data/split/thong_ke.csv`)

| Lớp | train | val | test | Tổng |
|---|---|---|---|---|
| binh_thuong | | | | |
| khoi | | | | |
| lua | | | | |

Yêu cầu tối thiểu: 200 ảnh mỗi lớp; lớp `binh_thuong` phải có ảnh dễ gây nhầm
(ánh đèn đỏ cam, nắng chiếu, hơi nước, đèn hậu xe).
