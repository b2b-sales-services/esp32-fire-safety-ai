# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Backend tích hợp mô hình AI với bảng điều khiển web.

Chức năng:
    - Kết nối broker MQTT, nghe trạng thái ESP32 (ptit/nhom07/status) và nhãn AI
      (ptit/nhom07/fire), lưu lịch sử sự kiện vào SQLite.
    - (Tùy chọn) chạy luôn mô hình AI: đọc webcam/video, suy luận, làm mượt,
      phát nhãn lên MQTT và cung cấp luồng video có vẽ nhãn (MJPEG) cho frontend.
    - Cung cấp REST API, WebSocket đẩy dữ liệu thời gian thực, và phục vụ frontend.

Hai chế độ chạy:
    python app.py --model ../../ai/outputs/model_lua_khoi.tflite --source 0   # backend chạy AI
    python app.py                                                             # chỉ giám sát
                                                     # (khi đó chạy ai/detect_publish.py riêng)
Mở trình duyệt: http://localhost:8000
"""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections import deque

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(THU_MUC, "..", "frontend")
sys.path.insert(0, os.path.join(THU_MUC, "..", "..", "ai"))   # dùng lại lớp MoHinh

BAN_TIN_HONG = {
    "khong_json": "day khong phai JSON {{{",
    "thieu_truong": '{"nhan":"lua"}',
    "nhan_la": '{"nhan":"chay_no","do_tin_cay":0.99}',
}


# ---------------------------------------------------------------- Lưu trữ
class KhoSuKien:
    """Lưu sự kiện vào SQLite; mỗi sự kiện gồm thời điểm, loại và nội dung JSON."""

    def __init__(self, duong_dan):
        self.khoa = threading.Lock()
        self.db = sqlite3.connect(duong_dan, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS su_kien ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, loai TEXT, noi_dung TEXT)")
        self.db.commit()

    def them(self, loai, noi_dung):
        with self.khoa:
            self.db.execute("INSERT INTO su_kien (ts, loai, noi_dung) VALUES (?, ?, ?)",
                            (time.time(), loai, json.dumps(noi_dung, ensure_ascii=False)))
            self.db.commit()

    def lay(self, gioi_han=100):
        with self.khoa:
            hang = self.db.execute("SELECT ts, loai, noi_dung FROM su_kien ORDER BY id DESC LIMIT ?",
                                   (gioi_han,)).fetchall()
        return [{"ts": ts, "loai": loai, "noi_dung": json.loads(nd)} for ts, loai, nd in hang]


# ---------------------------------------------------------------- Trạng thái dùng chung
class TrangThaiChung:
    def __init__(self):
        self.khoa = threading.Lock()
        self.thiet_bi = {}          # bản tin status gần nhất của ESP32
        self.moc_thiet_bi = 0.0
        self.ai = {}                # bản tin nhãn AI gần nhất trên broker
        self.moc_ai = 0.0
        self.mqtt_ket_noi = False
        self.ai_noi_bo = False      # backend có tự chạy mô hình không
        self.ms_suy_luan = 0.0
        self.khung_jpeg = None      # khung hình đã vẽ nhãn (MJPEG)

    def anh_chup(self):
        with self.khoa:
            bay_gio = time.time()
            return {
                "thiet_bi": self.thiet_bi,
                "giay_tu_status": round(bay_gio - self.moc_thiet_bi, 1) if self.moc_thiet_bi else None,
                "ai": self.ai,
                "giay_tu_ai": round(bay_gio - self.moc_ai, 1) if self.moc_ai else None,
                "mqtt_ket_noi": self.mqtt_ket_noi,
                "ai_noi_bo": self.ai_noi_bo,
                "ms_suy_luan": round(self.ms_suy_luan, 1),
            }


# ---------------------------------------------------------------- MQTT
class CauNoiMQTT:
    def __init__(self, a, tt, kho, khi_doi):
        self.a, self.tt, self.kho, self.khi_doi = a, tt, kho, khi_doi
        self.tt_truoc = None
        self.nhan_truoc = None
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"nhom07-backend-{uuid.uuid4().hex[:6]}")
        self.c.on_connect = self._ket_noi
        self.c.on_disconnect = self._mat_ket_noi
        self.c.on_message = self._nhan

    def bat_dau(self):
        self.c.connect_async(self.a.broker, self.a.port, keepalive=30)
        self.c.loop_start()

    def _ket_noi(self, client, userdata, flags, reason_code, properties):
        self.tt.mqtt_ket_noi = not reason_code.is_failure
        client.subscribe([(self.a.topic_status, 0), (self.a.topic, 0)])
        self.kho.them("he_thong", {"mqtt": "da ket noi", "broker": self.a.broker})
        self.khi_doi()

    def _mat_ket_noi(self, client, userdata, flags, reason_code, properties):
        self.tt.mqtt_ket_noi = False
        self.khi_doi()

    def _nhan(self, client, userdata, msg):
        try:
            du_lieu = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            du_lieu = None
        if msg.topic == self.a.topic_status and isinstance(du_lieu, dict):
            with self.tt.khoa:
                self.tt.thiet_bi = du_lieu
                self.tt.moc_thiet_bi = time.time()
            # Chỉ ghi lịch sử khi trạng thái hoặc trạng thái online thay đổi
            khoa_tt = (du_lieu.get("tt"), du_lieu.get("online"))
            if khoa_tt != self.tt_truoc:
                self.tt_truoc = khoa_tt
                self.kho.them("trang_thai", du_lieu)
        elif msg.topic == self.a.topic:
            # Cùng tiêu chí hợp lệ với ESP32: đủ trường, nhãn thuộc 3 lớp, độ tin cậy trong [0, 1]
            hop_le = (isinstance(du_lieu, dict)
                      and du_lieu.get("nhan") in ("lua", "khoi", "binh_thuong")
                      and isinstance(du_lieu.get("do_tin_cay"), (int, float))
                      and 0 <= du_lieu["do_tin_cay"] <= 1)
            if hop_le:
                with self.tt.khoa:
                    self.tt.ai = du_lieu
                    self.tt.moc_ai = time.time()
                if du_lieu.get("nhan") != self.nhan_truoc:
                    self.nhan_truoc = du_lieu.get("nhan")
                    self.kho.them("nhan_ai", du_lieu)
            else:
                self.kho.them("ban_tin_hong", {"payload": msg.payload.decode("utf-8", "replace")[:120]})
        self.khi_doi()

    def gui(self, payload):
        self.c.publish(self.a.topic, payload, qos=0)


# ---------------------------------------------------------------- Nhánh AI chạy trong backend
def vong_ai(a, tt, cau_noi):
    """Đọc camera, suy luận mỗi N khung, đổi nhãn khi K dự đoán liên tiếp trùng nhau,
    phát bản tin mỗi chu kỳ và cập nhật khung hình JPEG cho luồng video."""
    import cv2
    import numpy as np
    from detect_publish import LOP, MAU, MoHinh

    mo_hinh = MoHinh(a.model)
    nguon = int(a.source) if str(a.source).isdigit() else a.source
    cap = cv2.VideoCapture(nguon)
    if not cap.isOpened():
        print(f"[AI] khong mo duoc nguon anh {a.source}")
        return
    tt.ai_noi_bo = True
    lich_su = deque(maxlen=a.k)
    nhan, tin_cay = "binh_thuong", 1.0
    so_khung, moc_gui = 0, 0.0
    while True:
        ok, khung = cap.read()
        if not ok:
            if isinstance(nguon, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            time.sleep(0.5)
            continue
        so_khung += 1
        if so_khung % a.n == 0:
            t0 = time.perf_counter()
            xs = mo_hinh.du_doan(khung)
            tt.ms_suy_luan = (time.perf_counter() - t0) * 1000
            i = int(np.argmax(xs))
            lich_su.append((LOP[i], float(xs[i])))
            if len(lich_su) == a.k and len({n for n, _ in lich_su}) == 1:
                nhan = lich_su[-1][0]
                tin_cay = sum(c for _, c in lich_su) / a.k
        if time.time() - moc_gui >= a.chu_ky:
            moc_gui = time.time()
            cau_noi.gui(json.dumps({"nhan": nhan, "do_tin_cay": round(tin_cay, 2), "ts": int(moc_gui)},
                                   separators=(",", ":")))
        cv2.rectangle(khung, (0, 0), (khung.shape[1], 40), (30, 30, 30), -1)
        cv2.putText(khung, f"{nhan} {tin_cay:.2f}  {tt.ms_suy_luan:.0f} ms", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, MAU[nhan], 2)
        ok, jpg = cv2.imencode(".jpg", khung, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            tt.khung_jpeg = jpg.tobytes()


# ---------------------------------------------------------------- Ứng dụng web
def tao_app(a):
    tt = TrangThaiChung()
    kho = KhoSuKien(a.db)
    app = FastAPI(title="Nhom 07 - Bang dieu khien PCCC")
    ket_noi_ws = set()
    vong_lap = {"loop": None}

    def khi_doi():
        # Gọi từ luồng MQTT: đẩy trạng thái mới tới mọi trình duyệt đang mở
        loop = vong_lap["loop"]
        if loop and ket_noi_ws:
            asyncio.run_coroutine_threadsafe(phat_ws(), loop)

    async def phat_ws():
        du_lieu = json.dumps(tt.anh_chup(), ensure_ascii=False)
        for ws in list(ket_noi_ws):
            try:
                await ws.send_text(du_lieu)
            except Exception:
                ket_noi_ws.discard(ws)

    cau_noi = CauNoiMQTT(a, tt, kho, khi_doi)

    @app.on_event("startup")
    async def khoi_dong():
        vong_lap["loop"] = asyncio.get_running_loop()
        cau_noi.bat_dau()
        if a.model:
            threading.Thread(target=vong_ai, args=(a, tt, cau_noi), daemon=True).start()

        async def nhip():   # cập nhật đồng hồ "giây kể từ bản tin" mỗi giây
            while True:
                await asyncio.sleep(1)
                if ket_noi_ws:
                    await phat_ws()
        asyncio.create_task(nhip())

    @app.get("/api/trang-thai")
    def api_trang_thai():
        return tt.anh_chup()

    @app.get("/api/su-kien")
    def api_su_kien(gioi_han: int = 100):
        return kho.lay(min(gioi_han, 500))

    @app.post("/api/kiem-thu/{kieu}")
    def api_kiem_thu(kieu: str):
        # Chỉ gửi bản tin SAI định dạng để kiểm thử tình huống 9, không gửi nhãn giả
        if kieu not in BAN_TIN_HONG:
            return JSONResponse({"loi": "kieu khong hop le"}, status_code=400)
        cau_noi.gui(BAN_TIN_HONG[kieu])
        kho.them("kiem_thu", {"kieu": kieu})
        return {"da_gui": BAN_TIN_HONG[kieu]}

    @app.get("/api/video")
    async def api_video():
        async def luong():
            while True:
                if tt.khung_jpeg:
                    yield b"--khung\r\nContent-Type: image/jpeg\r\n\r\n" + tt.khung_jpeg + b"\r\n"
                await asyncio.sleep(0.1)
        return StreamingResponse(luong(), media_type="multipart/x-mixed-replace; boundary=khung")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        ket_noi_ws.add(ws)
        await ws.send_text(json.dumps(tt.anh_chup(), ensure_ascii=False))
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ket_noi_ws.discard(ws)

    @app.get("/")
    def trang_chu():
        return FileResponse(os.path.join(FRONTEND, "index.html"))

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    return app


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backend bang dieu khien PCCC - Nhom 07")
    p.add_argument("--broker", default="broker.hivemq.com")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="ptit/nhom07/fire")
    p.add_argument("--topic-status", dest="topic_status", default="ptit/nhom07/status")
    p.add_argument("--model", default=None, help="Duong dan .tflite/.keras; bo trong = chi giam sat")
    p.add_argument("--source", default="0", help="Chi so webcam hoac duong dan video")
    p.add_argument("--n", type=int, default=3, help="Suy luan moi N khung hinh")
    p.add_argument("--k", type=int, default=5, help="So du doan lien tiep de doi nhan")
    p.add_argument("--chu-ky", dest="chu_ky", type=float, default=1.0)
    p.add_argument("--db", default=os.path.join(THU_MUC, "su_kien.db"))
    p.add_argument("--http-port", dest="http_port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 de may khac trong mang LAN xem duoc")
    a = p.parse_args()
    uvicorn.run(tao_app(a), host=a.host, port=a.http_port)
