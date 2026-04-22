#!/bin/bash
# ============================================================
# CETENA V0.15 - IMMORTAL REBUILD SCRIPT (STABLE VERSION)
# ============================================================

# === CẤU HÌNH BẢO MẬT ===
MY_GEMINI_KEY=""
MY_DB_PASS="donkihote"
# ======================================

PROJECT_ROOT=$(pwd)
SCRIPTS_DIR="$PROJECT_ROOT/app/scripts"
echo "🚀 Rebuilding Cetena Factory in: $PROJECT_ROOT"

# 0. Tạo file .env tự động (Ưu tiên lấy từ biến môi trường nếu script trống)
ENV_GEMINI="${MY_GEMINI_KEY:-$GEMINI_API_KEY}"
ENV_DB_PASS="${MY_DB_PASS:-$DB_PASSWORD}"

cat <<EOF > "$PROJECT_ROOT/.env"
GEMINI_API_KEY=$ENV_GEMINI
DB_PASSWORD=$ENV_DB_PASS
EOF
echo "✅ Created .env configuration file (Project: $PROJECT_ROOT)"

# 1. Cấu trúc thư mục và Môi trường ảo
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$PROJECT_ROOT/app/input_files/vendor_quotations/archive"
mkdir -p "$PROJECT_ROOT/app/input_files/vendor_quotations/standardize"
mkdir -p "$PROJECT_ROOT/app/xls_temp"

echo "🐍 Setting up Python Virtual Environment..."
rm -rf "$PROJECT_ROOT/venv"
python3 -m venv "$PROJECT_ROOT/venv"

# DÙNG TRỰC TIẾP PYTHON CỦA VENV ĐỂ CÀI ĐẶT (KHÔNG CẦN SOURCE ACTIVATE)
"$PROJECT_ROOT/venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/venv/bin/python" -m pip install flask pandas requests openpyxl pdfplumber python-dotenv

# 2. Phục hồi Database
echo "📥 Checking/Creating Database..."
export PGPASSWORD="$MY_DB_PASS"

# Tự động tạo database nếu chưa tồn tại
psql -U c -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'cSaas'" | grep -q 1 || psql -U c -d postgres -c "CREATE DATABASE \"cSaas\";"

psql -U c -d cSaas <<EOF
DROP TABLE IF EXISTS quotation_items, quotations, vendors, users, roles, dna_kernel, standardization_rules, domains, entities CASCADE;
CREATE TABLE entities (id SERIAL PRIMARY KEY, name VARCHAR(100), code VARCHAR(20) UNIQUE);
CREATE TABLE domains (id SERIAL PRIMARY KEY, name VARCHAR(100), code VARCHAR(20) UNIQUE);
CREATE TABLE standardization_rules (id SERIAL PRIMARY KEY, name VARCHAR(100), rule_type VARCHAR(50), config JSONB);
CREATE TABLE dna_kernel (id SERIAL PRIMARY KEY, entity_id INT REFERENCES entities(id), domain_id INT REFERENCES domains(id), ui_config JSONB, rule_mapping JSONB, UNIQUE(entity_id, domain_id));
CREATE TABLE roles (id SERIAL PRIMARY KEY, name VARCHAR(50) UNIQUE, power_level INT);
CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE, entity_id INT REFERENCES entities(id), role_id INT REFERENCES roles(id), default_domain_id INT REFERENCES domains(id));
CREATE TABLE vendors (id SERIAL PRIMARY KEY, vendor_name VARCHAR(255), entity_id INT REFERENCES entities(id), UNIQUE(vendor_name, entity_id));
CREATE TABLE quotations (id SERIAL PRIMARY KEY, vendor_id INT REFERENCES vendors(id), entity_id INT REFERENCES entities(id), quote_number VARCHAR(100), status VARCHAR(50));
CREATE TABLE quotation_items (id SERIAL PRIMARY KEY, quotation_id INT REFERENCES quotations(id), item_name TEXT, uom VARCHAR(20), quantity NUMERIC, unit_price NUMERIC);

INSERT INTO entities (name, code) VALUES ('CETENA GROUP', 'CENTENA'), ('VINGROUP', 'VIN');
INSERT INTO domains (code, name) VALUES ('PUR', 'Purchasing'), ('FIN', 'Finance'), ('HR', 'Human Resources'), ('WHS', 'Warehouse');
INSERT INTO roles (name, power_level) VALUES ('SUPER_ADMIN', 100), ('COMPANY_ADMIN', 50), ('STAFF', 10);
INSERT INTO users (username, entity_id, role_id, default_domain_id) VALUES ('god_mode', NULL, 1, NULL), ('niv', 1, 3, 1), ('vin_boss', 2, 2, NULL);
INSERT INTO dna_kernel (entity_id, domain_id, ui_config) VALUES
(1, 1, '{"prefix": "admin@cetena1: ", "primary_color": "#16a34a"}'),
(1, 2, '{"prefix": "fin@cetena: ", "primary_color": "#eab308"}'),
(1, 3, '{"prefix": "hr@cetena: ", "primary_color": "#ec4899"}'),
(2, 1, '{"prefix": "root@vin-internal: ", "primary_color": "#dc2626"}'),
(2, 4, '{"prefix": "whs@vin: ", "primary_color": "#f97316"}');
EOF

# 3. Phục hồi web_dashboard.py
echo "📝 Restoring web_dashboard.py..."
cat <<'EOF' > "$SCRIPTS_DIR/web_dashboard.py"
import os, json, subprocess
from flask import Flask, render_template_string, jsonify, request
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

app = Flask(__name__)
os.environ['PGPASSWORD'] = os.getenv("DB_PASSWORD", "donkihote")

def query_db(sql, params=None):
    json_cmd = ["psql", "-U", "c", "-d", "cSaas", "-A", "-t"]
    if params:
        for i, p in enumerate(params, 1):
            json_cmd.extend(["-v", f"v{i}={p}"])
    json_cmd.extend(["-c", f"SELECT row_to_json(t) FROM ({sql}) t;"])
    try:
        res = subprocess.check_output(json_cmd, timeout=5).decode('utf-8').strip()
        return [json.loads(line) for line in res.split('\n') if line]
    except: return []

@app.route('/')
def index():
    username = request.args.get('u', 'god_mode')
    user_sql = "SELECT u.*, r.power_level, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = :v1"
    user_res = query_db(user_sql, [username])
    if not user_res: return "User Not Found", 403
    user = user_res[0]
    eid = user['entity_id'] if user['entity_id'] else request.args.get('eid', 1)
    did = user['default_domain_id'] if user['default_domain_id'] else request.args.get('did', 1)
    res_dna = query_db("SELECT ui_config FROM dna_kernel WHERE entity_id = :v1 AND domain_id = :v2", [eid, did])
    dna = res_dna[0]['ui_config'] if res_dna else {"prefix": "SYSTEM:", "primary_color": "#444"}
    entities = query_db("SELECT id, name, code FROM entities ORDER BY id")
    domains = query_db("SELECT d.id, d.name, d.code FROM domains d JOIN dna_kernel k ON d.id = k.domain_id WHERE k.entity_id = :v1 ORDER BY d.id", [eid])
    curr_dom_code = next((d['code'].lower() for d in domains if str(d['id']) == str(did)), 'pur')

    return render_template_string("""
<!DOCTYPE html><html><head><script src="https://cdn.tailwindcss.com"></script>
<style>:root { --primary: {{ dna.primary_color }}; }
body { font-family: 'JetBrains Mono', monospace; background: #080808; color: #d1d1d1; }
.bc-text { cursor: pointer; color: var(--primary); font-weight: bold; }
.bc-caret { cursor: pointer; padding: 0 5px; color: #333; position: relative; }
.dropdown { position: absolute; top: 100%; left: 0; background: #0f0f0f; border: 1px solid #222; min-width: 200px; display: none; z-index:100; }
.bc-caret:hover .dropdown { display: block; }
.dropdown div { padding: 10px; font-size: 11px; border-bottom: 1px solid #1a1a1a; }
.dropdown div:hover { background: #1a1a1a; color: var(--primary); }</style></head>
<body class="p-10"><div class="flex justify-between border-b border-gray-900 pb-5 mb-10">
<div class="flex items-center text-[11px] uppercase tracking-tight">
<div class="relative"><span class="bc-text">{{ dna.prefix }}</span>{% if user.power_level >= 100 %}<span class="bc-caret">▼<div class="dropdown">{% for ent in entities %}<div onclick="location.href='/?u={{user.username}}&eid={{ent.id}}&did={{did}}'">{{ ent.code }}</div>{% endfor %}</div></span>{% endif %}</div>
<span class="mx-2 text-gray-800">/</span>
<div class="relative"><span class="bc-text">{{ curr_dom_code }}</span>{% if user.power_level >= 50 %}<span class="bc-caret">▼<div class="dropdown">{% for dom in domains %}<div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{dom.id}}'">{{ dom.code }}</div>{% endfor %}</div></span>{% endif %}</div>
</div><div class="text-[9px] text-gray-700 uppercase tracking-widest text-right">cSaas v0.15 Factory</div></div>
<div class="max-w-4xl">
<div class="text-[10px] text-gray-600 mb-2 italic text-sm">USER: {{ user.username }} (Power: {{ user.power_level }})</div>
<h2 class="text-3xl font-bold opacity-20 tracking-[0.5em] mb-10 uppercase">{{ curr_dom_code }}</h2>
<div class="p-10 border border-gray-900 bg-white/5 rounded italic text-gray-500 text-sm">Core Active. Waiting for Vendor Data.</div>
</div></body></html>""", dna=dna, eid=eid, did=did, entities=entities, domains=domains, curr_dom_code=curr_dom_code, user=user)

if __name__ == '__main__': app.run(port=5001)
EOF

# 4. Phục hồi standardize_with_ai.py
echo "📝 Restoring standardize_with_ai.py..."
cat <<'EOF' > "$SCRIPTS_DIR/standardize_with_ai.py"
import pandas as pd
import json, os, sys, re, shutil, requests, subprocess, time
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ARCHIVE_DIR = os.path.join(BASE_DIR, "input_files/vendor_quotations/archive")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
os.environ['PGPASSWORD'] = os.getenv("DB_PASSWORD", "donkihote")

def query_db(sql, params=None):
    cmd = ["psql", "-U", "c", "-d", "cSaas", "-A", "-t"]
    if params:
        for i, p in enumerate(params, 1): cmd.extend(["-v", f"v{i}={p}"])
    cmd.extend(["-c", f"SELECT row_to_json(t) FROM ({sql}) t;"])
    try:
        res = subprocess.check_output(cmd, timeout=15).decode('utf-8').strip()
        return [json.loads(l) for l in res.split('\n') if l]
    except: return []

def call_gemini(prompt):
    if not GEMINI_API_KEY: return None
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}}
        res = requests.post(GEMINI_URL, json=payload, timeout=30)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(re.sub(r"```json\s?|\s?```", "", text).strip())
    except: pass
    return None

def extract_pdf_text(path):
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "".join([p.extract_text() or "" for p in pdf.pages[:5]])
    except: return "PDF Reader Error"

def process_file(file_path, entity_id=1, domain_id=1):
    filename = os.path.basename(file_path)
    print(f"🔍 Processing: {filename}")
    content = extract_pdf_text(file_path) if file_path.lower().endswith('.pdf') else pd.read_excel(file_path).head(40).to_string()
    prompt = f"Extract vendor_name, quote_no, items(name, uom, qty, price) from: {content[:10000]}"
    ai_res = call_gemini(prompt)
    if not ai_res: return

    v_sql = "WITH upsert AS (INSERT INTO vendors (vendor_name, entity_id) VALUES (:'v1', :v2) ON CONFLICT (vendor_name, entity_id) DO UPDATE SET vendor_name = EXCLUDED.vendor_name RETURNING id) SELECT id FROM upsert;"
    v_id = (query_db(v_sql, [ai_res.get('vendor_name', 'Unknown'), entity_id]) or [{}])[0].get('id')

    if v_id:
        q_no = ai_res.get('quote_no', filename)
        q_id = (query_db("INSERT INTO quotations (vendor_id, entity_id, quote_number, status) VALUES (:v1, :v2, :'v3', 'Draft') RETURNING id", [v_id, entity_id, q_no]) or [{}])[0].get('id')
        if q_id:
            for itm in ai_res.get('items', []):
                query_db("INSERT INTO quotation_items (quotation_id, item_name, uom, quantity, unit_price) VALUES (:v1, :'v2', :'v3', :v4, :v5)", [q_id, itm.get('name'), itm.get('uom'), itm.get('qty', 0), itm.get('price', 0)])

    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
    shutil.move(file_path, os.path.join(ARCHIVE_DIR, filename))
    print(f"✅ Success: {filename}")

if __name__ == "__main__":
    IN_DIR = os.path.join(BASE_DIR, "input_files/vendor_quotations")
    if os.path.exists(IN_DIR):
        for f in os.listdir(IN_DIR):
            if f.lower().endswith(('.xlsx', '.pdf')): process_file(os.path.join(IN_DIR, f))
EOF

chmod +x "$SCRIPTS_DIR/web_dashboard.py" "$SCRIPTS_DIR/standardize_with_ai.py"
echo "✅ SUCCESS: Factory restored and synchronized."
echo "🚀 Run: ./venv/bin/python app/scripts/web_dashboard.py"
