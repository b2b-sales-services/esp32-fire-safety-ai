# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Chia tập dữ liệu THEO NGUỒN (video/ảnh gốc), không theo khung hình.

Đầu vào: data/raw/<lop>/<ma_nguon>__<...>.jpg
    - Ảnh tách từ video có tiền tố <ma_nguon>__ giống nhau -> cùng một nhóm.
    - Ảnh lẻ (không có "__") được coi là một nguồn riêng.
Đầu ra:  data/split/{train,val,test}/<lop>/...  và tệp thong_ke.csv

Ví dụ:
    python split_dataset.py --raw data/raw --out data/split --val 0.15 --test 0.15
"""
import argparse
import csv
import os
import random
import shutil
from collections import defaultdict

LOP = ["binh_thuong", "khoi", "lua"]
DUOI_ANH = (".jpg", ".jpeg", ".png", ".bmp")


def ma_nguon_cua(ten_tep):
    goc = os.path.splitext(ten_tep)[0]
    return goc.split("__")[0] if "__" in goc else goc


def chia(raw, out, ti_le_val, ti_le_test, hat_giong):
    random.seed(hat_giong)
    thong_ke = []
    for lop in LOP:
        thu_muc = os.path.join(raw, lop)
        if not os.path.isdir(thu_muc):
            print(f"Bo qua lop {lop}: khong co thu muc {thu_muc}")
            continue
        nhom = defaultdict(list)
        for ten in os.listdir(thu_muc):
            if ten.lower().endswith(DUOI_ANH):
                nhom[ma_nguon_cua(ten)].append(ten)

        cac_nguon = sorted(nhom)
        random.shuffle(cac_nguon)
        n = len(cac_nguon)
        n_test = max(1, round(n * ti_le_test)) if n >= 3 else 0
        n_val = max(1, round(n * ti_le_val)) if n >= 3 else 0
        tap = {
            "test": cac_nguon[:n_test],
            "val": cac_nguon[n_test:n_test + n_val],
            "train": cac_nguon[n_test + n_val:],
        }
        for ten_tap, ds_nguon in tap.items():
            dich = os.path.join(out, ten_tap, lop)
            os.makedirs(dich, exist_ok=True)
            so_anh = 0
            for nguon in ds_nguon:
                for ten in nhom[nguon]:
                    shutil.copy2(os.path.join(thu_muc, ten), os.path.join(dich, ten))
                    so_anh += 1
            thong_ke.append([lop, ten_tap, len(ds_nguon), so_anh])
            print(f"{lop:12s} {ten_tap:5s}: {len(ds_nguon):4d} nguon, {so_anh:5d} anh")

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "thong_ke.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lop", "tap", "so_nguon", "so_anh"])
        w.writerows(thong_ke)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Chia tap du lieu theo nguon video")
    p.add_argument("--raw", default="data/raw")
    p.add_argument("--out", default="data/split")
    p.add_argument("--val", type=float, default=0.15)
    p.add_argument("--test", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    chia(a.raw, a.out, a.val, a.test, a.seed)
