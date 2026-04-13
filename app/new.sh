#!/bin/bash
# Script hỗ trợ quản lý Cetena Dashboard & Watcher

export DB_PASSWORD="donkihote"
BASE_DIR="/home/c/AndroidStudioProjects/Cetena0.15/app"

# Dọn dẹp tiến trình cũ (Kill port 5001 và các watcher)
echo "🧹 Đang dọn dẹp các tiến trình cũ..."
fuser -k 5001/tcp > /dev/null 2>&1
pkill -f watch_folder.sh > /dev/null 2>&1
pkill -f inotifywait > /dev/null 2>&1

echo "--------------------------------------------------"
echo "🚀 Đang khởi động Cetena Web Dashboard (Cổng 5001)..."
echo "👉 Truy cập: http://localhost:5001"
echo "--------------------------------------------------"

# Chạy Dashboard trong nền (Background)
$BASE_DIR/venv/bin/python3 $BASE_DIR/scripts/web_dashboard.py &

# Đợi 2 giây rồi bắt đầu theo dõi log của Watcher
sleep 2
echo "📊 Đang theo dõi Logs từ Watcher (Sử dụng Ctrl+C để thoát)..."

# Nếu chạy dưới dạng service:
# journalctl -u cetena-watcher.service -f
# Nếu chạy script trực tiếp:
bash $BASE_DIR/scripts/watch_folder.sh
