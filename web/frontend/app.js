// Nhom 07 - Frontend bang dieu khien: nhan du lieu thoi gian thuc qua WebSocket
const $ = (id) => document.getElementById(id);
const TEN_TT = { BINH_THUONG: 'BÌNH THƯỜNG', CANH_BAO: 'CẢNH BÁO', CHUA_CHAY: 'CHỮA CHÁY', KHOI_PHUC: 'KHÔI PHỤC' };
const TEN_LOAI = { trang_thai: 'Trạng thái', nhan_ai: 'Nhãn AI', ban_tin_hong: 'Bản tin hỏng', kiem_thu: 'Kiểm thử', he_thong: 'Hệ thống' };
let nhanTruoc = null, ttTruoc = null;

function hienThi(d) {
  const tb = d.thiet_bi || {};
  $('mqtt').textContent = d.mqtt_ket_noi ? 'MQTT: đã kết nối' : 'MQTT: mất kết nối';
  $('mqtt').className = 'chip' + (d.mqtt_ket_noi ? ' ok' : '');

  const tt = tb.online === false ? 'OFFLINE' : (tb.tt || '?');
  $('trang-thai').textContent = TEN_TT[tt] || tt;
  $('trang-thai').className = 'trang-thai ' + tt;
  $('nguon').textContent = tb.nguon || '-';
  $('online').textContent = tb.online === undefined ? '-' : (tb.online ? 'Có' : 'Không');
  $('tuoi-status').textContent = d.giay_tu_status == null ? '-' : d.giay_tu_status + ' s';
  $('khoi').textContent = tb.khoi ?? '-';
  $('lua').textContent = tb.lua === undefined ? '-' : (tb.lua ? 'PHÁT HIỆN' : 'Không');
  $('nhiet').textContent = tb.t === undefined || tb.t === -99 ? '-' : tb.t;
  $('muc-ai').textContent = tb.muc_ai ?? '-';
  $('ai-tb').textContent = tb.ai === undefined ? '-' : (tb.ai ? 'Có' : 'Không (hết hạn 15 s)');

  const ai = d.ai || {};
  $('nhan-ai').textContent = ai.nhan || '-';
  $('nhan-ai').className = 'nhan ' + (ai.nhan || '');
  $('tin-cay').textContent = ai.do_tin_cay ?? '-';
  $('tuoi-ai').textContent = d.giay_tu_ai == null ? '-' : d.giay_tu_ai + ' s';
  $('ms').textContent = d.ai_noi_bo ? d.ms_suy_luan + ' ms' : 'AI chạy ngoài backend';
  $('video').style.display = d.ai_noi_bo ? 'block' : 'none';

  // Lam moi lich su khi trang thai hoac nhan doi
  if (tt !== ttTruoc || ai.nhan !== nhanTruoc) { ttTruoc = tt; nhanTruoc = ai.nhan; taiLichSu(); }
}

async function taiLichSu() {
  const ds = await (await fetch('/api/su-kien?gioi_han=50')).json();
  $('lich-su').innerHTML = ds.map((s) => `<tr><td>${new Date(s.ts * 1000).toLocaleTimeString('vi-VN')}</td>`
    + `<td>${TEN_LOAI[s.loai] || s.loai}</td><td>${JSON.stringify(s.noi_dung).replace(/</g, '&lt;')}</td></tr>`).join('');
}

function ketNoi() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onmessage = (e) => hienThi(JSON.parse(e.data));
  ws.onclose = () => { $('mqtt').textContent = 'Mất kết nối backend'; $('mqtt').className = 'chip'; setTimeout(ketNoi, 2000); };
}

document.querySelectorAll('button[data-kieu]').forEach((b) => b.addEventListener('click', async () => {
  await fetch('/api/kiem-thu/' + b.dataset.kieu, { method: 'POST' });
  setTimeout(taiLichSu, 500);
}));
$('video').src = '/api/video';
taiLichSu();
ketNoi();
