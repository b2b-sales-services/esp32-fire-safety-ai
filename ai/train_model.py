# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Huấn luyện mô hình phân loại ảnh 3 lớp: binh_thuong, khoi, lua.

Phương pháp: học chuyển giao (transfer learning) từ MobileNetV2 đã huấn luyện
trên ImageNet. Giai đoạn 1 đóng băng phần trích đặc trưng, chỉ huấn luyện đầu
phân loại; giai đoạn 2 mở khóa một số lớp cuối và tinh chỉnh (fine-tuning)
với tốc độ học nhỏ. Chạy được trên Google Colab (GPU) hoặc máy cá nhân.

Đầu vào:  data/split/{train,val,test}/<lop>/*.jpg  (tạo bởi split_dataset.py)
Đầu ra:   outputs/
    model_lua_khoi.keras, model_lua_khoi.tflite, labels.txt
    duong_cong_huan_luyen.png, ma_tran_nham_lan.png, metrics.json

Ví dụ:
    python train_model.py --data data/split --out outputs --epochs1 10 --epochs2 10
"""
import argparse
import json
import os
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix

LOP = ["binh_thuong", "khoi", "lua"]   # Thứ tự cố định, dùng chung với detect_publish.py
KICH_THUOC = 224


def nap_tap(thu_muc, tron, batch):
    return tf.keras.utils.image_dataset_from_directory(
        thu_muc, labels="inferred", label_mode="int", class_names=LOP,
        image_size=(KICH_THUOC, KICH_THUOC), batch_size=batch, shuffle=tron, seed=7)


def tao_mo_hinh():
    # Tăng cường dữ liệu: lật ngang, xoay nhẹ, đổi độ sáng và độ tương phản
    tang_cuong = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.05),
        tf.keras.layers.RandomBrightness(0.2),
        tf.keras.layers.RandomContrast(0.2),
    ], name="tang_cuong")

    goc = tf.keras.applications.MobileNetV2(
        input_shape=(KICH_THUOC, KICH_THUOC, 3), include_top=False, weights="imagenet")
    goc.trainable = False

    vao = tf.keras.Input(shape=(KICH_THUOC, KICH_THUOC, 3))
    x = tang_cuong(vao)
    x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
    x = goc(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    ra = tf.keras.layers.Dense(len(LOP), activation="softmax")(x)
    return tf.keras.Model(vao, ra), goc


def ve_duong_cong(ls1, ls2, duong_dan):
    gop = {k: ls1.history[k] + ls2.history.get(k, []) for k in ls1.history}
    n1 = len(ls1.history["loss"])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(gop["accuracy"], label="train"); ax[0].plot(gop["val_accuracy"], label="val")
    ax[0].set_title("Do chinh xac theo epoch"); ax[0].set_xlabel("epoch")
    ax[1].plot(gop["loss"], label="train"); ax[1].plot(gop["val_loss"], label="val")
    ax[1].set_title("Ham mat mat theo epoch"); ax[1].set_xlabel("epoch")
    for a in ax:
        a.axvline(n1 - 0.5, color="gray", linestyle="--", linewidth=1)  # Mốc bắt đầu tinh chỉnh
        a.legend(); a.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(duong_dan, dpi=150); plt.close(fig)


def ve_ma_tran(cm, duong_dan):
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(LOP))); ax.set_xticklabels(LOP)
    ax.set_yticks(range(len(LOP))); ax.set_yticklabels(LOP)
    ax.set_xlabel("Nhan du doan"); ax.set_ylabel("Nhan thuc te")
    for i in range(len(LOP)):
        for j in range(len(LOP)):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_title("Ma tran nham lan tren tap kiem tra")
    fig.tight_layout(); fig.savefig(duong_dan, dpi=150); plt.close(fig)


def main(a):
    os.makedirs(a.out, exist_ok=True)
    train = nap_tap(os.path.join(a.data, "train"), True, a.batch)
    val = nap_tap(os.path.join(a.data, "val"), False, a.batch)
    test = nap_tap(os.path.join(a.data, "test"), False, a.batch)
    AUTOTUNE = tf.data.AUTOTUNE
    train, val = train.prefetch(AUTOTUNE), val.prefetch(AUTOTUNE)

    mo_hinh, goc = tao_mo_hinh()
    dung_som = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=3, restore_best_weights=True)

    # Giai đoạn 1: chỉ huấn luyện đầu phân loại
    mo_hinh.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                    loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    ls1 = mo_hinh.fit(train, validation_data=val, epochs=a.epochs1, callbacks=[dung_som])

    # Giai đoạn 2: mở khóa a.unfreeze lớp cuối của MobileNetV2 để tinh chỉnh
    goc.trainable = True
    for lop in goc.layers[:-a.unfreeze]:
        lop.trainable = False
    mo_hinh.compile(optimizer=tf.keras.optimizers.Adam(1e-5),
                    loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    ls2 = mo_hinh.fit(train, validation_data=val, epochs=a.epochs2, callbacks=[dung_som])
    ve_duong_cong(ls1, ls2, os.path.join(a.out, "duong_cong_huan_luyen.png"))

    # Đánh giá trên tập kiểm tra độc lập (nguồn video không có trong train/val)
    y_that, y_doan = [], []
    for anh, nhan in test:
        y_that.extend(nhan.numpy())
        y_doan.extend(np.argmax(mo_hinh.predict(anh, verbose=0), axis=1))
    cm = confusion_matrix(y_that, y_doan, labels=range(len(LOP)))
    ve_ma_tran(cm, os.path.join(a.out, "ma_tran_nham_lan.png"))
    bao_cao = classification_report(y_that, y_doan, labels=range(len(LOP)),
                                    target_names=LOP, output_dict=True, zero_division=0)
    print(classification_report(y_that, y_doan, labels=range(len(LOP)),
                                target_names=LOP, zero_division=0))

    # Đo thời gian suy luận trung bình một ảnh trên máy đang chạy
    mau = next(iter(test))[0][:1]
    mo_hinh.predict(mau, verbose=0)
    bat_dau = time.perf_counter()
    for _ in range(50):
        mo_hinh.predict(mau, verbose=0)
    ms_moi_anh = (time.perf_counter() - bat_dau) / 50 * 1000

    mo_hinh.save(os.path.join(a.out, "model_lua_khoi.keras"))
    chuyen = tf.lite.TFLiteConverter.from_keras_model(mo_hinh)
    chuyen.optimizations = [tf.lite.Optimize.DEFAULT]   # Lượng tử hóa trọng số
    tflite = chuyen.convert()
    with open(os.path.join(a.out, "model_lua_khoi.tflite"), "wb") as f:
        f.write(tflite)
    with open(os.path.join(a.out, "labels.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOP))

    ket_qua = {
        "do_chinh_xac_test": bao_cao["accuracy"],
        "recall_lua": bao_cao["lua"]["recall"],
        "theo_lop": {k: bao_cao[k] for k in LOP},
        "ma_tran_nham_lan": cm.tolist(),
        "ms_suy_luan_keras": ms_moi_anh,
        "kich_thuoc_tflite_kb": len(tflite) / 1024,
        "so_epoch": [len(ls1.history["loss"]), len(ls2.history["loss"])],
    }
    with open(os.path.join(a.out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(ket_qua, f, ensure_ascii=False, indent=2)
    print(json.dumps(ket_qua, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Huan luyen mo hinh phan loai lua/khoi")
    p.add_argument("--data", default="data/split")
    p.add_argument("--out", default="outputs")
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--epochs1", type=int, default=10)
    p.add_argument("--epochs2", type=int, default=10)
    p.add_argument("--unfreeze", type=int, default=30, help="So lop cuoi mo khoa khi tinh chinh")
    main(p.parse_args())
