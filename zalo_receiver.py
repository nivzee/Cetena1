from flask import Flask, request, jsonify, render_template_string, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
import re
import datetime
import threading
import time
from queue import Queue

app = Flask(__name__)

# Thư mục lưu file nhận được từ điện thoại
UPLOAD_FOLDER = 'zalo_files'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Cấu hình Database
DB_CONFIG = {
    "database": "message_center1",
    "user": "c",
    "password": "donkihote",
    "host": "127.0.0.1",
    "port": "5432"
}

# Biến toàn cục để ghi nhớ người đang chat
current_active_contact = "Người dùng Zalo"
db_queue = Queue()

def db_worker():
    """Luồng chuyên trách việc ghi vào Database"""
    while True:
        try:
            item = db_queue.get()
            if item is None: break
            data, direction = item

            sender_name = data.get('sender', 'Người dùng Zalo')
            message_content = data.get('message', '')

            conn = None
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cur = conn.cursor()

                # Chống trùng
                cur.execute("""
                    SELECT message_id FROM fact_messages
                    WHERE content = %s AND direction = %s
                    AND created_at > CURRENT_TIMESTAMP - INTERVAL '5 seconds'
                """, (message_content, direction))

                if not cur.fetchone():
                    cur.execute("SELECT contact_id FROM dim_contacts WHERE full_name = %s", (sender_name,))
                    contact = cur.fetchone()
                    contact_id = contact[0] if contact else None
                    if not contact_id:
                        cur.execute("INSERT INTO dim_contacts (full_name) VALUES (%s) RETURNING contact_id", (sender_name,))
                        contact_id = cur.fetchone()[0]

                    cur.execute(
                        "INSERT INTO fact_messages (contact_id, platform, content, direction, raw_data) VALUES (%s, %s, %s, %s, %s)",
                        (contact_id, 'ZALO', message_content, direction, Json(data))
                    )
                    conn.commit()
                cur.close()
            except Exception as e:
                print(f"❌ Lỗi Database: {e}")
            finally:
                if conn: conn.close()
            db_queue.task_done()
        except Exception: pass

threading.Thread(target=db_worker, daemon=True).start()

def get_now():
    return datetime.datetime.now().strftime("%H:%M:%S")

# Giao diện Web Dashboard đơn giản
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Cetena1 Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body { font-family: sans-serif; background: #f0f2f5; margin: 20px; }
        .container { max-width: 900px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h2 { color: #0068ff; border-bottom: 2px solid #0068ff; padding-bottom: 10px; }
        .message { border-bottom: 1px solid #eee; padding: 10px 0; display: flex; flex-direction: column; }
        .header { display: flex; justify-content: space-between; font-size: 0.85em; color: #666; margin-bottom: 5px; }
        .sender { font-weight: bold; color: #1c1e21; }
        .content { font-size: 1.1em; color: #333; line-height: 1.4; }
        .inbound { border-left: 4px solid #0068ff; padding-left: 10px; }
        .outbound { border-left: 4px solid #4caf50; padding-left: 10px; background: #f9fff9; }
        .file-link { color: #e91e63; text-decoration: none; font-weight: bold; }
        .img-preview { max-width: 300px; margin-top: 10px; border-radius: 5px; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <div class="container">
        <h2>💬 Nhật ký tin nhắn Zalo</h2>
        {% for msg in messages %}
            <div class="message {{ 'inbound' if msg.direction == 'INBOUND' else 'outbound' }}">
                <div class="header">
                    <span class="sender">{{ '📥' if msg.direction == 'INBOUND' else '🚀' }} {{ msg.full_name }}</span>
                    <span>{{ msg.created_at.strftime('%H:%M:%S - %d/%m') }}</span>
                </div>
                <div class="content">
                    {% if '[FILE]' in msg.content %}
                        <a href="/files/{{ msg.content.replace('[FILE] ', '') }}" class="file-link" target="_blank">📎 {{ msg.content }}</a>
                        {% if msg.content.lower().endswith(('.jpg', '.png', '.jpeg', '.gif')) %}
                            <br><img src="/files/{{ msg.content.replace('[FILE] ', '') }}" class="img-preview">
                        {% endif %}
                    {% else %}
                        {{ msg.content }}
                    {% endif %}
                </div>
            </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT m.created_at, c.full_name, m.direction, m.content
        FROM fact_messages m
        JOIN dim_contacts c ON m.contact_id = c.contact_id
        ORDER BY m.created_at DESC LIMIT 50
    """)
    messages = cur.fetchall()
    cur.close()
    conn.close()
    return render_template_string(HTML_TEMPLATE, messages=messages)

@app.route('/files/<path:filename>')
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/webhook/zalo', methods=['POST'])
def receive_zalo():
    global current_active_contact
    data = request.json
    direction = data.get('direction', 'INBOUND')
    raw_sender = data.get('sender', 'Người dùng Zalo')
    content = data.get('message', '')

    if direction == 'INBOUND' and raw_sender not in ['Người dùng Zalo', 'Ẩn danh', '']:
        current_active_contact = raw_sender

    sender = raw_sender
    if direction == 'OUTBOUND' and sender in ['Người dùng Zalo', 'Ẩn danh', '']:
        sender = current_active_contact
        data['sender'] = sender

    if direction == 'PING':
        print(f"[{get_now()}] 📡 PING OK")
        return jsonify({"status": "success"}), 200

    db_queue.put((data, direction))
    print(f"[{get_now()}] {'📥' if direction == 'INBOUND' else '🚀'} {sender}: {content}")
    return jsonify({"status": "success"}), 200

@app.route('/webhook/file', methods=['POST'])
def receive_file():
    try:
        file = request.files['file']
        sender = request.form.get('sender', current_active_contact)
        clean_name = re.sub(r'^\.trashed-\d+-', '', file.filename).lstrip('.')
        file.save(os.path.join(UPLOAD_FOLDER, clean_name))

        # Lưu vào DB để hiển thị trên Dashboard
        db_queue.put(({"sender": sender, "message": f"[FILE] {clean_name}"}, "INBOUND"))

        print(f"[{get_now()}] 📁 Đã nhận file từ {sender}: {clean_name}")
        return jsonify({"status": "success"}), 200
    except Exception:
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    print("--- DASHBOARD SẴN SÀNG TẠI: http://localhost:5000 ---")
    app.run(host='0.0.0.0', port=5000, threaded=True)
