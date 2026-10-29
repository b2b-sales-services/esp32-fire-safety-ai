// =====================================================================
// Nhom 07 - INT1461 - He thong phong chay chua chay mo phong tren Wokwi
// Board: ESP32 DevKit V1 (Wokwi: wokwi-esp32-devkit-v1)
// Nguyen tac an toan: lop luat cuc bo LUON chay, khong phu thuoc mang;
// nhan tu AI (qua MQTT) chi duoc NANG muc bao dong, khong duoc HA.
// ---------------------------------------------------------------------
// Nguon: khung chuong trinh trong "Huong dan thuc hien do an INT1461 -
//        Nhom 7" (ThS. Ho Nhut Minh, 2026), Phan F.
// Tham khao kien truc: bugsNburgers, "IOT-Fire-Alarm-System", GitHub.
// Muc do su dung: sua doi va viet bo sung.
// Noi dung nhom da sua/bo sung so voi khung:
//   - viet than ham ketNoiLaiMQTT() (khong chan, lui thoi gian, gioi han
//     so lan thu, dang ky lai chu de), hienThi(), ghiNhatKy(), guiTrangThai();
//   - do tre (hysteresis) cho nguong khoi; chong doi nut nhan;
//   - giai doan lam nong chi bo qua MQ-2, lua va nhiet van duoc xet;
//   - co hetGioChuaChay: bom khong tu chay lai sau khi het T_MAX;
//   - dem loi DHT22; kiem tra hop le ban tin JSON; LWT trang thai online.
// =====================================================================
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

// ----- Cau hinh ket noi -----
#define WIFI_SSID      "Wokwi-GUEST"          // Mang ao cua Wokwi; mach that: "<ten_wifi>"
#define WIFI_PASSWORD  ""                     // Wokwi-GUEST khong co mat khau; mach that: "<mat_khau_cua_ban>"
#define WIFI_KENH      6                      // Kenh 6 giup Wokwi ket noi nhanh hon
#define MQTT_BROKER    "broker.hivemq.com"    // Broker cong cong, khong can tai khoan
#define MQTT_PORT      1883
#define MQTT_TOPIC_AI  "ptit/nhom07/fire"     // Chu de nhan nhan tu nhanh AI
#define MQTT_TOPIC_TT  "ptit/nhom07/status"   // Chu de gui trang thai thiet bi

// ----- Khai bao chan (doi duoc, sua tai day) -----
#define PIN_MQ2        35   // ADC1, chi vao - dau ra analog cam bien khoi
#define PIN_FLAME_DO   18   // Dau ra so cam bien lua
#define PIN_FLAME_AO   39   // ADC1 (VN), chi vao - cuong do lua, chi de ghi nhat ky
#define PIN_NUT_LUA    23   // Nut mo phong lua (chi tren Wokwi: linh kien flame sensor
                            // khong co dieu khien tuong tac), nhan = co lua
#define PIN_DHT         4   // Du lieu DHT22
#define PIN_RELAY_BOM  26   // Relay bom chua chay
#define PIN_RELAY_VAN  25   // Relay van / quat hut khoi
#define PIN_BUZZER     27   // Coi bao dong
#define PIN_LED_DO     14   // Den bao dong
#define PIN_LED_XANH   13   // Den binh thuong
#define PIN_BTN_RESET  19   // Nut xac nhan / dat lai
#define PIN_SDA        21   // I2C LCD
#define PIN_SCL        22

// ----- Tham so van hanh -----
const uint32_t CHU_KY_MS         = 1000;   // Chu ky lay mau MQ-2 va cam bien lua
const uint32_t CHU_KY_DHT_MS     = 3000;   // Chu ky doc DHT22 (>= 2 s theo datasheet)
const uint32_t CHU_KY_GUI_TT_MS  = 5000;   // Chu ky gui trang thai len broker
const uint32_t T_MAX_CHUA_CHAY   = 60000;  // Thoi gian chua chay toi da mot luot
const uint32_t T_HET_HAN_AI      = 15000;  // Qua thoi gian nay coi nhu mat nguon AI
const uint32_t T_LAM_NONG_MQ2    = 20000;  // Bo qua nguong khoi khi MQ-2 chua on dinh
const uint32_t T_CHONG_DOI_MS    = 50;     // Thoi gian chong doi nut nhan
const uint32_t T_CHO_MQTT_DAU    = 2000;   // Khoang cho ket noi lai ban dau
const uint32_t T_CHO_MQTT_MAX    = 30000;  // Khoang cho ket noi lai toi da
const uint32_t T_NGHI_MQTT       = 60000;  // Nghi sau khi het so lan thu
const uint8_t  SO_LAN_THU_MQTT   = 5;      // So lan thu lien tiep truoc khi nghi
// Nguong hieu chuan tren Wokwi (Buoc 7): 400 ppm (mac dinh) -> ADC 3628,
// 2291 ppm -> 3853, >= 22909 ppm -> ~4000 (bao hoa). Mach that phai hieu chuan lai.
const int   NGUONG_KHOI_CANH_BAO  = 3750;  // ~1000 ppm
const int   NGUONG_KHOI_NGUY_HIEM = 3900;  // ~5000 ppm
const int   DO_TRE_KHOI           = 40;    // Muc khoi chi ha khi ADC xuong duoi (nguong - 40)
const float NGUONG_NHIET_C        = 55.0f; // Nguong nhiet do tuyet doi
const float NGUONG_TOC_DO_TANG    = 2.0f;  // Do C tang tren moi giay
const float NGUONG_TIN_CAY_AI     = 0.80f; // Chi chap nhan nhan AI khi du tin cay
const uint8_t SO_LOI_DHT_TOI_DA   = 3;     // So lan doc loi lien tiep truoc khi bao loi DHT
const uint16_t TAN_SO_COI         = 2000;  // Tan so coi (Hz)

// Wokwi relay module kich muc CAO. Nhieu module that kich muc THAP: doi hai hang so nay.
const uint8_t MUC_BAT = HIGH;
const uint8_t MUC_TAT = LOW;
// Module cam bien lua that thuong cho DO = LOW khi PHAT HIEN lua.
// Kiem tra lai voi linh kien Wokwi o Buoc 2 va doi neu can.
const uint8_t MUC_CO_LUA = LOW;

DHT dht(PIN_DHT, DHT22);
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

enum TrangThai { BINH_THUONG, CANH_BAO, CHUA_CHAY, KHOI_PHUC };
const char* TEN_TRANG_THAI[] = { "BINH_THUONG", "CANH_BAO", "CHUA_CHAY", "KHOI_PHUC" };
const char* TEN_LCD[]        = { "BINHTHUONG",  "CANH BAO",  "CHUA CHAY", "KHOI PHUC" };
TrangThai trangThai = BINH_THUONG;
uint32_t  mocVaoTrangThai = 0;
bool      hetGioChuaChay  = false;   // Da cat bom do het T_MAX, cho nguoi van hanh xac nhan
const char* nguonKichHoat = "-";     // Nguon dua he vao trang thai bao dong: LUAT / AI

// Bien du lieu cam bien
int   adcKhoi = 0, adcLua = 0, mucKhoi = 0;
bool  coLua = false;
float nhietDo = NAN, doAmKK = NAN, tocDoTangNhiet = 0.0f;
uint32_t mocDocDHT = 0, mocDHTThanhCong = 0;
uint8_t  demLoiDHT = 0;
bool     loiDHT = false;

// Bien nhanh AI
int   mucAI = 0;            // 0 binh thuong, 1 khoi, 2 lua
uint32_t mocNhanAI = 0;     // Moc thoi gian ban tin AI hop le gan nhat
bool  daNhanAI = false;     // Chua tung nhan ban tin thi coi nhu mat nguon AI
bool  nguonKichHoatLaAI = false;
int   mucCucBoGanNhat = 0;

// Bien nut nhan, ket noi lai, coi
bool     nutDaNhan = false;            // Su kien nhan nut (da chong doi)
uint32_t mocThuKetNoi = 0, khoangChoMQTT = 0;
uint8_t  soLanThuMQTT = 0;
bool     coiDangKeu = false;

// ----- Nguyen mau ham -----
void xuLyBanTinMQTT(char* topic, byte* payload, unsigned int len);
void docNutNhan();
void docCamBien();
int  luatCucBo();
bool aiConHieuLuc();
int  hopNhatQuyetDinh(int mucCucBo);
void chuyenTrangThai(TrangThai moi, int muc);
void capNhatTrangThai(int muc);
void dieuKhienChapHanh(int muc);
void ketNoiLaiMQTT();
void guiTrangThai();
void hienThi();
void ghiNhatKy(int muc);

// Khoi tao ngoai vi, Wi-Fi va MQTT. Wi-Fi co gioi han thoi gian cho
// de he thong van chay o che do cuc bo neu khong vao duoc mang.
void setup() {
  Serial.begin(115200);
  dht.begin();
  Wire.begin(PIN_SDA, PIN_SCL);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("NHOM 07 - PCCC");
  lcd.setCursor(0, 1); lcd.print("Dang khoi dong..");

  pinMode(PIN_FLAME_DO, INPUT_PULLUP);   // Module ho cuc thu can dien tro keo len
  pinMode(PIN_NUT_LUA, INPUT_PULLUP);
  pinMode(PIN_RELAY_BOM, OUTPUT); digitalWrite(PIN_RELAY_BOM, MUC_TAT);
  pinMode(PIN_RELAY_VAN, OUTPUT); digitalWrite(PIN_RELAY_VAN, MUC_TAT);
  pinMode(PIN_BUZZER, OUTPUT);    digitalWrite(PIN_BUZZER, LOW);
  pinMode(PIN_LED_DO, OUTPUT);    pinMode(PIN_LED_XANH, OUTPUT);
  pinMode(PIN_BTN_RESET, INPUT_PULLUP);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_KENH);
  uint32_t batDau = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - batDau < 10000) {
    delay(200);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("\n# WIFI,da ket noi,ip="));
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(F("\n# WIFI,chua ket noi - chay che do cuc bo"));
  }

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(xuLyBanTinMQTT);
  mqtt.setBufferSize(256);       // Du cho ban tin JSON ngan
  mqtt.setSocketTimeout(2);      // Giam thoi gian chan khi broker khong phan hoi
  khoangChoMQTT = T_CHO_MQTT_DAU;

  Serial.println(F("thoi_gian_ms,adc_khoi,muc_khoi,co_lua,adc_lua,nhiet_do,do_am,"
                   "toc_do_tang,muc_cuc_bo,muc_ai,ai_ket_noi,muc_cuoi,trang_thai,nguon_kich_hoat"));
}

// Ham goi lai khi nhan ban tin tu nhanh AI, dang {"nhan":"lua","do_tin_cay":0.93}.
// Ban tin hong, thieu truong, nhan la hoac do tin cay ngoai [0,1] bi bo qua
// hoan toan: khong cap nhat mucAI va khong lam moi moc thoi gian.
void xuLyBanTinMQTT(char* topic, byte* payload, unsigned int len) {
  JsonDocument doc;                                   // ArduinoJson phien ban 7
  if (deserializeJson(doc, payload, len)) {
    Serial.println(F("# MQTT,ban tin khong phai JSON - bo qua"));
    return;
  }
  const char* nhan = doc["nhan"];
  if (nhan == nullptr || !doc["do_tin_cay"].is<float>()) {
    Serial.println(F("# MQTT,ban tin thieu truong - bo qua"));
    return;
  }
  float tinCay = doc["do_tin_cay"];
  int muc;
  if      (strcmp(nhan, "lua") == 0)         muc = 2;
  else if (strcmp(nhan, "khoi") == 0)        muc = 1;
  else if (strcmp(nhan, "binh_thuong") == 0) muc = 0;
  else {
    Serial.println(F("# MQTT,nhan khong hop le - bo qua"));
    return;
  }
  if (tinCay < 0.0f || tinCay > 1.0f) {
    Serial.println(F("# MQTT,do tin cay ngoai [0,1] - bo qua"));
    return;
  }
  mocNhanAI = millis();
  daNhanAI  = true;
  mucAI = (tinCay >= NGUONG_TIN_CAY_AI) ? muc : 0;   // Khong du tin cay thi khong nang muc
  Serial.printf("# MQTT,nhan=%s,do_tin_cay=%.2f,muc_ai=%d\n", nhan, tinCay, mucAI);
}

// Doc nut xac nhan co chong doi; chi bao su kien mot lan cho moi lan nhan.
void docNutNhan() {
  static bool docTruoc = HIGH, onDinh = HIGH;
  static uint32_t mocDoi = 0;
  bool doc = digitalRead(PIN_BTN_RESET);
  if (doc != docTruoc) { mocDoi = millis(); docTruoc = doc; }
  if (millis() - mocDoi >= T_CHONG_DOI_MS && doc != onDinh) {
    onDinh = doc;
    if (onDinh == LOW) nutDaNhan = true;   // Canh xuong: nut vua duoc nhan
  }
}

// Doc cam bien. MQ-2 va cam bien lua doc moi chu ky chinh; DHT22 co chu ky
// rieng vi khong doc duoc nhanh hon 2 s. Toc do tang nhiet tinh theo khoang
// thoi gian thuc te giua hai lan doc DHT22 thanh cong.
void docCamBien() {
  uint32_t nay = millis();
  adcKhoi = analogRead(PIN_MQ2);
  adcLua  = analogRead(PIN_FLAME_AO);
  coLua   = (digitalRead(PIN_FLAME_DO) == MUC_CO_LUA) || (digitalRead(PIN_NUT_LUA) == LOW);

  // Phan muc khoi co do tre: chi ha muc khi ADC xuong duoi (nguong - DO_TRE_KHOI)
  int moi = 0;
  if (adcKhoi >= NGUONG_KHOI_NGUY_HIEM)     moi = 2;
  else if (adcKhoi >= NGUONG_KHOI_CANH_BAO) moi = 1;
  if (mucKhoi == 2 && moi < 2 && adcKhoi > NGUONG_KHOI_NGUY_HIEM - DO_TRE_KHOI)      moi = 2;
  else if (mucKhoi >= 1 && moi < 1 && adcKhoi > NGUONG_KHOI_CANH_BAO - DO_TRE_KHOI)  moi = 1;
  mucKhoi = moi;

  if (nay - mocDocDHT >= CHU_KY_DHT_MS) {
    mocDocDHT = nay;
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (isnan(t) || isnan(h)) {
      if (demLoiDHT < 255) demLoiDHT++;
      if (demLoiDHT >= SO_LOI_DHT_TOI_DA && !loiDHT) {
        loiDHT = true;
        Serial.println(F("# DHT,doc loi lien tiep - bo qua tieu chi nhiet"));
      }
      return;
    }
    if (!isnan(nhietDo) && mocDHTThanhCong != 0) {
      float dt = (nay - mocDHTThanhCong) / 1000.0f;
      if (dt > 0.0f) tocDoTangNhiet = (t - nhietDo) / dt;
    }
    nhietDo = t;
    doAmKK  = h;
    mocDHTThanhCong = nay;
    demLoiDHT = 0;
    loiDHT = false;
  }
}

// Lop luat an toan cuc bo: tra ve 0 binh thuong, 1 canh bao, 2 nguy hiem.
// Luon chay, khong phu thuoc mang. Trong giai doan lam nong chi bo qua MQ-2.
int luatCucBo() {
  int muc = 0;
  if (millis() >= T_LAM_NONG_MQ2) muc = mucKhoi;
  if (coLua) muc = 2;
  if (!loiDHT && !isnan(nhietDo)) {
    if (nhietDo >= NGUONG_NHIET_C)            muc = 2;
    if (tocDoTangNhiet >= NGUONG_TOC_DO_TANG) muc = 2;   // Nhiet tang dot ngot
  }
  return muc;
}

// Nguon AI con hieu luc khi da tung nhan ban tin hop le va chua qua han.
bool aiConHieuLuc() {
  return daNhanAI && (millis() - mocNhanAI <= T_HET_HAN_AI);
}

// Quy tac hop nhat: AI chi duoc NANG muc, khong duoc HA muc cua luat cuc bo.
int hopNhatQuyetDinh(int mucCucBo) {
  mucCucBoGanNhat = mucCucBo;
  int mucAIhieuLuc = aiConHieuLuc() ? mucAI : 0;
  nguonKichHoatLaAI = (mucAIhieuLuc > mucCucBo);
  return (mucAIhieuLuc > mucCucBo) ? mucAIhieuLuc : mucCucBo;
}

// Doi trang thai, ghi nhan nguon kich hoat va in dong su kien.
void chuyenTrangThai(TrangThai moi, int muc) {
  if (moi == CANH_BAO || moi == CHUA_CHAY) {
    nguonKichHoat = nguonKichHoatLaAI ? "AI" : "LUAT";
  } else if (moi == BINH_THUONG) {
    nguonKichHoat = "-";
  }
  Serial.printf("# CHUYEN,%lu,%s->%s,muc=%d,nguon=%s\n", (unsigned long)millis(),
                TEN_TRANG_THAI[trangThai], TEN_TRANG_THAI[moi], muc, nguonKichHoat);
  trangThai = moi;
  mocVaoTrangThai = millis();
  guiTrangThai();
}

// May trang thai bon trang thai. KHOI_PHUC la trang thai bao dong con chot:
// chi ve BINH_THUONG khi dieu kien da an toan VA nguoi van hanh nhan nut.
void capNhatTrangThai(int muc) {
  bool nhan = nutDaNhan;
  nutDaNhan = false;
  switch (trangThai) {
    case BINH_THUONG:
      if (muc == 2)      chuyenTrangThai(CHUA_CHAY, muc);
      else if (muc == 1) chuyenTrangThai(CANH_BAO, muc);
      break;
    case CANH_BAO:
      if (muc == 2)      chuyenTrangThai(CHUA_CHAY, muc);
      else if (muc == 0) chuyenTrangThai(KHOI_PHUC, muc);
      break;
    case CHUA_CHAY:
      if (millis() - mocVaoTrangThai >= T_MAX_CHUA_CHAY) {
        hetGioChuaChay = true;   // Cat bom, khong tu bom lai khi chua xac nhan
        Serial.println(F("# BOM,het thoi gian chua chay toi da - dung bom"));
        chuyenTrangThai(KHOI_PHUC, muc);
      } else if (muc < 2) {
        chuyenTrangThai(KHOI_PHUC, muc);
      }
      break;
    case KHOI_PHUC:
      if (nhan) {
        if (muc == 0) {
          hetGioChuaChay = false;
          chuyenTrangThai(BINH_THUONG, muc);
          break;
        }
        if (hetGioChuaChay) {    // Nguoi van hanh cho phep bom them mot luot
          hetGioChuaChay = false;
          Serial.println(F("# BOM,nguoi van hanh cho phep chua chay luot moi"));
        }
      }
      // Sau khi het gio, giu nguyen KHOI_PHUC (bom tat, coi goi nguoi van hanh)
      // de he khong vong qua CANH_BAO roi tu bom lai.
      if (hetGioChuaChay) break;
      if (muc == 2)      chuyenTrangThai(CHUA_CHAY, muc);
      else if (muc == 1) chuyenTrangThai(CANH_BAO, muc);
      break;
  }
}

// Xuat tin hieu ra relay, coi, den theo trang thai hien tai.
void dieuKhienChapHanh(int muc) {
  bool chuaChay = (trangThai == CHUA_CHAY);
  // Coi keu o CANH_BAO, CHUA_CHAY; o KHOI_PHUC chi keu khi bom da bi cat
  // do het gio ma nguy hiem van con, de goi nguoi van hanh.
  bool coiKeu = (trangThai == CANH_BAO || trangThai == CHUA_CHAY ||
                 (trangThai == KHOI_PHUC && hetGioChuaChay && muc >= 1));
  // KHOI_PHUC giu den do sang cho toi khi nguoi van hanh xac nhan.
  bool denDo = (trangThai != BINH_THUONG);
  digitalWrite(PIN_RELAY_BOM, chuaChay ? MUC_BAT : MUC_TAT);
  digitalWrite(PIN_RELAY_VAN, chuaChay ? MUC_BAT : MUC_TAT);
  digitalWrite(PIN_LED_DO,   denDo ? HIGH : LOW);
  digitalWrite(PIN_LED_XANH, (trangThai == BINH_THUONG) ? HIGH : LOW);
  if (coiKeu != coiDangKeu) {          // Chi goi tone() khi doi trang thai coi
    if (coiKeu) tone(PIN_BUZZER, TAN_SO_COI);
    else        noTone(PIN_BUZZER);
    coiDangKeu = coiKeu;
  }
}

// Ket noi lai Wi-Fi/MQTT khong chan vong lap chinh: moi lan goi chi thu toi
// da mot lan, khoang cho tang gap doi sau moi lan loi, nghi T_NGHI_MQTT sau
// SO_LAN_THU_MQTT lan loi lien tiep. Dang ky lai chu de sau moi lan noi lai.
void ketNoiLaiMQTT() {
  uint32_t nay = millis();
  if (nay - mocThuKetNoi < khoangChoMQTT) return;
  mocThuKetNoi = nay;

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    Serial.println(F("# WIFI,mat ket noi - thu lai"));
    khoangChoMQTT = 5000;
    return;
  }

  char clientId[32];
  snprintf(clientId, sizeof(clientId), "nhom07-esp32-%04X", (unsigned)(esp_random() & 0xFFFF));
  // LWT: broker tu dang {"online":false} len chu de trang thai khi thiet bi rot mang
  if (mqtt.connect(clientId, nullptr, nullptr, MQTT_TOPIC_TT, 0, true, "{\"online\":false}")) {
    mqtt.subscribe(MQTT_TOPIC_AI);
    Serial.printf("# MQTT,da ket noi %s,dang ky %s\n", MQTT_BROKER, MQTT_TOPIC_AI);
    soLanThuMQTT = 0;
    khoangChoMQTT = T_CHO_MQTT_DAU;
    guiTrangThai();
    return;
  }

  soLanThuMQTT++;
  Serial.printf("# MQTT,ket noi loi rc=%d,lan=%u\n", mqtt.state(), soLanThuMQTT);
  if (soLanThuMQTT >= SO_LAN_THU_MQTT) {
    soLanThuMQTT = 0;
    khoangChoMQTT = T_NGHI_MQTT;
  } else {
    khoangChoMQTT = min(khoangChoMQTT * 2, T_CHO_MQTT_MAX);
  }
}

// Gui trang thai thiet bi len broker (chieu ESP32 -> may tinh).
void guiTrangThai() {
  if (!mqtt.connected()) return;
  char buf[200];
  snprintf(buf, sizeof(buf),
           "{\"online\":true,\"tt\":\"%s\",\"khoi\":%d,\"lua\":%d,\"t\":%.1f,"
           "\"muc_ai\":%d,\"ai\":%d,\"nguon\":\"%s\",\"ms\":%lu}",
           TEN_TRANG_THAI[trangThai], adcKhoi, coLua ? 1 : 0,
           isnan(nhietDo) ? -99.0f : nhietDo, mucAI, aiConHieuLuc() ? 1 : 0,
           nguonKichHoat, (unsigned long)millis());
  mqtt.publish(MQTT_TOPIC_TT, buf, true);
}

// Cap nhat LCD 16x2. Dong 1: khoi, nhiet, lua. Dong 2: trang thai + AI.
void hienThi() {
  char d1[17], d2[17];
  if (loiDHT || isnan(nhietDo)) {
    snprintf(d1, sizeof(d1), "K%-4d T--.- %s", adcKhoi, coLua ? "LUA!" : "    ");
  } else {
    snprintf(d1, sizeof(d1), "K%-4d T%4.1f %s", adcKhoi, nhietDo, coLua ? "LUA!" : "    ");
  }
  if (trangThai == BINH_THUONG && millis() < T_LAM_NONG_MQ2) {
    snprintf(d2, sizeof(d2), "LAM NONG MQ2 %2lus",
             (unsigned long)((T_LAM_NONG_MQ2 - millis()) / 1000));
  } else {
    const char* ai = aiConHieuLuc() ? (trangThai == BINH_THUONG ? "AI OK" : nguonKichHoat)
                                    : "MATAI";
    snprintf(d2, sizeof(d2), "%-10s %5s", TEN_LCD[trangThai], ai);
  }
  lcd.setCursor(0, 0); lcd.print(d1);
  for (int i = strlen(d1); i < 16; i++) lcd.print(' ');
  lcd.setCursor(0, 1); lcd.print(d2);
  for (int i = strlen(d2); i < 16; i++) lcd.print(' ');
}

// In mot dong CSV ra Serial cho moi chu ky lay mau.
void ghiNhatKy(int muc) {
  Serial.printf("%lu,%d,%d,%d,%d,", (unsigned long)millis(), adcKhoi, mucKhoi, coLua ? 1 : 0, adcLua);
  if (isnan(nhietDo)) Serial.print("nan,nan,");
  else                Serial.printf("%.1f,%.1f,", nhietDo, doAmKK);
  Serial.printf("%.2f,%d,%d,%d,%d,%s,%s\n", tocDoTangNhiet, mucCucBoGanNhat, mucAI,
                aiConHieuLuc() ? 1 : 0, muc, TEN_TRANG_THAI[trangThai],
                trangThai == BINH_THUONG ? "-" : nguonKichHoat);
}

// Vong lap chinh: lap lich bang millis(), khong dung delay().
void loop() {
  static uint32_t mocLayMau = 0, mocGuiTT = 0;
  if (!mqtt.connected()) ketNoiLaiMQTT();
  mqtt.loop();
  docNutNhan();

  if (millis() - mocLayMau >= CHU_KY_MS) {
    mocLayMau = millis();
    docCamBien();
    int muc = hopNhatQuyetDinh(luatCucBo());
    capNhatTrangThai(muc);
    dieuKhienChapHanh(muc);
    hienThi();
    ghiNhatKy(muc);
  }
  if (millis() - mocGuiTT >= CHU_KY_GUI_TT_MS) {
    mocGuiTT = millis();
    guiTrangThai();
  }
}
