# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Tách khung hình từ video do nhóm tự quay.

Mỗi video được coi là một "nguồn" (source). Tên ảnh xuất ra có dạng
    <lop>/<ma_nguon>__<so_khung>.jpg
để bước chia tập (split_dataset.py) gom được mọi khung hình của cùng một video
vào cùng một tập, tránh rò rỉ dữ liệu giữa tập huấn luyện và tập kiểm tra.

Ví dụ:
    python extract_frames.py --video raw_video/nen_01.mp4 --lop lua --out data/raw --moi 10
"""
import argparse
import os

import cv2


def tach_khung(duong_dan_video, lop, thu_muc_ra, moi_n_khung, kich_thuoc):
    ma_nguon = os.path.splitext(os.path.basename(duong_dan_video))[0]
    thu_muc_lop = os.path.join(thu_muc_ra, lop)
    os.makedirs(thu_muc_lop, exist_ok=True)

    cap = cv2.VideoCapture(duong_dan_video)
    if not cap.isOpened():
        raise SystemExit(f"Khong mo duoc video: {duong_dan_video}")

    chi_so, da_luu = 0, 0
    while True:
        ok, khung = cap.read()
        if not ok:
            break
        if chi_so % moi_n_khung == 0:
            khung = cv2.resize(khung, (kich_thuoc, kich_thuoc))
            ten = f"{ma_nguon}__{chi_so:05d}.jpg"
            cv2.imwrite(os.path.join(thu_muc_lop, ten), khung)
            da_luu += 1
        chi_so += 1
    cap.release()
    print(f"{duong_dan_video}: doc {chi_so} khung, luu {da_luu} anh vao {thu_muc_lop}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Tach khung hinh tu video")
    p.add_argument("--video", required=True, help="Duong dan video")
    p.add_argument("--lop", required=True, choices=["lua", "khoi", "binh_thuong"])
    p.add_argument("--out", default="data/raw", help="Thu muc anh dau ra")
    p.add_argument("--moi", type=int, default=10, help="Lay 1 khung trong moi N khung")
    p.add_argument("--size", type=int, default=224, help="Kich thuoc anh vuong")
    a = p.parse_args()
    tach_khung(a.video, a.lop, a.out, a.moi, a.size)
