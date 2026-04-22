import pandas as pd
import json, os, sys, re, shutil, requests, time
import psycopg2
from psycopg2.extras import RealDictCursor
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ARCHIVE_DIR = os.path.join(BASE_DIR, "input_files/vendor_quotations/archive")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

DB_CONFIG = {
    "dbname": "cSaas",
    "user": "c",
    "password": os.getenv("DB_PASSWORD", "donkihote"),
    "host": "localhost",
    "port": "5432"
}

def query_db(sql, params=None):
    # Support :v1 style placeholders by converting them to %s
    sql = re.sub(r':v(\d+)', '%s', sql)
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        if cur.description:
            return [dict(row) for row in cur.fetchall()]
        conn.commit()
        return []
    except Exception as e:
        print(f"Database Error: {e}")
        return []
    finally:
        if conn: conn.close()

def call_gemini(prompt):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not found.")
        return None
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }
        res = requests.post(GEMINI_URL, json=payload, timeout=30)
        if res.status_code == 200:
            candidates = res.json().get('candidates', [])
            if not candidates: return None
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return json.loads(re.sub(r"```json\s?|\s?```", "", text).strip())
        else:
            print(f"Gemini API Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Gemini call failed: {e}")
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

    content = ""
    if file_path.lower().endswith('.pdf'):
        content = extract_pdf_text(file_path)
    else:
        content = pd.read_excel(file_path).head(100).to_string()

    prompt = f"""
    Extract data from this quotation document into JSON format.
    Fields: vendor_name, quote_no, items (list of: name, uom, qty, price).
    Document Content:
    {content[:15000]}
    """

    ai_res = call_gemini(prompt)
    if not ai_res:
        print(f"⚠️ Failed to extract data from {filename}")
        return

    # Use %s or :v1 style based on query_db replacement logic
    v_name = ai_res.get('vendor_name', 'Unknown')
    v_sql = "INSERT INTO vendors (vendor_name, entity_id) VALUES (:v1, :v2) ON CONFLICT (vendor_name, entity_id) DO UPDATE SET vendor_name = EXCLUDED.vendor_name RETURNING id;"
    v_id_res = query_db(v_sql, [v_name, entity_id])
    v_id = v_id_res[0].get('id') if v_id_res else None

    if v_id:
        q_no = ai_res.get('quote_no') or filename
        q_id_res = query_db("INSERT INTO quotations (vendor_id, entity_id, quote_number, status) VALUES (:v1, :v2, :v3, 'Draft') RETURNING id", [v_id, entity_id, q_no])
        q_id = q_id_res[0].get('id') if q_id_res else None

        if q_id:
            for itm in ai_res.get('items', []):
                query_db("INSERT INTO quotation_items (quotation_id, item_name, uom, quantity, unit_price) VALUES (:v1, :v2, :v3, :v4, :v5)",
                         [q_id, itm.get('name'), itm.get('uom'), itm.get('qty', 0), itm.get('price', 0)])
            print(f"✅ Success: {filename} -> DB")
        else:
            print(f"❌ Failed to create quotation record for {filename}")
    else:
        print(f"❌ Failed to identify/create vendor for {filename}")

    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
    shutil.move(file_path, os.path.join(ARCHIVE_DIR, filename))

if __name__ == "__main__":
    IN_DIR = os.path.join(BASE_DIR, "input_files/vendor_quotations")
    if os.path.exists(IN_DIR):
        for f in os.listdir(IN_DIR):
            if f.lower().endswith(('.xlsx', '.pdf')): process_file(os.path.join(IN_DIR, f))
