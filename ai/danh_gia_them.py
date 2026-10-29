# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Đánh giá bổ sung sau khi huấn luyện.

1. Đo thời gian suy luận của mô hình .tflite trên CPU máy tính.
2. Tình huống kiểm thử 11 (ảnh dễ gây nhầm): chọn tự động N ảnh lớp binh_thuong
   trong tập kiểm tra có tỉ lệ điểm ảnh màu đỏ - cam (giống lửa) cao nhất, rồi đếm
   số ảnh mô hình KHÔNG gán nhãn lua.
3. Xuất lưới ảnh mẫu của từng lớp và lưới ảnh dễ gây nhầm kèm nhãn dự đoán.

Ví dụ: python danh_gia_them.py --data data/split --model outputs/model_lua_khoi.tflite --out outputs
"""
import argparse
import glob
import json
import os
import random
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_publish import LOP, MoHinh


def ti_le_do_cam(anh_bgr):
    hsv = cv2.cvtColor(anh_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mat_na = ((h <= 22) | (h >= 170)) & (s >= 100) & (v >= 120)   # do - cam, du dam va du sang
    return float(mat_na.mean())


def luoi(ds_anh, nhan, cot, duong_dan, o=160):
    hang = (len(ds_anh) + cot - 1) // cot
    nen = np.full((hang * (o + 24), cot * o, 3), 255, np.uint8)
    for i, (anh, chu) in enumerate(zip(ds_anh, nhan)):
        r, c = divmod(i, cot)
        nen[r * (o + 24):r * (o + 24) + o, c * o:(c + 1) * o] = cv2.resize(anh, (o, o))
        cv2.putText(nen, chu, (c * o + 4, r * (o + 24) + o + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    # imencode + ghi bang Python: cv2.imwrite khong ghi duoc duong dan co dau tren Windows
    with open(duong_dan, "wb") as f:
        f.write(cv2.imencode(".png", nen)[1].tobytes())


def main(a):
    mo_hinh = MoHinh(a.model)
    test = {l: sorted(glob.glob(os.path.join(a.data, "test", l, "*"))) for l in LOP}

    # 1. Thoi gian suy luan TFLite
    mau = cv2.imread(test["lua"][0])
    mo_hinh.du_doan(mau)
    t0 = time.perf_counter()
    for p in test["lua"][:100]:
        mo_hinh.du_doan(cv2.imread(p))
    ms = (time.perf_counter() - t0) / min(100, len(test["lua"])) * 1000

    # 2. Tinh huong 11
    diem = sorted(((ti_le_do_cam(cv2.imread(p)), p) for p in test["binh_thuong"]), reverse=True)[:a.n]
    chon, nhan_chon, ket = [], [], []
    for tl, p in diem:
        xs = mo_hinh.du_doan(cv2.imread(p))
        nhan = LOP[int(np.argmax(xs))]
        ket.append({"anh": os.path.basename(p), "ti_le_do_cam": round(tl, 3), "nhan": nhan, "do_tin_cay": round(float(xs.max()), 3)})
        chon.append(cv2.imread(p))
        nhan_chon.append(f"{nhan} {xs.max():.2f}")
    dung = sum(1 for k in ket if k["nhan"] != "lua")
    luoi(chon, nhan_chon, 5, os.path.join(a.out, "anh_de_nham.png"))

    # 3. Luoi anh mau
    random.seed(7)
    anh_mau, nhan_mau = [], []
    for l in LOP:
        for p in random.sample(sorted(glob.glob(os.path.join(a.data, "train", l, "*"))), 6):
            anh_mau.append(cv2.imread(p))
            nhan_mau.append(l)
    luoi(anh_mau, nhan_mau, 6, os.path.join(a.out, "luoi_anh_mau.png"))

    kq = {"ms_suy_luan_tflite": round(ms, 1), "th11_dung": dung, "th11_tong": len(ket), "th11_chi_tiet": ket}
    with open(os.path.join(a.out, "danh_gia_them.json"), "w", encoding="utf-8") as f:
        json.dump(kq, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in kq.items() if k != "th11_chi_tiet"}, ensure_ascii=False))
    for k in ket:
        print(k)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/split")
    p.add_argument("--model", default="outputs/model_lua_khoi.tflite")
    p.add_argument("--out", default="outputs")
    p.add_argument("--n", type=int, default=20)
    main(p.parse_args())
