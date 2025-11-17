# templar-log
templar-log-monitor
# 🛡️ Templar Log Monitor  
Realtime Grafana Log Crawler & Error Alert Tool for Templar Validators

Templar Log Monitor là công cụ chạy trên Windows giúp **giám sát realtime log Validator trên Grafana**, tự động lọc lỗi quan trọng theo từng UID, và gửi cảnh báo sang **Discord Webhook** ngay lập tức.

Công cụ thiết kế để chạy ổn định 24/7, với nhiều cơ chế tự phục hồi, tự reload, chống crash trình duyệt và chống bỏ sót log.

---

## 🚀 Tính năng nổi bật

### ✅ 1. Monitoring Realtime Grafana  
- Crawler tự động đọc log từ Grafana dashboard (headless Chrome)  
- Lọc chính xác theo `var-Search=UID`  
- Parse DOM bằng BeautifulSoup → không bị stale element

### ✅ 2. Lọc lỗi **theo đúng UID** (không nhầm UID khác)
Chỉ gửi lỗi nếu:
- UID trong log == UID người dùng nhập  
- Không gửi lỗi của UID khác

### ✅ 3. Nhận diện lỗi thông minh  
Các lỗi được phát hiện và gửi alert:
- Gradient Score âm (xác định bằng phân tích số thực, không phải tìm dấu “-”)
- Negative Eval Frequency
- avg_steps_behind vượt max
- No gradient gathered / Consecutive Misses
- Skip score do zero / negative

### ✅ 4. Ngăn spam và tránh gửi trùng  
- Tự ghi lịch sử sent vào `sent_history.json`  
- Log giống nhau KHÔNG gửi lại

### ✅ 5. Cơ chế tự phục hồi mạnh mẽ
- Soft Refresh nếu 120s không có log mới  
- Sau 10 soft refresh liên tiếp → **HARD RELOAD trang Grafana**  
- Nếu ChromeDriver crash → **tự restart headless Chrome và chạy lại**  
- Không bao giờ tự tắt hoặc treo

### ✅ 6. Giao diện GUI dễ dùng
- Nhập UID
- Nhập thời gian lọc (minutes)
- Nút Start / Pause / Resume / Stop
- Log mở rộng full screen

---
## 📂 Cấu trúc thư mục 
templar-log-monitor/
 │ 
 ├── 📄README.md # Tài liệu mô tả dự án 
 ├── 🐍main.py # File giao diện Tkinter 
 ├── 🐍crawler.py # Core crawler theo dõi Grafana 
 ├── 🐍discord_notify.py # Gửi thông báo sang Discord webhook
 ├── 📄main.spec # File build PyInstaller  
 ├── 📄templar.ico # Icon mặc định của ứng dụng 
 ├── 📄templar_icon.png # Ảnh PNG (backup icon)  
 ├── 📝sent_history.json # Lưu lịch sử log đã gửi để tránh spam  
 │── 📂dist/ │ 
 │   └── 🧩main.exe # File EXE build từ PyInstaller (ứng dụng chạy chính) 
 │── 📂build/ # Folder build tạm của PyInstaller 
 │      └── 📂main
 │──📝json pycache/ # Cache Python