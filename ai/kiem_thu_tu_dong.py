# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Chạy tự động các tình huống kiểm thử trên mô phỏng Wokwi.

Chương trình thao tác chuột lên cửa sổ Wokwi đang mở (Windows, Chrome, màn hình
1920x1080) để đổi nồng độ khí, nhiệt độ DHT22, nhấn nút; gửi bản tin lên chủ đề
nhãn AI; rồi đọc kết quả từ chủ đề trạng thái mà ESP32 gửi về. Mỗi bản tin trạng
thái được ghi vào CSV kèm mốc thời gian để làm minh chứng.

Tọa độ màn hình trong TOA_DO phụ thuộc bố cục cửa sổ Wokwi, phải đo lại nếu khác.
Tình huống 11 (ảnh dễ gây nhầm) cần mô hình đã huấn luyện nên không có ở đây.

Ví dụ:  python kiem_thu_tu_dong.py --lap 20 --ra ket_qua_kiem_thu
"""
import argparse
import csv
import ctypes
import json
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
# Giu man hinh sang va may khong ngu trong luc chay (khoa man hinh lam Chrome dung mo phong)
ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)

TOA_DO = {
    "cam_bien_khi": (1090, 470), "thanh_khi_y": 391,
    "khi_x": {"400": 1260, "1259": 1300, "11482": 1375, "bien_duoi": 1286, "bien_tren": 1300},
    "dht": (1190, 670), "thanh_nhiet_y": 335, "nhiet_x0": 1105, "nhiet_x1": 1262,   # -40..80 do C
    "nut_lua": (1267, 625), "nut_xac_nhan": (1272, 697), "dong_bang": (1888, 313),
}


# ---------------------------------------------------------------- Thao tác giao diện
def cua_so_chrome():
    ket_qua = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def duyet(h, _):
        buf = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, buf, 512)
        if u32.IsWindowVisible(h) and "Wokwi" in buf.value and "Chrome" in buf.value:
            ket_qua.append(h)
        return True
    u32.EnumWindows(proc(duyet), 0)
    return ket_qua[0] if ket_qua else None


HWND = None


def giu_chrome_truoc():
    """Đưa Chrome lên trước nếu cửa sổ khác chiếm (Chrome làm chậm tab bị che)."""
    if HWND and u32.GetForegroundWindow() != HWND:
        u32.keybd_event(0x12, 0, 0, 0)
        u32.keybd_event(0x12, 0, 2, 0)
        u32.SetForegroundWindow(HWND)
        time.sleep(0.3)


def nhan(x, y, giu=0.12, cho=0.4):
    giu_chrome_truoc()
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.08)
    u32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(giu)
    u32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(cho)


def mo_bang(vi_tri):
    # Dong bang dieu khien dang mo (neu co) roi mo bang cua linh kien can chinh
    nhan(*TOA_DO["dong_bang"], cho=0.3)
    nhan(*vi_tri, cho=0.6)


def dat_khi(muc):
    """Doi nong do khi; tra ve moc thoi gian ngay truoc khi nhan thanh truot."""
    mo_bang(TOA_DO["cam_bien_khi"])
    moc = time.time()
    nhan(TOA_DO["khi_x"][muc], TOA_DO["thanh_khi_y"])
    return moc


def dat_nhiet(do_c):
    x0, x1 = TOA_DO["nhiet_x0"], TOA_DO["nhiet_x1"]
    mo_bang(TOA_DO["dht"])
    moc = time.time()
    nhan(x0 + (do_c + 40) / 120 * (x1 - x0), TOA_DO["thanh_nhiet_y"])
    return moc


OUT_DIR = "."


def chup(ten):
    """Chup toan man hinh bang GDI va luu PNG (minh chung cho lan thu dau)."""
    import cv2
    import numpy as np
    g32 = ctypes.windll.gdi32
    w, h = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    hdc = u32.GetDC(0)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mdc, bmp)
    g32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    buf = ctypes.create_string_buffer(w * h * 4)
    hdr = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    g32.GetDIBits(mdc, bmp, 0, h, buf, hdr, 0)
    anh = np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, :3]
    with open(os.path.join(OUT_DIR, ten), "wb") as f:
        f.write(cv2.imencode(".png", anh)[1].tobytes())
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(0, hdc)


def bam_xac_nhan():
    nhan(*TOA_DO["nut_xac_nhan"], giu=0.35)


# ---------------------------------------------------------------- MQTT
class Kenh:
    def __init__(self, a):
        self.a = a
        self.khoa = threading.Lock()
        self.ds = []                       # (thoi_diem_pc, dict)
        self.f = open(os.path.join(a.ra, "nhat_ky_trang_thai.csv"), "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        self.w.writerow(["thoi_diem_pc", "tinh_huong", "lan", "payload"])
        self.tinh_huong, self.lan = "-", 0
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"nhom07-kt-{uuid.uuid4().hex[:6]}")
        self.c.on_connect = lambda c, u, f, rc, p: c.subscribe(a.topic_status)
        self.c.on_message = self._nhan
        self.c.connect(a.broker, a.port, keepalive=30)
        self.c.loop_start()

    def _nhan(self, c, u, msg):
        try:
            d = json.loads(msg.payload.decode("utf-8"))
        except ValueError:
            return
        t = time.time()
        with self.khoa:
            self.ds.append((t, d))
            self.w.writerow([f"{t:.3f}", self.tinh_huong, self.lan, msg.payload.decode("utf-8")])
            self.f.flush()

    def gui(self, payload):
        self.c.publish(self.a.topic, payload)

    def gui_nhan(self, nhan, tin_cay):
        self.gui(json.dumps({"nhan": nhan, "do_tin_cay": tin_cay, "ts": int(time.time())}, separators=(",", ":")))

    def moi_nhat(self):
        with self.khoa:
            return self.ds[-1][1] if self.ds else {}

    def tu(self, moc):
        with self.khoa:
            return [(t, d) for t, d in self.ds if t >= moc]

    def cho(self, dieu_kien, moc, han):
        """Chờ bản tin đầu tiên sau mốc thỏa điều kiện; trả về (độ trễ giây, bản tin) hoặc (None, None)."""
        het = moc + han * HE_SO
        while time.time() < het:
            for t, d in self.tu(moc):
                if dieu_kien(d):
                    return t - moc, d
            time.sleep(0.05)
        return None, None

    def cho_ban_tin_moi(self, han=8):
        moc = time.time()
        _, d = self.cho(lambda d: True, moc, han)
        return d


# Mo phong Wokwi chay cham hon thoi gian thuc (~40%), moi han cho tinh theo dong ho PC nhan HE_SO.
HE_SO = 3.0


def tt_la(*ten):
    return lambda d: d.get("tt") in ten


# ---------------------------------------------------------------- Đưa hệ về trạng thái gốc
def ve_binh_thuong(k):
    dat_khi("400")
    for _ in range(4):
        d = k.moi_nhat()
        if d.get("tt") == "BINH_THUONG":
            return True
        if d.get("tt") in ("KHOI_PHUC",):
            moc = time.time()
            bam_xac_nhan()
            if k.cho(tt_la("BINH_THUONG"), moc, 4)[0] is not None:
                return True
        else:
            k.cho(tt_la("KHOI_PHUC", "BINH_THUONG"), time.time(), 6)
    return k.moi_nhat().get("tt") == "BINH_THUONG"


# ---------------------------------------------------------------- Các tình huống
def th1(k, i):
    d = k.cho_ban_tin_moi()
    ok = bool(d) and d.get("tt") == "BINH_THUONG" and d.get("lua") == 0 and d.get("nguon") == "-"
    return ok, None, d


def th_khi(k, muc, ky_vong):
    moc = dat_khi(muc)
    tre, d = k.cho(tt_la("CANH_BAO", "CHUA_CHAY", "KHOI_PHUC"), moc, 4)
    ok = tre is not None and d.get("tt") == ky_vong
    dat_khi("400")
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    ve_binh_thuong(k)
    return ok, tre, d


def th2(k, i):
    return th_khi(k, "1259", "CANH_BAO")


def th3(k, i):
    return th_khi(k, "11482", "CHUA_CHAY")


def th4(k, i):
    moc = time.time()
    giu_chrome_truoc()
    x, y = TOA_DO["nut_lua"]
    u32.SetCursorPos(x, y)
    time.sleep(0.08)
    u32.mouse_event(2, 0, 0, 0, 0)
    tre, d = k.cho(tt_la("CHUA_CHAY", "CANH_BAO"), moc, 4)
    u32.mouse_event(4, 0, 0, 0, 0)
    ok = tre is not None and d.get("tt") == "CHUA_CHAY" and d.get("nguon") == "LUAT" and d.get("lua") == 1
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    ve_binh_thuong(k)
    return ok, tre, d


def th5(k, i):
    moc = dat_nhiet(45)               # tang ~17 do giua hai lan doc DHT22, chua toi 55 do
    tre, d = k.cho(tt_la("CHUA_CHAY", "CANH_BAO"), moc, 9)
    ok = tre is not None and d.get("tt") == "CHUA_CHAY" and d.get("t", 99) < 55
    if i == 0:
        time.sleep(1.5)
        chup("ts5.png")
    k.cho(tt_la("KHOI_PHUC"), time.time(), 8)
    dat_nhiet(28)
    time.sleep(4)
    ve_binh_thuong(k)
    return ok, tre, d


def th6(k, i):
    moc = time.time()
    k.gui_nhan("lua", 0.93)
    tre, d = k.cho(tt_la("CHUA_CHAY", "CANH_BAO"), moc, 4)
    ok = tre is not None and d.get("tt") == "CHUA_CHAY" and d.get("nguon") == "AI"
    k.gui_nhan("binh_thuong", 0.95)
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    ve_binh_thuong(k)
    return ok, tre, d


def th7(k, i):
    moc = time.time()
    for _ in range(4):                # dao động qua lại quanh ngưỡng cảnh báo
        dat_khi("bien_tren")
        time.sleep(1.2)
        dat_khi("bien_duoi")
        time.sleep(1.2)
    time.sleep(1)
    if i == 0:
        chup("ts7.png")
    chuyen = [d.get("tt") for _, d in k.tu(moc)]
    vao = sum(1 for a, b in zip(["BINH_THUONG"] + chuyen, chuyen) if a != b)
    ok = chuyen.count("KHOI_PHUC") == 0 and "CANH_BAO" in chuyen and vao == 1
    khoi = sorted({d.get("khoi") for _, d in k.tu(moc)})
    dat_khi("400")
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    ve_binh_thuong(k)
    return ok, None, {"so_lan_doi_trang_thai": vao, "adc_quan_sat": khoi}


def th8(k, i):
    for _ in range(3):
        k.gui_nhan("binh_thuong", 0.95)
        time.sleep(1)
    moc = time.time()
    _, dau = k.cho(lambda d: True, moc, 7)            # ban tin dau tien sau lan gui cuoi
    tre, d = k.cho(lambda d: d.get("ai") == 0, moc, 25)
    # Thoi gian tinh theo dong ho thiet bi (ms) vi mo phong chay cham hon thoi gian thuc
    tb = None if (dau is None or d is None) else (d["ms"] - dau["ms"]) / 1000
    ok = (dau is not None and dau.get("ai") == 1 and tb is not None and 10 <= tb <= 21
          and d.get("tt") == "BINH_THUONG")
    return ok, None if tb is None else tb, d


def th9(k, i):
    kieu = ["day khong phai JSON {{{", '{"nhan":"lua"}', '{"nhan":"chay_no","do_tin_cay":0.99}'][i % 3]
    truoc = k.moi_nhat().get("tt")
    moc = time.time()
    k.gui(kieu)
    time.sleep(1.5)
    d = k.cho_ban_tin_moi(7)          # thiết bị vẫn gửi trạng thái định kỳ: không treo
    doi = [x.get("tt") for _, x in k.tu(moc)]
    ok = bool(d) and all(t == truoc for t in doi) and d.get("muc_ai") == 0
    return ok, None, d


def th10(k, i):
    k.gui_nhan("binh_thuong", 0.95)
    time.sleep(0.8)
    moc = dat_khi("11482")
    tre, d = k.cho(tt_la("CHUA_CHAY", "CANH_BAO"), moc, 4)
    ok = tre is not None and d.get("tt") == "CHUA_CHAY" and d.get("nguon") == "LUAT"
    if i == 0:
        time.sleep(1.5)
        chup("ts10.png")
    dat_khi("400")
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    ve_binh_thuong(k)
    return ok, tre, d


def th12(k, i):
    moc = dat_khi("11482")
    tre0, d0 = k.cho(tt_la("CHUA_CHAY"), moc, 4)
    if tre0 is None:
        ve_binh_thuong(k)
        return False, None, {}
    bat_dau = moc + tre0
    tre, d = k.cho(tt_la("KHOI_PHUC"), bat_dau, 70)
    time.sleep(6 * HE_SO)             # nguy hiem van con: khong duoc bom lai
    if i == 0:
        chup("ts12.png")
    sau = [x.get("tt") for _, x in k.tu(bat_dau + (tre or 0) + 0.5)]
    # Thoi gian bom tinh theo dong ho thiet bi
    tg = None if d is None else (d["ms"] - d0["ms"]) / 1000
    ok = tg is not None and 59 <= tg <= 62 and "CHUA_CHAY" not in sau
    tre = tg
    dat_khi("400")
    time.sleep(1.5)
    ve_binh_thuong(k)
    return ok, tre, d


def th13(k, i):
    dat_khi("11482")
    k.cho(tt_la("CHUA_CHAY"), time.time(), 4)
    dat_khi("400")
    k.cho(tt_la("KHOI_PHUC"), time.time(), 4)
    moc = time.time()
    time.sleep(6 * HE_SO)             # khong tu ve binh thuong khi chua nhan nut
    tu_ve = any(d.get("tt") == "BINH_THUONG" for _, d in k.tu(moc))
    if i == 0:
        chup("ts13_truoc.png")
    moc2 = time.time()
    bam_xac_nhan()
    tre, d = k.cho(tt_la("BINH_THUONG"), moc2, 4)
    if i == 0:
        time.sleep(2)
        chup("ts13_sau.png")
    ok = not tu_ve and tre is not None
    return ok, tre, d


TINH_HUONG = {1: th1, 2: th2, 3: th3, 4: th4, 5: th5, 6: th6, 7: th7, 8: th8, 9: th9, 10: th10, 12: th12, 13: th13}


def main(a):
    global HWND, OUT_DIR
    os.makedirs(a.ra, exist_ok=True)
    OUT_DIR = a.ra
    HWND = cua_so_chrome()
    if not HWND:
        raise SystemExit("Khong thay cua so Chrome dang mo Wokwi")
    # Chrome tam dung mo phong khi tab bi che: giu cua so Wokwi o tren cung trong suot luot chay
    def giu_truoc_lien_tuc():
        while True:
            giu_chrome_truoc()
            time.sleep(2)
    threading.Thread(target=giu_truoc_lien_tuc, daemon=True).start()
    k = Kenh(a)
    k.cho_ban_tin_moi(10)
    dat_nhiet(28)
    time.sleep(4 * HE_SO)
    ve_binh_thuong(k)
    ket_qua = {}
    ds = [int(x) for x in a.tinh_huong.split(",")]
    for so in ds:
        k.tinh_huong = so
        dung, tre_ds, chi_tiet, gian_doan = 0, [], [], 0
        for i in range(a.lap):
            k.lan = i + 1
            while True:
                bat_dau_lan = time.time()
                ok, tre, d = TINH_HUONG[so](k, i)
                # Mo phong bi tam dung (khoa man hinh, tab bi an): broker phat LWT online=false.
                # Lan do khong phan anh firmware nen ghi nhan gian doan va chay lai.
                if not any(x.get("online") is False for _, x in k.tu(bat_dau_lan)) or gian_doan >= 10:
                    break
                gian_doan += 1
                print(f"TH{so} lan {i + 1}: GIAN DOAN mo phong, chay lai", flush=True)
                k.cho(lambda x: x.get("online") is True, time.time(), 200)
                ve_binh_thuong(k)
            dung += int(bool(ok))
            if tre is not None:
                tre_ds.append(round(tre * 1000))
            chi_tiet.append({"lan": i + 1, "dung": bool(ok), "tre_ms": None if tre is None else round(tre * 1000), "ban_tin": d})
            print(f"TH{so} lan {i + 1}: {'DUNG' if ok else 'SAI'} tre={tre}", flush=True)
        ket_qua[so] = {"dung": dung, "tong": a.lap, "tre_ms": tre_ds, "gian_doan": gian_doan, "chi_tiet": chi_tiet}
        with open(os.path.join(a.ra, "ket_qua.json"), "w", encoding="utf-8") as f:
            json.dump(ket_qua, f, ensure_ascii=False, indent=1)
        print(f"=== TH{so}: {dung}/{a.lap}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Kiem thu tu dong tren Wokwi - Nhom 07")
    p.add_argument("--broker", default="broker.hivemq.com")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="ptit/nhom07/fire")
    p.add_argument("--topic-status", dest="topic_status", default="ptit/nhom07/status")
    p.add_argument("--lap", type=int, default=20)
    p.add_argument("--tinh-huong", dest="tinh_huong", default="1,2,3,4,5,6,7,8,9,10,12,13")
    p.add_argument("--ra", default="ket_qua_kiem_thu")
    main(p.parse_args())
