from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import Json

app = Flask(__name__)

# Bước 1: Cấu hình DB
DB_CONFIG = {
    "database": "message_center1",
    "user": "c",
    "password": "donkihote",
    "host": "127.0.0.1",
    "port": "5432"
}

# Biến tạm để ghi nhớ người vừa nhắn tin đến gần nhất
last_inbound_sender = "Người dùng Zalo"

@app.route('/webhook/zalo', methods=['POST'])
def receive_zalo():
    global last_inbound_sender
    conn = None
    try:
        data = request.json
        raw_sender = data.get('sender', 'Người dùng Zalo')
        message_content = data.get('message', '')
        direction = data.get('direction', 'INBOUND')

        print(f"📩 Nhận dữ liệu gốc: Sender='{raw_sender}', Direction='{direction}'")

        # LOGIC GÁN TÊN:
        # Nếu App tìm thấy tên thật (ví dụ 'Bao An'), nó sẽ dùng luôn tên đó.
        # Chỉ khi App gửi về 'Người dùng Zalo' thì Server mới lấy tên người nhắn đến gần nhất.
        sender_name = raw_sender
        if direction == 'OUTBOUND':
            if sender_name == 'Người dùng Zalo' or not sender_name:
                sender_name = last_inbound_sender
                print(f"⚠️ App không tìm thấy tên người nhận, tự gán cho: {sender_name}")
            else:
                print(f"🎯 App đã tìm thấy tên người nhận: {sender_name}")

        if direction == 'INBOUND' and raw_sender != 'Người dùng Zalo':
            last_inbound_sender = raw_sender

        # Xử lý gói tin PING
        if direction == 'PING':
            print("📡 Nhận gói tin PING từ điện thoại. Kết nối OK!")
            return jsonify({"status": "success", "message": "Pong"}), 200

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Tìm/Tạo Contact
        cur.execute("SELECT contact_id FROM dim_contacts WHERE full_name = %s", (sender_name,))
        contact = cur.fetchone()

        if contact:
            contact_id = contact[0]
        else:
            cur.execute(
                "INSERT INTO dim_contacts (full_name) VALUES (%s) RETURNING contact_id",
                (sender_name,)
            )
            contact_id = cur.fetchone()[0]
            print(f"✨ Tạo danh bạ mới cho: {sender_name}")

        # Lưu tin nhắn
        cur.execute(
            """
            INSERT INTO fact_messages (contact_id, platform, content, direction, raw_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (contact_id, 'ZALO', message_content, direction, Json(data))
        )
        
        conn.commit()
        cur.close()
        print(f"✅ [{direction}] {sender_name}: {message_content[:30]}...")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"❌ Error: {e}")
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
