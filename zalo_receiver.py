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
        sender_name = data.get('sender', 'Người dùng Zalo')
        message_content = data.get('message')
        direction = data.get('direction', 'INBOUND')

        # LOGIC THÔNG MINH CHO OUTBOUND:
        # Nếu không lấy được tên người nhận từ App (vẫn là 'Người dùng Zalo')
        # thì gán nó cho người vừa nhắn tin đến gần nhất (vì mình thường reply người đó).
        if direction == 'OUTBOUND' and (sender_name == 'Người dùng Zalo' or not sender_name):
            sender_name = last_inbound_sender
            print(f"ℹ️ Auto-match Outbound to: {sender_name}")

        # Nếu là tin nhắn đến, ghi nhớ tên người gửi để dùng cho tin đi sau này
        if direction == 'INBOUND' and sender_name != 'Người dùng Zalo':
            last_inbound_sender = sender_name

        # Bước 2: Kết nối database
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # BƯỚC 1: Tìm/Tạo Contact
        cur.execute("SELECT contact_id FROM dim_contacts WHERE full_name = %s", (sender_name,))
        contact = cur.fetchone()

        if contact:
            contact_id = contact[0]
        else:
            # Nếu vẫn không xác định được ai, cứ tạo/lấy contact 'Người dùng Zalo'
            cur.execute(
                "INSERT INTO dim_contacts (full_name) VALUES (%s) RETURNING contact_id",
                (sender_name,)
            )
            contact_id = cur.fetchone()[0]
            print(f"✨ Created new contact: {sender_name}")

        # BƯỚC 2: Lưu tin nhắn
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
