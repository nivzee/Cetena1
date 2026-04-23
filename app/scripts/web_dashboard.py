import os, json, shutil, subprocess
from flask import Flask, render_template_string, jsonify, request, redirect, url_for
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2.extras import RealDictCursor
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cetena_secret'
# Bỏ async_mode='threading' để Socket.IO tự chọn eventlet cho ổn định
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    print(f"--- Browser Connected: {request.sid}")

@socketio.on('dna_event')
def handle_dna_event(data):
    print(f"!!! RECEIVED FROM WATCHDOG: {data}")
    # socketio.emit mặc định sẽ gửi tới tất cả các trình duyệt đang mở
    socketio.emit('dashboard_notify', data)

@socketio.on('test_trigger')
def handle_test(data):
    print("!!! TEST BUTTON PRESSED")
    socketio.emit('dashboard_notify', {'message': 'Test Connection Successful! 🚀'})
DB_CONFIG = {
    "dbname": "cSaas", "user": "c", "password": os.getenv("DB_PASSWORD", "donkihote"), "host": "localhost", "port": "5432"
}

def query_db(sql, params=None):
    import re
    sql = re.sub(r':v(\d+)', '%s', sql)
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        res = []
        if cur.description:
            res = [dict(row) for row in cur.fetchall()]
        conn.commit() # LUÔN LUÔN COMMIT
        return res
    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Error: {e}"); return []
    finally:
        if conn: conn.close()

@app.route('/')
def index():
    username = request.args.get('u', 'god_mode')
    user_res = query_db("SELECT u.*, r.power_level, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s", [username])
    if not user_res: return "User Not Found", 403
    user = user_res[0]
    is_sa = user['power_level'] >= 100

    # Load Shortcuts
    shortcuts = query_db("SELECT * FROM shortcuts WHERE user_id = %s ORDER BY slot_index", [user['id']])
    shortcut_json = json.dumps(shortcuts)

    # 1. Entities
    entities = query_db("SELECT id, name, code FROM entities ORDER BY id")
    eid = request.args.get('eid')
    if eid == 'None' or eid == '': eid = None
    if not eid and entities: eid = str(entities[0]['id'])
    curr_ent = next((e for e in entities if str(e['id']) == str(eid)), {}) if eid else {}
    ent_code = curr_ent.get('code', '')

    # 2. Domains
    domains = []
    if eid and str(eid).isdigit():
        domains = query_db("SELECT d.id, d.name, d.code FROM domains d JOIN dna_kernel k ON d.id = k.domain_id WHERE k.entity_id = %s ORDER BY d.id", [eid])
    did = request.args.get('did')
    if did == 'None' or did == '': did = None
    if not did and domains: did = str(domains[0]['id'])
    curr_dom = next((d for d in domains if str(d['id']) == str(did)), {}) if did else {}
    dom_code = curr_dom.get('code', '')

    # 3. Breadcrumb & Menu Logic (DB-BASED)
    mode = request.args.get('mode', 'data') # 'data' hoặc 'dna'
    sid_path = request.args.get('sid', '').strip('/')
    sub_parts = [p for p in sid_path.split('/') if p]
    breadcrumb_subs = []
    pending_options = []
    path_nodes = []
    curr_id = None
    base_path = f"app/{ent_code}/{dom_code}" if ent_code and dom_code else "app"

    if eid and did and str(eid).isdigit() and str(did).isdigit():
        e_int, d_int = int(eid), int(did)
        # 1. ĐỒNG BỘ QUÉT Ổ ĐĨA VÀO DATABASE (Đã sửa lỗi Commit)
        def sync_disk_to_db(path, p_id=None):
            if not os.path.exists(path): return
            for entry in os.scandir(path):
                # Không quét thư mục DNA vào database cấu trúc dữ liệu
                if entry.is_dir() and not entry.name.startswith('.') and entry.name != 'DNA':
                    # So khớp không phân biệt hoa thường
                    if p_id is None:
                        res = query_db("SELECT id FROM dna_structure WHERE UPPER(code) = UPPER(%s) AND parent_id IS NULL AND entity_id = %s AND domain_id = %s", [entry.name, e_int, d_int])
                    else:
                        res = query_db("SELECT id FROM dna_structure WHERE UPPER(code) = UPPER(%s) AND parent_id = %s", [entry.name, p_id])

                    if not res:
                        res_ins = query_db("INSERT INTO dna_structure (entity_id, domain_id, parent_id, code, name) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                                         [e_int, d_int, p_id, entry.name, entry.name])
                        new_id = res_ins[0]['id'] if res_ins else None
                    else:
                        new_id = res[0]['id']

                    if new_id: sync_disk_to_db(entry.path, new_id)

        sync_disk_to_db(base_path)

        # 2. PHÂN GIẢI ĐƯỜNG DẪN HIỆN TẠI
        path_nodes = []
        curr_id = None
        for part in sub_parts:
            if curr_id is None:
                res = query_db("SELECT id, code FROM dna_structure WHERE UPPER(code) = UPPER(%s) AND parent_id IS NULL AND entity_id = %s AND domain_id = %s", [part, e_int, d_int])
            else:
                res = query_db("SELECT id, code FROM dna_structure WHERE UPPER(code) = UPPER(%s) AND parent_id = %s", [part, curr_id])
            if res:
                curr_id = res[0]['id']
                path_nodes.append(res[0])
            else:
                curr_id = -1; break

        # FIX: Nếu đường dẫn (sid) không tồn tại trong Domain này, reset về gốc để tránh "ghost path" từ domain cũ
        if curr_id == -1:
            sid_path = ""
            curr_id = None
            path_nodes = []
            sub_parts = []

        # 3. WATERFALL REDIRECT: Điều khiển qua tham số 'wf'
        target_sid = sid_path
        wf_enabled = request.args.get('wf', '0') == '1' # Mặc định là OFF (0)

        if wf_enabled and mode != 'dna' and not request.args.get('organ'):
            wf_id = curr_id
            while True:
                if wf_id is None:
                    f = query_db("SELECT id, code FROM dna_structure WHERE parent_id IS NULL AND entity_id = %s AND domain_id = %s ORDER BY id LIMIT 1", [e_int, d_int])
                elif wf_id != -1:
                    f = query_db("SELECT id, code FROM dna_structure WHERE parent_id = %s ORDER BY id LIMIT 1", [wf_id])
                else: f = None

                if f:
                    wf_id = f[0]['id']
                    target_sid = (target_sid + '/' + f[0]['code']).strip('/')
                else: break

        if target_sid != sid_path:
            return redirect(url_for('index', u=user['username'], eid=eid, did=did, sid=target_sid, mode=mode, organ=request.args.get('organ'), wf='1'))

    # 4. DỰNG BREADCRUMB UI
    breadcrumb_subs = []
    acc = ""
    # Tránh lỗi khi path_nodes trống (trường hợp Entity mới chưa có Domain/Structure)
    parent_ids = [None] + [n['id'] for n in path_nodes[:-1]] if path_nodes else [None]
    for i, part in enumerate(sub_parts):
        if i >= len(parent_ids): break # Safety break
        p_id = parent_ids[i]

        # Đảm bảo e_int và d_int tồn tại trước khi query
        if not eid or not did: break
        e_int_val, d_int_val = int(eid), int(did)

        if p_id is None:
            sibs = query_db("SELECT code FROM dna_structure WHERE parent_id IS NULL AND entity_id = %s AND domain_id = %s", [e_int_val, d_int_val])
        else:
            sibs = query_db("SELECT code FROM dna_structure WHERE parent_id = %s", [p_id])
        acc = (acc + '/' + part) if acc else part

        # Kiểm tra sự tồn tại vật lý
        dna_path = os.path.join(f"app/{ent_code}/DNA/{dom_code}", acc)
        has_dna_zone = os.path.exists(dna_path)
        has_reified = os.path.exists(os.path.join(dna_path, "Script"))

        breadcrumb_subs.append({
            "name": part,
            "path": acc,
            "options": sorted(list(set([s['code'] for s in sibs]))),
            "has_dna_zone": has_dna_zone,
            "has_dna": has_reified
        })

    # Kiểm tra DNA zone cho Entity và Domain
    has_ent_dna_zone = os.path.exists(f"app/{ent_code}/DNA") if ent_code else False
    has_dom_dna_zone = os.path.exists(f"app/{ent_code}/DNA/{dom_code}") if (ent_code and dom_code) else False

    # Kiểm tra Reified (Có nội tạng)
    has_ent_reified = os.path.exists(os.path.join(f"app/{ent_code}/DNA", "Script")) if ent_code else False
    has_dom_reified = os.path.exists(os.path.join(f"app/{ent_code}/DNA/{dom_code}", "Script")) if (ent_code and dom_code) else False

    # 5. LỰA CHỌN TIẾP THEO (PENDING)
    next_items = []
    if eid and did:
        e_int_val, d_int_val = int(eid), int(did)
        if curr_id is None:
            next_items = query_db("SELECT code FROM dna_structure WHERE parent_id IS NULL AND entity_id = %s AND domain_id = %s", [e_int_val, d_int_val])
        elif curr_id != -1:
            next_items = query_db("SELECT code FROM dna_structure WHERE parent_id = %s", [curr_id])
    pending_options = sorted(list(set([i['code'] for i in next_items])))

    # 6. DNA ORGANS & FILE LISTING
    dna_organs = []
    organ_files = []
    curr_organ = request.args.get('organ')

    if mode == 'dna' and eid and did:
        # Kiểm tra sự tồn tại của 4 nội tạng trong DNA zone
        dna_path = os.path.join(f"app/{ent_code}/DNA/{dom_code}", sid_path)

        if curr_organ:
            # List files in the selected organ
            target_path = os.path.join(dna_path, curr_organ)
            if os.path.exists(target_path):
                if os.path.isdir(target_path):
                    for entry in os.scandir(target_path):
                        if entry.is_file():
                            organ_files.append({"name": entry.name, "size": entry.stat().st_size})
                else:
                    # If it's a file (shouldn't happen with our organ structure but for safety)
                    organ_files.append({"name": os.path.basename(target_path), "size": os.path.getsize(target_path)})
        else:
            organs = [
                {"name": "Standardized", "path": "Standardized", "icon": "fa-file-csv", "color": "#4ade80"},
                {"name": "Processed", "path": "Processed", "icon": "fa-archive", "color": "#9ca3af"},
                {"name": "Script", "path": "Script", "icon": "fa-code", "color": "#facc15"},
                {"name": "Script/Template", "path": "Script/Template", "icon": "fa-fill-drip", "color": "#60a5fa"}
            ]
            for org in organs:
                if os.path.exists(os.path.join(dna_path, org['path'])):
                    dna_organs.append(org)

    dna = {"prefix": "SYSTEM:", "primary_color": "#00ff00"}
    if eid and did:
        res_dna = query_db("SELECT ui_config FROM dna_kernel WHERE entity_id = %s AND domain_id = %s", [eid, did])
        if res_dna: dna = res_dna[0]['ui_config']

    return render_template_string("""
<!DOCTYPE html><html><head><script src="https://cdn.tailwindcss.com">function deleteItem(level, id, code) {
    if (!confirm(`Are you sure you want to DELETE ${level.toUpperCase()} [${code}]? This will remove ALL physical files and DB records!`)) return;

    fetch('/delete_dna', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            level: level,
            id: id,
            eid: '{{ eid }}',
            did: '{{ did }}'
        })
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            const params = new URLSearchParams(window.location.search);
            const user = params.get('u') || 'god_mode';
            const curEid = params.get('eid');
            const curDid = params.get('did');
            const curSid = params.get('sid') || '';

            if (level === 'sub') {
                // Nếu xóa chính thư mục đang đứng hoặc cha của nó
                if (curSid === id || curSid.startsWith(id + '/')) {
                    location.href = `/?u=${user}&eid=${curEid}&did=${curDid}&sid=${data.new_sid}`;
                } else {
                    location.reload();
                }
            } else if (level === 'entity' && String(id) === String(curEid)) {
                location.href = `/?u=${user}`;
            } else if (level === 'domain' && String(id) === String(curDid)) {
                location.href = `/?u=${user}&eid=${curEid}`;
            } else {
                location.reload();
            }
        } else {
            alert('Error: ' + data.message);
        }
    });
}
</script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
<style>
:root { --primary: {{ dna.primary_color }}; }
body { font-family: 'JetBrains Mono', monospace; background: #080808; color: #eee; }
.bc-item { display: flex; flex-direction: column; align-items: center; position: relative; margin: 0 2px; }
.bc-main { display: flex; align-items: center; min-height: 20px; }
.bc-sep { font-size: 10px; color: #222; margin: 0 4px; display: flex; align-items: center; }
.bc-connector { color: #333; font-size: 11px; letter-spacing: -1px; margin-left: 8px; cursor: pointer; transition: 0.3s; display: flex; align-items: center; gap: 5px; }
.bc-connector:hover { color: var(--primary); text-shadow: 0 0 8px var(--primary); }
.bc-organ-caret { cursor: pointer; color: #00ff00; font-size: 10px; line-height: 1; margin-top: -4px; opacity: 0.7; transition: 0.2s; height: 10px; width: 100%; text-align: center; }
.bc-organ-caret:hover { opacity: 1; text-shadow: 0 0 5px #00ff00; }
.organ-dropdown { position: absolute; top: 100%; left: 50%; transform: translateX(-50%); background: #0a0a0a; border: 1px solid #1a1a1a; min-width: 140px; display: none; z-index:110; box-shadow: 0 5px 20px rgba(0,255,0,0.2); }
.bc-item:hover .organ-dropdown { display: block; }
.organ-dropdown div { padding: 8px 12px; font-size: 10px; border-bottom: 1px solid #111; color: #888; display: flex; align-items: center; gap: 8px; }
.organ-dropdown div:hover { background: #111; color: #00ff00; }
.bc-text { cursor: pointer; color: #fff; font-weight: bold; text-shadow: 0 0 5px rgba(255,255,255,0.2); transition: 0.2s; }
.bc-text:hover { color: var(--primary); }
.bc-caret { cursor: pointer; padding: 0 4px; color: #444; font-size: 8px; transition: 0.2s; display: flex; align-items: center; height: 100%; position: relative; }
.bc-caret:hover { color: #fff; }
.dropdown { position: absolute; top: 100%; left: 0; background: #111; border: 1px solid #333; min-width: 180px; display: none; z-index:100; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }
.bc-caret:hover .dropdown { display: block; }
.dropdown div { padding: 10px 15px; font-size: 11px; border-bottom: 1px solid #222; transition: all 0.2s; color: #aaa; display: flex; justify-content: space-between; align-items: center; cursor:pointer; }
.dropdown div:hover { background: #222; color: #fff; }
.plus-btn { color: #00ff00; cursor: pointer; font-size: 16px; padding: 0 10px; transition: all 0.3s; font-weight: bold; }
.plus-btn:hover { transform: scale(1.3); text-shadow: 0 0 10px #00ff00; }
.symbol-btn { color: #555; cursor: pointer; font-size: 12px; padding: 0 8px; transition: all 0.3s; font-weight: bold; }
.symbol-btn:hover { color: #fff; transform: scale(1.2); }
.shortcut-slot { width: 12px; height: 12px; border: 1px solid #555; cursor: pointer; transition: 0.2s; }
.shortcut-slot.active { background: var(--primary); border-color: var(--primary); box-shadow: 0 0 8px var(--primary); }
#factory-panel, #shortcut-panel, #settings-panel { display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:#111; border:1px solid #333; padding:20px; z-index:1000; width:400px; box-shadow: 0 0 50px rgba(0,0,0,1); }
.overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); z-index:999; }
.hidden { display: none !important; }
</style></head>
<body class="px-10 pb-10 pt-0">
<!-- NOTIFICATION TOAST -->
<div id="toast-container" class="fixed top-5 right-5 z-[2000] space-y-2"></div>
<div id="factory-panel">
    <div id="panel-title" class="text-[10px] text-green-500 mb-4 tracking-widest uppercase text-center">Factory: Initialize DNA</div>
    <div class="mb-4 text-[9px] text-gray-500 uppercase text-center border-b border-gray-800 pb-2">Target: <span id="factory-context" class="text-white">---</span></div>
    <div class="space-y-3">
        <div>
            <label class="text-[8px] text-gray-500 uppercase">Folder Name</label>
            <input id="f-name" class="bg-black border border-gray-800 p-2 w-full text-xs text-white outline-none focus:border-green-500" placeholder="e.g. Request 2026">
        </div>
        <div>
            <label class="text-[8px] text-gray-500 uppercase">System Code (Folder ID)</label>
            <input id="f-code" class="bg-black border border-gray-800 p-2 w-full text-xs text-white outline-none focus:border-green-500" placeholder="e.g. 2026">
        </div>
        <div class="flex items-center gap-2 py-2">
            <input type="checkbox" id="f-template" class="accent-green-500 w-3 h-3" onchange="toggleTemplatePanel()">
            <label for="f-template" class="text-[9px] text-gray-400 uppercase cursor-pointer">Apply Standard DNA Template (temp, script...)</label>
        </div>

        <!-- Template Config Panel (Hidden by default) -->
        <div id="template-config" class="hidden space-y-3 border-l-2 border-green-900 pl-4 py-2 bg-black/50">
            <div>
                <label class="text-[7px] text-gray-500 uppercase">Path for Template File/Folder</label>
                <div class="flex gap-2">
                    <input id="f-path-temp" class="bg-transparent border border-gray-800 p-1 w-full text-[10px] text-gray-300 outline-none" placeholder="/path/to/source/template">
                    <span class="cursor-pointer text-gray-500 hover:text-white" onclick="browsePath('f-path-temp')"><i class="fas fa-folder-open"></i></span>
                </div>
            </div>
            <div>
                <label class="text-[7px] text-gray-500 uppercase">Path for Script File/Folder</label>
                <div class="flex gap-2">
                    <input id="f-path-script" class="bg-transparent border border-gray-800 p-1 w-full text-[10px] text-gray-300 outline-none" placeholder="/path/to/source/script">
                    <span class="cursor-pointer text-gray-500 hover:text-white" onclick="browsePath('f-path-script')"><i class="fas fa-folder-open"></i></span>
                </div>
            </div>
        </div>
    </div>
    <div class="flex justify-end gap-2 mt-6">
        <button onclick="closePanel()" class="text-[9px] uppercase border border-gray-800 px-3 py-1 text-gray-400 hover:bg-gray-900">Cancel</button>
        <button onclick="submitFactory()" class="text-[9px] uppercase bg-green-900 px-4 py-1 text-white hover:bg-green-700 font-bold">Initialize</button>
    </div>
</div>

<div id="settings-panel">
    <div class="text-[10px] text-blue-500 mb-4 tracking-widest uppercase text-center">System Settings</div>
    <div class="space-y-4">
        <div class="flex justify-between items-center bg-black/50 p-3 border border-gray-800">
            <div class="flex flex-col">
                <span class="text-[10px] text-white font-bold uppercase">Waterfall Redirect</span>
                <span class="text-[8px] text-gray-500">Auto-jump to first child directory</span>
            </div>
            {% set is_wf = request.args.get('wf') == '1' %}
            <div class="cursor-pointer text-2xl" onclick="toggleWaterfall()">
                <i class="fas {{ 'fa-toggle-on text-green-500' if is_wf else 'fa-toggle-off text-gray-700' }}"></i>
            </div>
        </div>
        <div class="text-[8px] text-gray-600 italic px-1">Note: This setting is preserved in the URL for this session.</div>
    </div>
    <div class="flex justify-end mt-6">
        <button onclick="closeSettings()" class="text-[9px] uppercase bg-gray-900 px-6 py-2 text-white hover:bg-gray-800">Close</button>
    </div>
</div>

<div class="overlay" onclick="closePanel(); closeShortcut(); closeSettings();"></div>

<!-- BREADCRUMB -->
<div class="flex justify-between border-b border-gray-800 h-12 mb-10 items-center">
<div class="flex items-center text-[12px] uppercase tracking-tight">
    <!-- ENTITY -->
    <div class="bc-item">
        <div class="bc-main">
            <span class="bc-text" style="color:#aaa">{{ user.username }}</span>
            {% set next_mode = 'dna' if mode == 'data' else 'data' %}
            <span class="bc-text mx-2 font-black transition-all duration-300 normal-case"
                  style="color: {{ '#00ff00' if mode == 'dna' else '#555' }}; text-shadow: {{ '0 0 10px #00ff00' if mode == 'dna' else 'none' }}; cursor:pointer;"
                  onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sid_path}}&mode={{next_mode}}'"
                  title="Toggle DNA Mode">
                @{{ 'n' if mode == 'dna' else '' }}
            </span>
            {% if curr_ent.code %}
                <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}&mode={{mode}}'">{{ curr_ent.code }}</span>
                <div class="bc-caret">▼
                    <div class="dropdown">
                        {% for ent in entities %}
                            <div class="group flex justify-between items-center {% if ent.code == curr_ent.code %}bg-gray-900/50{% endif %}">
                                <span class="flex-grow {% if ent.code == curr_ent.code %}text-white font-bold{% endif %}" onclick="location.href='/?u={{user.username}}&eid={{ent.id}}&mode={{mode}}'">{{ ent.code }}</span>
                                {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('entity', '{{ent.id}}', '{{ent.code}}')"></i>{% endif %}
                            </div>
                        {% endfor %}
                        {% if is_sa %}
                            {% if mode == 'dna' %}
                                {% if curr_ent.code %}
                                <div class="font-bold border-t border-gray-800 {% if has_ent_reified %}text-gray-600 opacity-40 pointer-events-none{% else %}text-blue-400{% endif %}" onclick="openPanel('entity', '', '{{curr_ent.code}}', '{{curr_ent.name}}')">
                                    <i class="fas {% if has_ent_reified %}fa-check-circle{% else %}fa-atom{% endif %} mr-2"></i>REIFY NUCLEUS: {{curr_ent.code}}
                                </div>
                                {% endif %}
                            {% else %}
                                <div class="text-green-500 font-bold border-t border-gray-800" onclick="openPanel('entity', '')">+ NEW ENTITY</div>
                            {% endif %}
                        {% endif %}
                    </div>
                </div>
            {% else %}
                <span class="plus-btn" onclick="openPanel('entity', '')">+</span>
            {% endif %}
        </div>
        {% if mode == 'dna' and has_ent_dna_zone %}
        <div class="bc-organ-caret">▾
            <div class="organ-dropdown">
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&mode=dna&organ=Standardized'"><i class="fas fa-file-csv w-4"></i> Standardized</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&mode=dna&organ=Processed'"><i class="fas fa-archive w-4"></i> Processed</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&mode=dna&organ=Script'"><i class="fas fa-code w-4"></i> Script</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&mode=dna&organ=Template'"><i class="fas fa-fill-drip w-4"></i> Template</div>
            </div>
        </div>
        {% endif %}
    </div>

    {% if curr_ent.code %}
    <span class="mx-2 text-gray-600 font-bold">/</span>
    <div class="bc-item">
        <div class="bc-main">
            {% if curr_dom.code %}
                <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&mode={{mode}}'">{{ curr_dom.code }}</span>
                <div class="bc-caret">▼
                    <div class="dropdown">
                        {% for dom in domains %}
                            <div class="group flex justify-between items-center {% if dom.code == curr_dom.code %}bg-gray-900/50{% endif %}">
                                <span class="flex-grow {% if dom.code == curr_dom.code %}text-white font-bold{% endif %}" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{dom.id}}&mode={{mode}}'">{{ dom.code }}</span>
                                {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('domain', '{{dom.id}}', '{{dom.code}}')"></i>{% endif %}
                            </div>
                        {% endfor %}
                        {% if is_sa %}
                            {% if mode == 'dna' %}
                                {% if curr_dom.code %}
                                <div class="font-bold border-t border-gray-800 {% if has_dom_reified %}text-gray-600 opacity-40 pointer-events-none{% else %}text-blue-400{% endif %}" onclick="openPanel('domain', '', '{{curr_dom.code}}', '{{curr_dom.name}}')">
                                    <i class="fas {% if has_dom_reified %}fa-check-circle{% else %}fa-atom{% endif %} mr-2"></i>REIFY NUCLEUS: {{curr_dom.code}}
                                </div>
                                {% endif %}
                            {% else %}
                                <div class="text-green-500 font-bold border-t border-gray-800" onclick="openPanel('domain', '')">+ NEW DOMAIN</div>
                            {% endif %}
                        {% endif %}
                    </div>
                </div>
            {% else %}
                <span class="plus-btn" onclick="openPanel('domain', '')">+</span>
            {% endif %}
        </div>
        {% if mode == 'dna' and has_dom_dna_zone %}
        <div class="bc-organ-caret">▾
            <div class="organ-dropdown">
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&mode=dna&organ=Standardized'"><i class="fas fa-file-csv w-4"></i> Standardized</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&mode=dna&organ=Processed'"><i class="fas fa-archive w-4"></i> Processed</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&mode=dna&organ=Script'"><i class="fas fa-code w-4"></i> Script</div>
                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&mode=dna&organ=Template'"><i class="fas fa-fill-drip w-4"></i> Template</div>
            </div>
        </div>
        {% endif %}
    </div>

    {% if curr_dom.code %}
        <!-- RECURSIVE SUBS -->
        {% for sub in breadcrumb_subs %}
        <span class="mx-2 text-gray-600 font-bold">/</span>
        <div class="bc-item">
            <div class="bc-main">
                <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ sub.path }}&mode={{mode}}'">{{ sub.name }}</span>
                <div class="bc-caret">▼
                    <div class="dropdown">
                        {% for opt in sub.options %}
                            {% set parts = sub.path.split('/')[:-1] %}
                            {% set opt_sid = (parts + [opt])|join('/') if parts else opt %}
                            <div class="group flex justify-between items-center {% if opt == sub.name %}bg-gray-900/50{% endif %}">
                                <span class="flex-grow {% if opt == sub.name %}text-white font-bold{% endif %}" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ opt_sid }}&mode={{mode}}'">{{ opt }}</span>
                                {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('sub', '{{ opt_sid }}', '{{ opt }}')"></i>{% endif %}
                            </div>
                        {% endfor %}
                        {% if is_sa %}
                            {% if mode == 'dna' %}
                                <div class="font-bold border-t border-gray-800 {% if sub.has_dna %}text-gray-600 opacity-40 pointer-events-none{% else %}text-blue-400{% endif %}" onclick="openPanel('sub', '{{ '/'.join(sub.path.split('/')[:-1]) }}', '{{sub.name}}', '{{sub.name}}')">
                                    <i class="fas {% if sub.has_dna %}fa-check-circle{% else %}fa-atom{% endif %} mr-2"></i>REIFY NUCLEUS: {{sub.name}}
                                </div>
                            {% else %}
                                <div class="text-green-500 font-bold border-t border-gray-800" onclick="openPanel('sub', '{{ '/'.join(sub.path.split('/')[:-1]) }}')">+ NEW SIBLING</div>
                            {% endif %}
                        {% endif %}
                    </div>
                </div>
            </div>
            {% if mode == 'dna' and sub.has_dna_zone %}
            <div class="bc-organ-caret">▾
                <div class="organ-dropdown">
                    <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sub.path}}&mode=dna&organ=Standardized'"><i class="fas fa-file-csv w-4"></i> Standardized</div>
                    <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sub.path}}&mode=dna&organ=Processed'"><i class="fas fa-archive w-4"></i> Processed</div>
                    <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sub.path}}&mode=dna&organ=Script'"><i class="fas fa-code w-4"></i> Script</div>
                    <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sub.path}}&mode=dna&organ=Template'"><i class="fas fa-fill-drip w-4"></i> Template</div>
                </div>
            </div>
            {% endif %}
        </div>
        {% endfor %}

        <!-- DNA CONNECTOR (--- ▼) -->
        {% if pending_options or is_sa %}
        <div class="bc-item">
            <div class="bc-main">
                <div class="bc-connector">
                    <span>---</span>
                    <div class="bc-caret group">
                        <i class="fas fa-caret-down group-hover:text-white"></i>
                        <div class="dropdown">
                            {% for opt in pending_options %}
                                <div onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ (sid_path + '/' + opt).strip('/') }}&mode={{mode}}'">
                                    <i class="fas fa-folder text-[8px] mr-2 opacity-50"></i> {{ opt }}
                                </div>
                            {% endfor %}
                            {% if is_sa %}
                                <div class="text-green-500 font-bold border-t border-gray-800" onclick="openPanel('sub', '{{ sid_path }}')">
                                    <i class="fas fa-plus-circle mr-2"></i> NEW NUCLEUS
                                </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% endif %}
    {% endif %}
    {% endif %}

    <div class="ml-6 flex items-center gap-2">
        <span class="symbol-btn" onclick="openSettings()" title="Settings"><i class="fas fa-asterisk text-blue-400"></i></span>
        <span class="symbol-btn">:::</span>
        <span class="symbol-btn" onclick="window.history.back()">&lt;&lt;</span>
        <div class="flex gap-1 mx-1 items-center">
            {% for s in shortcuts %}<div class="shortcut-slot active" title="{{ s.url }}" onclick="location.href='{{ s.url }}'"></div>{% endfor %}
            {% if shortcuts|length < 5 %}{% for i in range(5 - shortcuts|length) %}<div class="shortcut-slot"></div>{% endfor %}{% endif %}
        </div>
        <span class="symbol-btn" onclick="window.history.forward()">&gt;&gt;</span>
        <span class="symbol-btn">?</span>
    </div>
</div>
</div>

<div class="max-w-4xl">
    <h2 class="text-4xl font-bold opacity-10 tracking-[1em] mb-10 uppercase">{{ sub_parts[-1] if sub_parts else (curr_dom.code or 'DNA') }}</h2>

    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {% if mode == 'dna' %}
            {% if curr_organ %}
                <div class="col-span-full mb-4 flex justify-between items-center border-b border-gray-900 pb-2">
                    <h3 class="text-xs font-bold text-green-500 uppercase flex items-center gap-2">
                        <i class="fas fa-folder-open"></i> {{ curr_organ }}
                        <span class="text-[10px] text-gray-600 font-normal">/ {{ sid_path }}</span>
                    </h3>
                    <button onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sid_path}}&mode=dna'" class="text-[9px] text-gray-500 hover:text-white uppercase">
                        <i class="fas fa-arrow-left mr-1"></i> Back to Organs
                    </button>
                </div>
                {% for file in organ_files %}
                <div class="bg-gray-900/40 border border-gray-800 p-3 rounded hover:border-green-500 transition-all cursor-pointer flex items-center gap-3 group">
                    <i class="fas fa-file-code text-gray-600 group-hover:text-green-500"></i>
                    <div class="flex flex-col overflow-hidden">
                        <span class="text-[11px] text-gray-300 truncate" title="{{ file.name }}">{{ file.name }}</span>
                        <span class="text-[8px] text-gray-600">{{ (file.size / 1024)|round(1) }} KB</span>
                    </div>
                </div>
                {% endfor %}
                {% if not organ_files %}
                <div class="col-span-full py-20 text-center border-2 border-dashed border-gray-900 rounded-lg">
                    <div class="text-gray-600 text-xs uppercase mb-2">Empty Organ</div>
                    <div class="text-[9px] text-gray-800">No files found in {{ curr_organ }}</div>
                </div>
                {% endif %}
            {% else %}
                {% for org in dna_organs %}
                <div class="bg-gray-900/30 border border-gray-800 p-4 rounded hover:border-blue-500 transition-all cursor-pointer group"
                     onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{sid_path}}&mode=dna&organ={{org.path}}'">
                    <div class="text-[8px] text-gray-500 uppercase mb-2">Internal Organ</div>
                    <div class="flex items-center gap-3">
                        <i class="fas {{ org.icon }} text-xl" style="color: {{ org.color }}"></i>
                        <span class="text-xs font-bold text-gray-200 group-hover:text-white">{{ org.name }}</span>
                    </div>
                </div>
                {% endfor %}
                {% if not dna_organs and sid_path %}
                <div class="col-span-full py-10 text-center border-2 border-dashed border-gray-900 rounded-lg">
                    <div class="text-gray-600 text-xs uppercase mb-4">No DNA Organs found for this node</div>
                    <button onclick="openPanel('sub', '{{ '/'.join(sid_path.split('/')[:-1]) }}', '{{sub_parts[-1]}}', '{{sub_parts[-1]}}')" class="bg-green-900/20 text-green-500 text-[10px] px-4 py-2 rounded hover:bg-green-900/40 transition-all">
                        <i class="fas fa-dna mr-2"></i>REIFY NUCLEUS: {{sub_parts[-1]}}
                    </button>
                </div>
                {% endif %}
            {% endif %}
        {% endif %}

        {% for opt in pending_options %}
            <div class="bg-gray-900/20 border border-gray-900 p-4 rounded hover:bg-gray-900/40 transition-all cursor-pointer group"
                 onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ (sid_path + '/' + opt).strip('/') }}&mode={{mode}}'">
                <div class="text-[8px] text-gray-600 uppercase mb-2">Next Gen</div>
                <div class="flex justify-between items-center">
                    <span class="text-xs font-bold text-gray-400 group-hover:text-white transition-colors">{{ opt }}</span>
                    <i class="fas fa-chevron-right text-[10px] text-gray-800 group-hover:text-green-500 transition-colors"></i>
                </div>
            </div>
        {% endfor %}
    </div>
</div>

<script>
function openSettings() { document.getElementById('settings-panel').style.display = 'block'; document.querySelector('.overlay').style.display = 'block'; }
function closeSettings() { document.getElementById('settings-panel').style.display = 'none'; document.querySelector('.overlay').style.display = 'none'; }

function toggleWaterfall() {
    const params = new URLSearchParams(window.location.search);
    const currentWf = params.get('wf') === '1';
    params.set('wf', currentWf ? '0' : '1');
    location.href = window.location.pathname + '?' + params.toString();
}

let currentLevel = '';
let factoryParentSid = '';

function openPanel(level, pSid, prefillCode = '', prefillName = '') {
    const isDNA = new URLSearchParams(window.location.search).get('mode') === 'dna';
    currentLevel = level;
    factoryParentSid = pSid;

    let actionName = 'NEW ' + level.toUpperCase();
    if (prefillCode) actionName = 'REIFY NUCLEUS';
    else if (isDNA) actionName = 'INIT NUCLEUS';

    document.getElementById('factory-context').innerText = (pSid || 'ROOT') + ' > ' + actionName;

    const codeInput = document.getElementById('f-code');
    const nameInput = document.getElementById('f-name');
    const templateCheckbox = document.getElementById('f-template');

    codeInput.value = prefillCode;
    nameInput.value = prefillName;

    if (prefillCode) {
        templateCheckbox.checked = true; // Auto check if initializing existing
        toggleTemplatePanel();
    }

    document.getElementById('factory-panel').style.display = 'block';
    document.querySelector('.overlay').style.display = 'block';
    codeInput.focus();
}
function closePanel() { document.getElementById('factory-panel').style.display = 'none'; document.querySelector('.overlay').style.display = 'none'; }

function toggleTemplatePanel() {
    const isChecked = document.getElementById('f-template').checked;
    document.getElementById('template-config').classList.toggle('hidden', !isChecked);
}

function browsePath(targetId) {
    fetch('/browse_path', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        if(data.path) document.getElementById(targetId).value = data.path;
    });
}

function submitFactory() {
    const code = document.getElementById('f-code').value.trim().toUpperCase();
    if(!code) return alert('System Code (Folder ID) is required');

    const payload = {
        level: currentLevel,
        name: document.getElementById('f-name').value.trim() || code,
        code: code,
        parent_eid: '{{ eid or "" }}',
        parent_did: '{{ did or "" }}',
        parent_sid: factoryParentSid,
        use_template: document.getElementById('f-template').checked,
        src_temp: document.getElementById('f-path-temp').value.trim(),
        src_script: document.getElementById('f-path-script').value.trim()
    };

    fetch('/initialize_dna', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            const params = new URLSearchParams(window.location.search);
            const mode = params.get('mode') || 'data';
            if (currentLevel === 'sub') {
                const newSid = factoryParentSid ? (factoryParentSid + '/' + code) : code;
                location.href = `/?u={{user.username}}&eid={{eid}}&did={{did}}&sid=${newSid}&mode=${mode}`;
            } else {
                location.href = `/?u={{user.username}}&eid={{eid}}&did={{did}}&mode=${mode}`;
            }
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(err => alert('Network error or server down'));
}
function deleteItem(level, id, code) {
    if (!confirm(`Are you sure you want to DELETE ${level.toUpperCase()} [${code}]? This will remove ALL physical files and DB records!`)) return;

    fetch('/delete_dna', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            level: level,
            id: id,
            eid: '{{ eid }}',
            did: '{{ did }}'
        })
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            const params = new URLSearchParams(window.location.search);
            const user = params.get('u') || 'god_mode';
            const curEid = params.get('eid');
            const curDid = params.get('did');
            const curSid = params.get('sid') || '';

            if (level === 'sub') {
                // Nếu xóa chính thư mục đang đứng hoặc cha của nó
                if (curSid === id || curSid.startsWith(id + '/')) {
                    location.href = `/?u=${user}&eid=${curEid}&did=${curDid}&sid=${data.new_sid}`;
                } else {
                    location.reload();
                }
            } else if (level === 'entity' && String(id) === String(curEid)) {
                location.href = `/?u=${user}`;
            } else if (level === 'domain' && String(id) === String(curDid)) {
                location.href = `/?u=${user}&eid=${curEid}`;
            } else {
                location.reload();
            }
        } else {
            alert('Error: ' + data.message);
        }
    });
}
</script>
</body></html>""", shortcuts=shortcuts, eid=eid, did=did, sid_path=sid_path, breadcrumb_subs=breadcrumb_subs, entities=entities, domains=domains, user=user, is_sa=is_sa, dna=dna, shortcut_json=shortcut_json, curr_ent=curr_ent, curr_dom=curr_dom, sub_parts=sub_parts, pending_options=pending_options, base_path=base_path, mode=mode, dna_organs=dna_organs, curr_organ=curr_organ, organ_files=organ_files, has_ent_dna_zone=has_ent_dna_zone, has_dom_dna_zone=has_dom_dna_zone, has_ent_reified=has_ent_reified, has_dom_reified=has_dom_reified)

@app.route('/browse_path', methods=['POST'])
def browse_path():
    try:
        # Lấy môi trường hiện tại của hệ thống để truyền cho Zenity
        env = os.environ.copy()
        # Đảm bảo DISPLAY được thiết lập (thường là :0)
        if "DISPLAY" not in env: env["DISPLAY"] = ":0"

        # Gọi zenity để chọn file hoặc thư mục
        # Bỏ --directory để cho phép chọn file
        cmd = ['zenity', '--file-selection', '--title=Select Source File or Folder']
        path = subprocess.check_output(cmd, env=env, text=True).strip()
        return jsonify({"path": path})
    except subprocess.CalledProcessError:
        # Người dùng nhấn Cancel
        return jsonify({"path": ""})
    except Exception as e:
        print(f"Zenity Error: {e}")
        return jsonify({"path": ""})

@app.route('/initialize_dna', methods=['POST'])
def initialize_dna():
    data = request.json
    level, code = data.get('level'), data.get('code').upper()
    peid, pdid, psid = data.get('parent_eid'), data.get('parent_did'), data.get('parent_sid', '')
    use_template = data.get('use_template', False)
    src_temp = data.get('src_temp')
    src_script = data.get('src_script')

    def create_template(ent_code, dom_code, psid, code):
        if use_template:
            # 1. Cấu trúc DNA mới theo ý chú
            # KET/DNA/PUR/REQ/Standardized
            # KET/DNA/PUR/REQ/Processed
            # KET/DNA/PUR/REQ/Script
            # KET/DNA/PUR/REQ/Script/Template
            dna_base = os.path.join(f"app/{ent_code}/DNA/{dom_code}", psid, code)

            std_dir = os.path.join(dna_base, "Standardized")
            proc_dir = os.path.join(dna_base, "Processed")
            script_dir = os.path.join(dna_base, "Script")
            tpl_dir = os.path.join(script_dir, "Template")

            for d in [std_dir, proc_dir, tpl_dir]: os.makedirs(d, exist_ok=True)

            # Copy source files nếu có
            if src_temp and os.path.exists(src_temp):
                if os.path.isdir(src_temp): shutil.copytree(src_temp, tpl_dir, dirs_exist_ok=True)
                else: shutil.copy2(src_temp, tpl_dir)

            if src_script and os.path.exists(src_script):
                if os.path.isdir(src_script): shutil.copytree(src_script, script_dir, dirs_exist_ok=True)
                else: shutil.copy2(src_script, script_dir)

    try:
        if level == 'entity':
            res = query_db("SELECT id FROM entities WHERE code = %s", [code])
            if not res:
                query_db("INSERT INTO entities (name, code) VALUES (%s, %s)", [data.get('name'), code])
            os.makedirs(f"app/{code}", exist_ok=True)
            os.makedirs(f"app/{code}/DNA", exist_ok=True) # Luôn tạo DNA folder cho Entity
            if use_template: create_template(code, "", "", "") # Nếu stick template thì cấy luôn vào gốc DNA

        else:
            ent_res = query_db("SELECT code FROM entities WHERE id = %s", [int(peid)])
            ent_code = ent_res[0]['code']

            if level == 'domain':
                res = query_db("SELECT id FROM domains WHERE code = %s", [code])
                if not res:
                    query_db("INSERT INTO domains (name, code) VALUES (%s, %s)", [data.get('name'), code])
                dom_id = query_db("SELECT id FROM domains WHERE code = %s", [code])[0]['id']
                query_db("INSERT INTO dna_kernel (entity_id, domain_id, ui_config) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", [int(peid), dom_id, json.dumps({"prefix": f"{code.lower()}@", "primary_color": "#00ff00"})])
                os.makedirs(f"app/{ent_code}/{code}", exist_ok=True)
                os.makedirs(f"app/{ent_code}/DNA/{code}", exist_ok=True) # Luôn tạo DNA zone cho Domain
                if use_template: create_template(ent_code, code, "", "")

            elif level == 'sub':
                dom_code = query_db("SELECT code FROM domains WHERE id = %s", [int(pdid)])[0]['code']
                # ... (giữ nguyên logic tìm parent_id)

                # 1. Tìm parent_id
                parent_id = None
                if psid:
                    curr = None
                    for p in [x for x in psid.split('/') if x]:
                        r = query_db("SELECT id FROM dna_structure WHERE code = %s AND parent_id " + ("IS NULL" if curr is None else f"= {curr}") + " AND entity_id = %s AND domain_id = %s", [p, int(peid), int(pdid)])
                        if r: curr = r[0]['id']
                    parent_id = curr

                # 2. Kiểm tra tồn tại trước khi Insert
                sql_check = "SELECT id FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND code = %s AND "
                sql_check += "parent_id IS NULL" if parent_id is None else f"parent_id = {parent_id}"
                res_sub = query_db(sql_check, [int(peid), int(pdid), code])

                if not res_sub:
                    query_db("INSERT INTO dna_structure (entity_id, domain_id, parent_id, code, name) VALUES (%s, %s, %s, %s, %s)",
                            [int(peid), int(pdid), parent_id, code, data.get('name') or code])

                # 3. Tạo thư mục vật lý (Data Zone & DNA Zone)
                os.makedirs(os.path.join(f"app/{ent_code}/{dom_code}", psid, code), exist_ok=True)
                os.makedirs(os.path.join(f"app/{ent_code}/DNA/{dom_code}", psid, code), exist_ok=True)
                create_template(ent_code, dom_code, psid, code)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)})

@app.route('/delete_dna', methods=['POST'])
def delete_dna():
    data = request.json
    level, target_id = data.get('level'), data.get('id')
    peid, pdid = data.get('eid'), data.get('did')

    try:
        if level == 'entity':
            ent_res = query_db("SELECT code FROM entities WHERE id = %s", [int(target_id)])
            if ent_res:
                ent_code = ent_res[0]['code']
                query_db("DELETE FROM entities WHERE id = %s", [int(target_id)])
                path = f"app/{ent_code}"
                if os.path.exists(path): shutil.rmtree(path)

        elif level == 'domain':
            dom_res = query_db("SELECT code FROM domains WHERE id = %s", [int(target_id)])
            if dom_res:
                dom_code = dom_res[0]['code']
                ent_code = query_db("SELECT code FROM entities WHERE id = %s", [int(peid)])[0]['code']
                query_db("DELETE FROM dna_kernel WHERE entity_id = %s AND domain_id = %s", [int(peid), int(target_id)])
                # Delete Data Zone
                path_data = f"app/{ent_code}/{dom_code}"
                if os.path.exists(path_data): shutil.rmtree(path_data)
                # Delete DNA Zone
                path_dna = f"app/{ent_code}/DNA/{dom_code}"
                if os.path.exists(path_dna): shutil.rmtree(path_dna)

        elif level == 'sub':
            ent_code = query_db("SELECT code FROM entities WHERE id = %s", [int(peid)])[0]['code']
            dom_code = query_db("SELECT code FROM domains WHERE id = %s", [int(pdid)])[0]['code']

            # target_id here is the SID_PATH (e.g., "REQ/2023")
            parts = [p for p in target_id.split('/') if p]
            code_to_delete = parts[-1]

            # Find the record in DB to get its children/ID
            temp_p = None
            for p in parts[:-1]:
                res = query_db("SELECT id FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND code = %s AND " + ("parent_id IS NULL" if temp_p is None else f"parent_id = {temp_p}"), [int(peid), int(pdid), p])
                if res: temp_p = res[0]['id']

            # Delete from DB
            query_db("DELETE FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND code = %s AND " + ("parent_id IS NULL" if temp_p is None else f"parent_id = {temp_p}"), [int(peid), int(pdid), code_to_delete])

            # Physical delete: Data Zone
            path_data = os.path.join(f"app/{ent_code}/{dom_code}", target_id)
            if os.path.exists(path_data): shutil.rmtree(path_data)

            # Physical delete: DNA Zone
            path_dna = os.path.join(f"app/{ent_code}/DNA/{dom_code}", target_id)
            if os.path.exists(path_dna): shutil.rmtree(path_dna)

            # Find replacement sibling from DB
            parent_rel = "/".join(parts[:-1])
            new_sid = parent_rel
            sql_sib = "SELECT code FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND "
            sql_sib += "parent_id IS NULL" if not parent_rel else f"parent_id = {temp_p}"
            siblings = query_db(sql_sib + " ORDER BY sort_order, id", [int(peid), int(pdid)])

            if siblings:
                new_sid = (parent_rel + '/' + siblings[0]['code']) if parent_rel else siblings[0]['code']

            return jsonify({"success": True, "new_sid": new_sid.strip("/")})

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    # Chạy trực tiếp bằng Flask thay vì eventlet để tránh xung đột
    socketio.run(app, host='127.0.0.1', port=5001, debug=True, allow_unsafe_werkzeug=True)
