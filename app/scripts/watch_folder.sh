#!/bin/bash

# Các đường dẫn tuyệt đối
BASE_DIR="/home/c/AndroidStudioProjects/Cetena0.15/app"
TARGET_DIR="$BASE_DIR/input_files/vendor_quotations"
PYTHON_BIN="$BASE_DIR/venv/bin/python3"
PROCESSOR_SCRIPT="$BASE_DIR/scripts/standardize_with_ai.py"

echo "--------------------------------------------------"
echo "🚀 Cetena Purchasing Watcher started"
echo "📂 Monitoring: $TARGET_DIR"
echo "--------------------------------------------------"

# Theo dõi sự kiện tạo file mới hoặc di chuyển file vào
# Mở rộng cho cả .xlsx, .xls, .csv và .pdf
inotifywait -m "$TARGET_DIR" -e create -e moved_to |
    while read path action file; do
        if [[ "$file" == *.xlsx ]] || [[ "$file" == *.xls ]] || [[ "$file" == *.csv ]] || [[ "$file" == *.pdf ]]; then
            echo "$(date): 📥 Phát hiện báo giá mới: $file"

            # Chạy script xử lý chính
            $PYTHON_BIN "$PROCESSOR_SCRIPT" "$TARGET_DIR/$file"

            echo "$(date): ✅ Đã xử lý xong: $file"
            echo "--------------------------------------------------"
        fi
    done
