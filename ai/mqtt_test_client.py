# -*- coding: utf-8 -*-
"""
Nhóm 07 - INT1461 - Chương trình khách MQTT dùng cho KIỂM THỬ kênh truyền.

Công cụ này KHÔNG thay thế mô hình AI. Nó chỉ dùng để:
    - kiểm chứng kênh MQTT hai chiều (Bước 6): gửi một bản tin và in mọi bản tin
      trạng thái ESP32 gửi về;
    - tạo bản tin sai định dạng cho tình huống kiểm thử số 9;
    - đo độ trễ từ lúc gửi bản tin tới lúc ESP32 báo đổi trạng thái.

Ví dụ:
    python mqtt_test_client.py nghe                      # chỉ in trạng thái ESP32
    python mqtt_test_client.py gui --nhan lua --tin-cay 0.93
    python mqtt_test_client.py hong --kieu khong_json    # tình huống 9
    python mqtt_test_client.py hong --kieu thieu_truong
    python mqtt_test_client.py hong --kieu nhan_la
"""
import argparse
import json
import time
import uuid

import paho.mqtt.client as mqtt

BAN_TIN_HONG = {
    "khong_json": "day khong phai JSON {{{",
    "thieu_truong": '{"nhan":"lua"}',
    "nhan_la": '{"nhan":"chay_no","do_tin_cay":0.99}',
    "tin_cay_sai": '{"nhan":"lua","do_tin_cay":7.5}',
    "rong": "",
}


def tao_client(a, in_trang_thai=True):
    moc = {"gui": None}

    def khi_ket_noi(client, userdata, flags, reason_code, properties):
        print(f"[MQTT] ket noi {a.broker}:{a.port} rc={reason_code}")
        client.subscribe(a.topic_status)

    def khi_nhan(client, userdata, msg):
        if not in_trang_thai:
            return
        tre = ""
        if moc["gui"] is not None:
            tre = f"  (sau {1000 * (time.time() - moc['gui']):.0f} ms ke tu luc gui)"
        print(f"[SUB] {time.strftime('%H:%M:%S')} {msg.topic} {msg.payload.decode(errors='replace')}{tre}")

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"nhom07-test-{uuid.uuid4().hex[:6]}")
    c.on_connect = khi_ket_noi
    c.on_message = khi_nhan
    c.connect(a.broker, a.port, keepalive=30)
    c.loop_start()
    time.sleep(1.0)
    return c, moc


def main(a):
    c, moc = tao_client(a)
    try:
        if a.lenh == "gui":
            ban_tin = json.dumps({"nhan": a.nhan, "do_tin_cay": a.tin_cay, "ts": int(time.time())},
                                 separators=(",", ":"))
            for _ in range(a.lap):
                moc["gui"] = time.time()
                c.publish(a.topic, ban_tin)
                print(f"[PUB] {a.topic} {ban_tin}")
                time.sleep(a.chu_ky)
        elif a.lenh == "hong":
            moc["gui"] = time.time()
            c.publish(a.topic, BAN_TIN_HONG[a.kieu])
            print(f"[PUB] {a.topic} {BAN_TIN_HONG[a.kieu]!r}")
        print("Dang nghe chu de trang thai, Ctrl+C de thoat...")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        c.loop_stop()
        c.disconnect()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Khach MQTT kiem thu - Nhom 07")
    p.add_argument("lenh", choices=["nghe", "gui", "hong"])
    p.add_argument("--broker", default="broker.hivemq.com")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="ptit/nhom07/fire")
    p.add_argument("--topic-status", dest="topic_status", default="ptit/nhom07/status")
    p.add_argument("--nhan", default="binh_thuong", choices=["binh_thuong", "khoi", "lua"])
    p.add_argument("--tin-cay", dest="tin_cay", type=float, default=0.9)
    p.add_argument("--lap", type=int, default=1, help="So lan gui")
    p.add_argument("--chu-ky", dest="chu_ky", type=float, default=1.0)
    p.add_argument("--kieu", default="khong_json", choices=list(BAN_TIN_HONG))
    main(p.parse_args())
