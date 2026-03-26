from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import Json

app = Flask(__name__)

# Bước 1: Định nghĩa cấu hình kết nối một lần duy nhất
DB_CONFIG = {
    "database": "message_center1",
    "user": "c",
    "password": "donkihote",
    "host": "127.0.0.1",
    "port": "5432"
}

@app.route('/webhook/zalo', methods=['POST'])
def receive_zalo():
    conn = None
    try:
        data = request.json
        sender_name = data.get('sender')
        message_content = data.get('message')
        direction = data.get('direction', 'INBOUND') # Lấy direction từ App

        # Bước 2: Kết nối database
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # BƯỚC 1: Tìm xem người này đã có trong danh bạ chưa
        cur.execute("SELECT contact_id FROM dim_contacts WHERE full_name = %s", (sender_name,))
        contact = cur.fetchone()

        if contact:
            contact_id = contact[0]
        else:
            # BƯỚC 2: Nếu chưa có, tự động tạo mới một contact
            cur.execute(
                "INSERT INTO dim_contacts (full_name) VALUES (%s) RETURNING contact_id",
                (sender_name,)
            )
            contact_id = cur.fetchone()[0]
            print(f"✨ Đã tạo danh bạ mới cho: {sender_name}")

        # BƯỚC 3: Lưu tin nhắn kèm theo contact_id và direction
        cur.execute(
            """
            INSERT INTO fact_messages (contact_id, platform, content, direction, raw_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (contact_id, 'ZALO', message_content, direction, Json(data))
        )
        
        conn.commit()
        cur.close()
        print(f"✅ Đã lưu tin nhắn {direction} từ/đến {sender_name}")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # Bước 4: Luôn đóng kết nối để tránh treo Database
        if conn:
            conn.close()

if __name__ == '__main__':
    # Chạy Server lắng nghe từ Star 5 qua WiFi
    app.run(host='0.0.0.0', port=5000)
