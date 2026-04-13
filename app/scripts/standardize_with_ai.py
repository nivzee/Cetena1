import pandas as pd
import json
import os
import sys
import psycopg2
from psycopg2.extras import Json
import anthropic
import re
import difflib

# CẤU HÌNH KẾT NỐI DATABASE
DB_CONFIG = {
    "dbname": "purchasing",
    "user": "c",
}

# CẤU HÌNH CLAUDE API
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG)

def find_header_row(file_path):
    try:
        df_top = pd.read_excel(file_path, header=None, nrows=20)
        keywords = ['item', 'description', 'price', 'unit', 'qty', 'tên hàng', 'đơn giá', 'số lượng', 'quotation']
        for i, row in df_top.iterrows():
            row_str = " ".join([str(val).lower() for val in row.values if not pd.isna(val)])
            if any(key in row_str for key in keywords):
                return i
        return 0
    except: return 0

def ask_claude_for_mapping(preview_csv):
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=1000,
            temperature=0,
            system="Bạn chỉ trả về JSON mapping.",
            messages=[{"role": "user", "content": f"Map CSV này về chuẩn: [product_name, uom, quantity, unit_price, note].\n{preview_csv}"}]
        )
        response_text = message.content[0].text
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")
        return json.loads(response_text[start:end])
    except Exception as e:
        return {
            "mapping": {
                "ITEM": "product_name",
                "TOTAL QTY": "quantity",
                "QUOTATION 01": "price_1",
                "QUOTATION 02": "price_2",
                "QUOTATION 03": "price_3",
                "ITEM.1": "uom"
            },
            "skip_rows": -1
        }

def get_or_create_product(cur, product_name, uom):
    """Tìm product_id theo tên (Fuzzy Matching). Nếu chưa có thì tạo mới."""
    # 1. Thử khớp chính xác trước để tối ưu tốc độ
    cur.execute(
        "SELECT product_id FROM products_master WHERE product_name = %s",
        (product_name,)
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # 2. Fuzzy Matching sử dụng difflib nếu không khớp chính xác
    cur.execute("SELECT product_id, product_name FROM products_master")
    all_products = cur.fetchall()
    if all_products:
        names = [p[1] for p in all_products]
        matches = difflib.get_close_matches(product_name, names, n=1, cutoff=0.8)
        if matches:
            matched_name = matches[0]
            for pid, pname in all_products:
                if pname == matched_name:
                    print(f"✨ Fuzzy Match: '{product_name}' -> '{pname}'")
                    return pid

    # 3. Tạo mới nếu không tìm thấy hoặc không khớp đủ tốt
    cur.execute(
        "INSERT INTO products_master (product_name, uom) VALUES (%s, %s) RETURNING product_id",
        (product_name, uom if uom else None)
    )
    return cur.fetchone()[0]

def clean_price(price_val):
    if pd.isna(price_val) or str(price_val).strip() == "": return None
    s = re.sub(r'[^\d.,]', '', str(price_val))
    if not s: return None
    try:
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'): s = s.replace('.', '').replace(',', '.')
            else: s = s.replace(',', '')
        elif ',' in s and len(s.split(',')[-1]) <= 2: s = s.replace(',', '.')
        else: s = s.replace(',', '')
        return float(s)
    except: return None

def process_file(file_path):
    if not os.path.exists(file_path): return
    print(f"🔍 Đang xử lý: {os.path.basename(file_path)}")
    
    skip_rows = find_header_row(file_path)
    df_raw = pd.read_excel(file_path, skiprows=skip_rows)
    df_raw.columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in df_raw.columns]

    mapping_config = ask_claude_for_mapping(df_raw.head(10).to_csv())

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO raw_documents (file_name, file_path, mapping_used, ai_processed, process_status) VALUES (%s, %s, %s, False, 'processing') RETURNING file_id",
                (os.path.basename(file_path), file_path, Json(mapping_config)))
    file_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Ánh xạ cột động — mỗi std_name chỉ nhận cột đầu tiên khớp
        final_map = {}
        assigned_std = set()
        for raw_col in df_raw.columns:
            for map_key, std_name in mapping_config['mapping'].items():
                if map_key.lower() in raw_col.lower() and std_name not in assigned_std:
                    final_map[raw_col] = std_name
                    assigned_std.add(std_name)
                    break

        df_final = df_raw.rename(columns=final_map)

        count = 0
        for _, row in df_final.iterrows():
            p_name = str(row.get('product_name', '')).strip()
            if not p_name or p_name.lower() in ['nan', 'chemicals', 'item']: continue

            # Lấy giá từ bất kỳ cột price nào có dữ liệu
            prices = [row.get('price_1'), row.get('price_2'), row.get('price_3'), row.get('unit_price')]
            price_clean = None
            for p in prices:
                price_clean = clean_price(p)
                if price_clean is not None: break

            if price_clean is not None:
                uom_raw = str(row.get('uom', '')).strip()
                uom_val = (uom_raw.splitlines()[0].strip()[:50] if uom_raw else None) or None
                product_id = get_or_create_product(cur, p_name, uom_val)
                qty = clean_price(row.get('quantity'))
                amount = round(price_clean * qty, 2) if qty is not None else None
                note_val = str(row.get('note', '')).strip() or None
                cur.execute(
                    "INSERT INTO quotation_details (file_id, product_id, unit_price, quantity, amount, note) VALUES (%s, %s, %s, %s, %s, %s)",
                    (file_id, product_id, price_clean, qty, amount, note_val)
                )
                count += 1

        print(f"🎉 Kết quả: Đã nạp {count} dòng vào Database.")
        cur.execute("UPDATE raw_documents SET process_status = 'processed', ai_processed = True WHERE file_id = %s", (file_id,))
        conn.commit()

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        conn.rollback()
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1: process_file(sys.argv[1])
