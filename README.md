# Kokoro TTS – Giọng đọc AI tiếng Việt & tiếng Anh (offline)

Giao diện web chạy ngay trên máy, không cần Internet sau khi cài:

- **25 giọng tiếng Việt** (Bắc/Trung/Nam) – mô hình [VieNeu-TTS v3 Turbo](https://github.com/pnnbao97/VieNeu-TTS)
- **24 giọng tiếng Anh** + 6 giọng kể chuyện trinh thám – mô hình [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)
- Nghe thử giọng, chỉnh tốc độ, tâm trạng, nút 🎲 đổi kiểu đọc
- Biểu cảm: `[cười]` `[thở dài]` `[hắng giọng]`
- 📖 Từ điển phát âm cho từ tiếng Anh (hỗ trợ phiên âm IPA)
- 🔍 Kiểm tra kỹ: tự nghe lại bằng [PhoWhisper](https://huggingface.co/vinai/PhoWhisper-small) và đọc lại đoạn lỗi
- 🌏 **Bộ đọc song ngữ (tuỳ chọn)**: giọng Việt đọc tiếng Anh chuẩn bằng [OmniVoice](https://github.com/k2-fsa/OmniVoice), cài bằng file `3. Cai them Song ngu`
- **Tự cập nhật** từ GitHub mỗi lần mở

## Cài đặt (macOS chip M / Windows 10-11)

1. Tải về: **[Download ZIP](https://github.com/JayCo13/kokoro-tts/archive/refs/heads/main.zip)** rồi giải nén.
2. Chạy file cài (1 lần, cần Internet, tải ~3 GB):
   - macOS: chuột phải `1. Cai dat (Mac).command` → **Open**
   - Windows: bấm đúp `1. Cai dat (Windows).bat` (nếu bị chặn: *More info → Run anyway*)
3. Mở ứng dụng: bấm đúp `2. Mo Kokoro TTS (Mac).command` hoặc `2. Mo Kokoro TTS (Windows).bat`
   → trình duyệt mở `http://localhost:7860`.

Chi tiết: xem `HUONG DAN.txt`.

## Cập nhật
Mỗi lần mở, ứng dụng tự kiểm tra GitHub và tải bản code mới nhất (vài trăm KB).
Từ điển phát âm riêng của mỗi máy (`app/pronounce.txt`) được giữ nguyên.
