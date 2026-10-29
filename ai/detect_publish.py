# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Nhánh thị giác máy tính chạy trên PC.

Đọc webcam hoặc tệp video, chạy mô hình phân loại 3 lớp mỗi N khung hình,
làm mượt bằng cách chỉ đổi nhãn khi cùng một nhãn lặp lại K lần liên tiếp,
rồi phát bản tin JSON ngắn lên chủ đề MQTT mỗi CHU_KY_GUI giây:
    {"nhan":"lua","do_tin_cay":0.93,"ts":1730000000}
Đồng thời đăng ký chủ đề trạng thái để hiển thị trạng thái ESP32 trên cửa sổ
(kiểm chứng kênh MQTT hai chiều).

Ví dụ:
    python detect_publish.py --source 0                      # webcam
    python detect_publish.py --source video/test_lua.mp4     # tệp video
    python detect_publish.py --source 0 --model outputs/model_lua_khoi.keras
"""
import argparse
import json
import time
import uuid
from collections import deque

import cv2
import numpy as np
import paho.mqtt.client as mqtt

LOP = ["binh_thuong", "khoi", "lua"]
KICH_THUOC = 224
MAU = {"binh_thuong": (0, 160, 0), "khoi": (0, 200, 255), "lua": (0, 0, 255)}


class MoHinh:
    """Bọc mô hình .tflite hoặc .keras, trả về vector xác suất 3 lớp."""

    def __init__(self, duong_dan):
        self.la_tflite = duong_dan.endswith(".tflite")
        if self.la_tflite:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                import tensorflow as tf
                Interpreter = tf.lite.Interpreter
            # Doc file bang Python: TFLite khong mo duoc duong dan co dau tieng Viet tren Windows
            with open(duong_dan, "rb") as f:
                self.it = Interpreter(model_content=f.read())
            self.it.allocate_tensors()
            self.vao = self.it.get_input_details()[0]
            self.ra = self.it.get_output_details()[0]
        else:
            import tensorflow as tf
            self.km = tf.keras.models.load_model(duong_dan)

    def du_doan(self, khung_bgr):
        anh = cv2.cvtColor(cv2.resize(khung_bgr, (KICH_THUOC, KICH_THUOC)), cv2.COLOR_BGR2RGB)
        x = np.expand_dims(anh.astype(np.float32), 0)   # Mô hình tự chuẩn hóa bên trong
        if self.la_tflite:
            self.it.set_tensor(self.vao["index"], x)
            self.it.invoke()
            return self.it.get_tensor(self.ra["index"])[0]
        return self.km.predict(x, verbose=0)[0]


def main(a):
    mo_hinh = MoHinh(a.model)
    trang_thai_esp = {"tt": "?"}

    def khi_ket_noi(client, userdata, flags, reason_code, properties):
        print(f"[MQTT] ket noi {a.broker}:{a.port} rc={reason_code}")
        client.subscribe(a.topic_status)

    def khi_nhan(client, userdata, msg):
        try:
            trang_thai_esp.update(json.loads(msg.payload.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            pass

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"nhom07-pc-{uuid.uuid4().hex[:6]}")
    client.on_connect = khi_ket_noi
    client.on_message = khi_nhan
    client.connect(a.broker, a.port, keepalive=30)
    client.loop_start()

    nguon = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(nguon)
    if not cap.isOpened():
        raise SystemExit(f"Khong mo duoc nguon anh: {a.source}")

    lich_su = deque(maxlen=a.k)          # K nhãn gần nhất để làm mượt
    nhan_on_dinh, tin_cay_on_dinh = "binh_thuong", 1.0
    xs = np.zeros(len(LOP))
    ms_suy_luan, so_khung, moc_gui = 0.0, 0, 0.0

    while True:
        ok, khung = cap.read()
        if not ok:
            if isinstance(nguon, str):    # Hết video thì phát lại từ đầu
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break
        so_khung += 1

        if so_khung % a.n == 0:
            t0 = time.perf_counter()
            xs = mo_hinh.du_doan(khung)
            ms_suy_luan = (time.perf_counter() - t0) * 1000
            i = int(np.argmax(xs))
            lich_su.append((LOP[i], float(xs[i])))
            # Chỉ đổi nhãn ổn định khi K dự đoán liên tiếp cùng một nhãn
            if len(lich_su) == a.k and len({n for n, _ in lich_su}) == 1:
                nhan_on_dinh = lich_su[-1][0]
                tin_cay_on_dinh = sum(c for _, c in lich_su) / a.k

        bay_gio = time.time()
        if bay_gio - moc_gui >= a.chu_ky:
            moc_gui = bay_gio
            ban_tin = json.dumps({"nhan": nhan_on_dinh,
                                  "do_tin_cay": round(tin_cay_on_dinh, 2),
                                  "ts": int(bay_gio)}, separators=(",", ":"))
            client.publish(a.topic, ban_tin, qos=0)
            print(f"[PUB] {time.strftime('%H:%M:%S')} {a.topic} {ban_tin}")

        # Vẽ nhãn và thông tin lên khung hình
        mau = MAU[nhan_on_dinh]
        cv2.rectangle(khung, (0, 0), (khung.shape[1], 90), (30, 30, 30), -1)
        cv2.putText(khung, f"{nhan_on_dinh}  {tin_cay_on_dinh:.2f}", (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, mau, 2)
        chi_tiet = "  ".join(f"{LOP[j]}={xs[j]:.2f}" for j in range(len(LOP)))
        cv2.putText(khung, f"{chi_tiet}  |  {ms_suy_luan:.0f} ms", (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1)
        cv2.putText(khung, f"ESP32: {trang_thai_esp.get('tt')}  nguon={trang_thai_esp.get('nguon', '-')}",
                    (10, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1)
        cv2.imshow("Nhom 07 - Nhan dien lua/khoi", khung)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Nhan dien lua/khoi va phat nhan qua MQTT")
    p.add_argument("--source", default="0", help="Chi so webcam hoac duong dan video")
    p.add_argument("--model", default="outputs/model_lua_khoi.tflite")
    p.add_argument("--broker", default="broker.hivemq.com")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="ptit/nhom07/fire")
    p.add_argument("--topic-status", dest="topic_status", default="ptit/nhom07/status")
    p.add_argument("--n", type=int, default=3, help="Suy luan moi N khung hinh")
    p.add_argument("--k", type=int, default=5, help="So du doan lien tiep de doi nhan")
    p.add_argument("--chu-ky", dest="chu_ky", type=float, default=1.0, help="Chu ky gui ban tin (s)")
    main(p.parse_args())
