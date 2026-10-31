# Nhom07-INT1461-Phong-chay-chua-chay

**Tên đề tài:** Mô phỏng hệ thống phòng cháy, chữa cháy bằng Wokwi, tích hợp mô hình AI nhận diện
lửa và khói để điều khiển hệ thống chữa cháy.

Học phần: Xây dựng các hệ thống nhúng (INT1461) - Học kỳ 1, năm học 2026 - 2027.
Giảng viên hướng dẫn: ThS. Hồ Nhựt Minh.

## Thành viên nhóm

| STT | Họ và tên | Mã sinh viên | Mã lớp | Phụ trách chính |
|---|---|---|---|---|
| 1 | Lê Trường Giang | K23DTCN475 | D23TXCN06-K | Mạch Wokwi, firmware cảm biến, máy trạng thái, chấp hành, hoàn thiện báo cáo |
| 2 | Đại Anh Dũng | K23DTCN268 | D23TXCN06-K | Tập ảnh, huấn luyện mô hình, chương trình Python phát nhãn |
| 3 | Nguyễn Văn Anh | K23DTCN473 | D23TXCN06-K | Kênh MQTT, quy tắc hợp nhất, tích hợp AI với backend/frontend, kiểm thử |

Dự án Wokwi (công khai): https://wokwi.com/projects/479188342847712257

> Hệ thống là mô hình học thuật, không phải thiết bị phòng cháy chữa cháy đạt chuẩn và
> không được dùng thay thế thiết bị chuyên dụng.

## 1. Kiến trúc hai nhánh

```
[Webcam/Video] -> PC: detect_publish.py (MobileNetV2) --MQTT ptit/nhom07/fire-->  ESP32 (Wokwi)
                                                        <--MQTT ptit/nhom07/status-- (trạng thái)
ESP32: MQ-2 + cảm biến lửa + DHT22 -> lớp luật cục bộ -> hợp nhất (AI chỉ nâng) -> máy 4 trạng thái
       -> relay bơm, relay van, còi, đèn đỏ/xanh, LCD 16x2; nút xác nhận
```

Wokwi không có đầu vào camera nên mô hình ảnh chạy trên PC và gửi nhãn qua MQTT; ESP32 ảo
chủ động đăng ký chủ đề (mô phỏng chỉ mở được kết nối đi ra).

## 2. Cấu trúc thư mục

```
firmware/
  sketch.ino        Chương trình ESP32 (Arduino)
  diagram.json      Sơ đồ mạch Wokwi
  libraries.txt     Danh sách thư viện cho Wokwi
ai/
  extract_frames.py Tách khung hình từ video tự quay
  split_dataset.py  Chia train/val/test THEO NGUỒN VIDEO
  train_model.py    Huấn luyện MobileNetV2 + xuất .keras/.tflite, ma trận nhầm lẫn
  train_colab.ipynb Notebook chạy trên Google Colab
  detect_publish.py Đọc webcam/video, suy luận, phát nhãn qua MQTT
  mqtt_test_client.py Khách MQTT kiểm thử (bản tin hỏng, đo trễ, nghe trạng thái)
  requirements.txt
  dataset/README.md Mô tả nguồn và thống kê tập dữ liệu
web/
  backend/app.py    FastAPI: cầu nối MQTT, chạy mô hình AI (tùy chọn), SQLite, REST + WebSocket
  frontend/         Bảng điều khiển (index.html, app.js, style.css)
  requirements.txt
```

## 3. Danh mục linh kiện (thiết bị mô phỏng trên Wokwi)

| STT | Linh kiện | Mã phần tử Wokwi | Số lượng | Vai trò |
|---|---|---|---|---|
| 1 | ESP32 DevKit V1 | `wokwi-esp32-devkit-v1` | 1 | Vi điều khiển trung tâm, Wi-Fi + MQTT |
| 2 | Cảm biến khí/khói MQ-2 | `wokwi-gas-sensor` | 1 | Đo nồng độ khói (ADC) |
| 3 | Cảm biến lửa | `wokwi-flame-sensor` | 1 | Phát hiện ngọn lửa (DOUT/AOUT) |
| 4 | Cảm biến nhiệt độ, độ ẩm DHT22 | `wokwi-dht22` | 1 | Nhiệt độ tuyệt đối và tốc độ tăng nhiệt |
| 5 | Module relay | `wokwi-relay-module` | 2 | Bơm chữa cháy, van/quạt hút |
| 6 | Còi chip | `wokwi-buzzer` | 1 | Báo động âm thanh |
| 7 | LED đỏ (BÁO ĐỘNG), LED xanh (BÌNH THƯỜNG) + điện trở 220 Ω | `wokwi-led`, `wokwi-resistor` | 2 + 2 | Báo trạng thái |
| 8 | LED xanh dương (BƠM), LED vàng (VAN) + điện trở 220 Ω | `wokwi-led`, `wokwi-resistor` | 2 + 2 | Tải giả nối sau tiếp điểm NO của hai relay, sáng khi relay đóng |
| 9 | Nút nhấn | `wokwi-pushbutton` | 2 | Nút vàng XÁC NHẬN; nút đỏ MÔ PHỎNG LỬA |
| 10 | LCD 16x2 giao tiếp I2C (0x27) | `wokwi-lcd1602` | 1 | Hiển thị số liệu và trạng thái |
| 11 | Máy tính chạy Python + webcam/video | (ngoài Wokwi) | 1 | Nhánh AI nhận diện lửa/khói, bảng điều khiển web |

Sơ đồ nối dây đầy đủ nằm trong `firmware/diagram.json`.

## 4. Phần mềm và thư viện (cách nạp chương trình)

| Thành phần | Phiên bản đã dùng |
|---|---|
| Wokwi (wokwi.com), board `wokwi-esp32-devkit-v1` | bản web tại thời điểm làm đồ án |
| Arduino-ESP32 core (Wokwi dùng mặc định) | 3.x (ghi lại số phiên bản in ra khi biên dịch) |
| DHT sensor library (Adafruit) | 1.4.x |
| Adafruit Unified Sensor | 1.1.x |
| LiquidCrystal I2C (Frank de Brabander) | 1.1.2 |
| PubSubClient (Nick O'Leary) | 2.8 |
| ArduinoJson (Benoit Blanchon) | 7.x - mã dùng `JsonDocument` (API v7) |
| Python | 3.10 - 3.11 |
| TensorFlow / OpenCV / paho-mqtt | 2.15 / 4.8+ / 2.x |

## 5. Sơ đồ chân (ESP32 DevKit V1)

| Linh kiện | Chân linh kiện | Chân ESP32 | Ghi chú |
|---|---|---|---|
| MQ-2 (gas sensor) | AOUT | GPIO35 (D35) | ADC1, chỉ vào. Mạch thật: chia áp 10k/15k |
| MQ-2 | VCC / GND | VIN (5 V) / GND | Sợi đốt cần 5 V |
| Cảm biến lửa | DOUT | GPIO18 (D18) | INPUT_PULLUP |
| Cảm biến lửa | AOUT | GPIO39 (VN) | ADC1, chỉ ghi nhật ký |
| DHT22 | SDA (DATA) | GPIO4 (D4) | Đọc mỗi 3 s |
| Relay bơm | IN | GPIO26 (D26) | Wokwi kích mức cao |
| Relay van/quạt hút | IN | GPIO25 (D25) | |
| Còi | + | GPIO27 (D27) | tone() 2 kHz |
| LED đỏ / LED xanh | A (qua 220 Ω) | GPIO14 / GPIO13 | |
| Nút xác nhận | 1 chân | GPIO19 (D19) | INPUT_PULLUP, chân kia xuống GND |
| Nút mô phỏng lửa (chỉ Wokwi) | 1 chân | GPIO23 (D23) | Nhấn = có lửa (wokwi-flame-sensor không điều khiển được) |
| LCD 16x2 I2C (0x27) | SDA / SCL | GPIO21 / GPIO22 | |

Mọi cảm biến analog nằm trên ADC1 vì ADC2 không đọc được khi Wi-Fi bật.

## 6. Nạp và chạy mô phỏng trên Wokwi

1. Mở https://wokwi.com, tạo dự án **ESP32**, đặt tên `Nhom07_PhongChayChuaChay`.
2. Dán nội dung `firmware/sketch.ino` vào `sketch.ino`, `firmware/diagram.json` vào `diagram.json`.
3. Tạo tệp `libraries.txt` (tab Library Manager) với nội dung `firmware/libraries.txt`.
4. Bấm **Start Simulation**. Serial Monitor in dòng tiêu đề CSV và mỗi giây một dòng số liệu.
5. 20 giây đầu LCD hiện `LAM NONG MQ2` (bỏ qua ngưỡng khói; lửa và nhiệt vẫn được xét).
6. Thử: bấm vào cảm biến khí để kéo thanh GAS (PPM); giữ nút đỏ MÔ PHỎNG LỬA; đổi nhiệt độ DHT22; nhấn nút vàng XÁC NHẬN.
7. Để tab Wokwi luôn hiển thị khi kiểm thử: Chrome làm chậm mô phỏng ở tab ẩn.

Ngưỡng khói đã hiệu chuẩn trên Wokwi: 400 ppm (mặc định) -> ADC 3628, 1259 ppm -> 3790 (CẢNH BÁO),
11482 ppm -> 3966 (CHỮA CHÁY). Ngưỡng 3750 / 3900, độ trễ 40. Mạch thật phải hiệu chuẩn lại.

## 7. Chạy nhánh AI trên máy tính

```bash
cd ai
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# Chuẩn bị dữ liệu và huấn luyện (hoặc dùng train_colab.ipynb trên Colab)
python extract_frames.py --video raw_video/nen_01.mp4 --lop lua --out data/raw --moi 10
python split_dataset.py --raw data/raw --out data/split
python train_model.py --data data/split --out outputs

# Chạy suy luận và phát nhãn (Wokwi phải đang chạy mô phỏng)
python detect_publish.py --source 0 --model outputs/model_lua_khoi.tflite

# Kiểm thử kênh MQTT
python mqtt_test_client.py nghe
python mqtt_test_client.py hong --kieu khong_json
```

Bản tin AI -> ESP32 (chủ đề `ptit/nhom07/fire`):
`{"nhan":"lua","do_tin_cay":0.93,"ts":1730000000}`
Bản tin ESP32 -> PC (chủ đề `ptit/nhom07/status`, retained, có LWT `{"online":false}`):
`{"online":true,"tt":"CHUA_CHAY","khoi":2950,"lua":0,"t":31.2,"muc_ai":2,"ai":1,"nguon":"AI","ms":84213}`

Broker mặc định `broker.hivemq.com:1883` (công cộng, không cần tài khoản). Phương án dự
phòng: `test.mosquitto.org:1883`, đổi ở `MQTT_BROKER` trong `sketch.ino` và tham số
`--broker` của các chương trình Python. Không đưa mật khẩu Wi-Fi thật, khóa API hay token
vào mã nguồn.

## 8. Bảng điều khiển web (tích hợp AI với backend và frontend)

```bash
cd web
pip install -r requirements.txt
# Chế độ giám sát (detect_publish.py chạy riêng):
python backend/app.py
# Backend tự chạy mô hình AI từ webcam:
python backend/app.py --model ../ai/outputs/model_lua_khoi.tflite --source 0
```

Mở http://localhost:8000. Dùng `--host 0.0.0.0` nếu muốn máy khác trong mạng LAN xem.

## 9. Chạy thử và kết quả mong đợi

| Thao tác thử | Kết quả mong đợi |
|---|---|
| Khởi động mô phỏng, không tác động | LCD dòng 1 `NHOM 07 - PCCC`, sau đó đếm `LAM NONG MQ2` 20 s rồi `BINHTHUONG`; LED xanh sáng; Serial in `# MQTT,da ket noi broker.hivemq.com,...` |
| Kéo GAS lên khoảng 1259 ppm (ADC ≈ 3790) | Chuyển `CANH BAO`: LED đỏ, còi kêu, bơm và van chưa bật |
| Kéo GAS lên khoảng 11482 ppm (ADC ≈ 3966), giữ nút MÔ PHỎNG LỬA, hoặc nhiệt độ DHT22 ≥ 55 °C / tăng ≥ 2 °C/s | Chuyển `CHUA CHAY`: relay bơm và relay van đóng (LED BƠM, LED VAN sáng), còi kêu, LED đỏ sáng |
| Gửi nhãn AI `lua`/`khoi` với độ tin cậy ≥ 0,80 qua `ptit/nhom07/fire` | Mức báo động được nâng, LCD hiện nguồn kích hoạt `AI`; nhãn AI không bao giờ hạ mức của luật cục bộ |
| Gửi bản tin hỏng (`mqtt_test_client.py hong`) hoặc ngừng gửi nhãn quá 15 s | Bản tin bị bỏ qua; LCD hiện `MATAI`, luật cục bộ vẫn hoạt động bình thường |
| Đưa cảm biến về an toàn | Chuyển `KHOI PHUC`: bơm tắt, LED đỏ giữ sáng cho tới khi nhấn nút XÁC NHẬN thì về `BINHTHUONG` |
| Duy trì nguy hiểm quá 60 s | Bơm tự cắt, chuyển `KHOI PHUC`, còi gọi người vận hành; chỉ bơm lại khi nhấn XÁC NHẬN |
| Mở http://localhost:8000 (mục 8) | Bảng điều khiển hiện trạng thái thiết bị theo thời gian thực qua chủ đề `ptit/nhom07/status` |

Kết quả chi tiết 13 tình huống kiểm thử (mỗi tình huống 20 lần) có trong Bảng 5.2 của báo cáo.

## 10. Nguồn tham khảo mã

- Khung chương trình trong tài liệu "Hướng dẫn thực hiện đồ án INT1461 - Nhóm 7", Phần F
  (ThS. Hồ Nhựt Minh, 2026) - nhóm đã viết thân các hàm còn thiếu và bổ sung như ghi ở đầu
  `sketch.ino`.
- bugsNburgers, *IOT-Fire-Alarm-System*, GitHub - chỉ tham khảo kiến trúc, không sao chép mã.
