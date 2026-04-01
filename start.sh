#!/bin/bash

# Di chuyển vào thư mục dự án
cd /home/c/AndroidStudioProjects/Cetena1

# Thông báo
echo "🚀 Đang khởi động Zalo Receiver Server..."

# Chạy server bằng python trong môi trường ảo
if [ -d "venv" ]; then
    ./venv/bin/python3 zalo_receiver.py
else
    echo "❌ Lỗi: Không tìm thấy thư mục venv. Hãy tạo môi trường ảo trước."
fi
