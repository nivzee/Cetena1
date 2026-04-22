import os, json, shutil
from flask import Flask, render_template_string, jsonify, request, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

app = Flask(__name__)
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
        if cur.description: return [dict(row) for row in cur.fetchall()]
        conn.commit(); return []
    except Exception as e:
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
    if not eid and entities: eid = str(entities[0]['id'])
    curr_ent = next((e for e in entities if str(e['id']) == str(eid)), {})
    ent_code = curr_ent.get('code', '')

    # 2. Domains
    domains = []
    if eid: domains = query_db("SELECT d.id, d.name, d.code FROM domains d JOIN dna_kernel k ON d.id = k.domain_id WHERE k.entity_id = %s ORDER BY d.id", [eid])
    did = request.args.get('did')
    if not did and domains: did = str(domains[0]['id'])
    curr_dom = next((d for d in domains if str(d['id']) == str(did)), {})
    dom_code = curr_dom.get('code', '')

    # 3. Breadcrumb & Menu Logic (DB-BASED)
    sid_path = request.args.get('sid', '').strip('/')
    sub_parts = [p for p in sid_path.split('/') if p]

    # --- SAFE DEEP REDIRECT ---
    # Find current level's ID to check for children
    current_level_id = None
    if sub_parts:
        temp_p = None
        for p in sub_parts:
            res = query_db("SELECT id FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND code = %s AND " + ("parent_id IS NULL" if temp_p is None else f"parent_id = {temp_p}"), [int(eid), int(did), p])
            if res: temp_p = res[0]['id']
            else:
                temp_p = None
                break
        current_level_id = temp_p

    # Look for the first child of this level
    sql_child = "SELECT code FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND "
    sql_child += "parent_id IS NULL" if not sub_parts else (f"parent_id = {current_level_id}" if current_level_id else "1=0")

    first_child = query_db(sql_child + " ORDER BY sort_order, id LIMIT 1", [int(eid), int(did)])
    if first_child:
        new_sid = (sid_path + '/' + first_child[0]['code']) if sid_path else first_child[0]['code']
        return redirect(url_for('index', u=user['username'], eid=eid, did=did, sid=new_sid))

    breadcrumb_subs = []
    base_path = f"app/{ent_code}/{dom_code}" if ent_code and dom_code else "app"

    EXCLUDE_DIRS = ['script', 'processed']
    current_rel_path = ""
    parent_id = None # Root of domain

    for part in sub_parts:
        # Get options (siblings) from DB
        sql = "SELECT * FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND "
        sql += "parent_id IS NULL" if parent_id is None else f"parent_id = {parent_id}"
        siblings = query_db(sql, [int(eid), int(did)])
        options = [s['code'] for s in siblings]

        # update current path
        current_rel_path = (f"{current_rel_path}/{part}" if current_rel_path else part).strip('/')

        # Find this part in DB to get its ID for next level
        this_item = next((s for s in siblings if s['code'] == part), None)
        if this_item: parent_id = this_item['id']

        breadcrumb_subs.append({
            "name": part,
            "path": current_rel_path,
            "options": sorted(options)
        })

    # Get options for the "Next" segment
    if not sub_parts:
        next_items = query_db("SELECT code FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND parent_id IS NULL", [int(eid), int(did)])
    else:
        next_items = query_db("SELECT code FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND parent_id = %s", [int(eid), int(did), parent_id]) if parent_id else []

    pending_options = sorted([i['code'] for i in next_items])

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
.bc-item { display: flex; align-items: center; position: relative; }
.bc-text { cursor: pointer; color: #fff; font-weight: bold; text-shadow: 0 0 5px rgba(255,255,255,0.2); transition: 0.2s; }
.bc-text:hover { color: var(--primary); }
.bc-caret { cursor: pointer; padding: 0 4px; color: #666; font-size: 10px; transition: color 0.2s; }
.bc-item:hover .bc-caret { color: #fff; }
.dropdown { position: absolute; top: 100%; left: 0; background: #111; border: 1px solid #333; min-width: 180px; display: none; z-index:100; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }
.dropdown::before { content: ''; position: absolute; top: -10px; left: 0; right: 0; height: 10px; }
.bc-item:hover .dropdown { display: block; }
.dropdown div { padding: 10px 15px; font-size: 11px; border-bottom: 1px solid #222; transition: all 0.2s; color: #aaa; display: flex; justify-content: space-between; align-items: center; cursor:pointer; }
.dropdown div:hover { background: #222; color: #fff; }
.plus-btn { color: #00ff00; cursor: pointer; font-size: 16px; padding: 0 10px; transition: all 0.3s; font-weight: bold; }
.plus-btn:hover { transform: scale(1.3); text-shadow: 0 0 10px #00ff00; }
.symbol-btn { color: #555; cursor: pointer; font-size: 12px; padding: 0 8px; transition: all 0.3s; font-weight: bold; }
.symbol-btn:hover { color: #fff; transform: scale(1.2); }
.shortcut-slot { width: 12px; height: 12px; border: 1px solid #555; cursor: pointer; transition: 0.2s; }
.shortcut-slot.active { background: var(--primary); border-color: var(--primary); box-shadow: 0 0 8px var(--primary); }
#factory-panel, #shortcut-panel { display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:#111; border:1px solid #333; padding:20px; z-index:1000; width:400px; box-shadow: 0 0 50px rgba(0,0,0,1); }
.overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); z-index:999; }
</style></head>
<body class="p-10">
<!-- DEBUG INFO (Hidden unless SA) -->
{% if is_sa %}
<div class="text-[8px] text-gray-700 mb-2 p-2 border border-gray-900">
    DEBUG: EID={{eid}} | DID={{did}} | SID_PATH={{sid_path}} | BASE_PATH={{base_path}} | SUB_PARTS={{sub_parts}} | SUBS_COUNT={{breadcrumb_subs|length}} | PENDING={{pending_options|length}}
</div>
{% endif %}
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
            <input type="checkbox" id="f-template" class="accent-green-500 w-3 h-3">
            <label for="f-template" class="text-[9px] text-gray-400 uppercase cursor-pointer">Apply Standard DNA Template (temp, script...)</label>
        </div>
    </div>
    <div class="flex justify-end gap-2 mt-6">
        <button onclick="closePanel()" class="text-[9px] uppercase border border-gray-800 px-3 py-1 text-gray-400 hover:bg-gray-900">Cancel</button>
        <button onclick="submitFactory()" class="text-[9px] uppercase bg-green-900 px-4 py-1 text-white hover:bg-green-700 font-bold">Initialize</button>
    </div>
</div>

<div class="overlay" onclick="closePanel(); closeShortcut();"></div>

<!-- BREADCRUMB -->
<div class="flex justify-between border-b border-gray-800 pb-5 mb-10">
<div class="flex items-center text-[12px] uppercase tracking-tight">
    <div class="bc-item"><span class="bc-text" style="color:#aaa">{{ user.username }}</span><span class="mx-2 text-gray-600 font-bold">@</span></div>

    <!-- ENTITY -->
    <div class="bc-item relative">
        <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}'">{{ curr_ent.code or '---' }}</span><span class="bc-caret">▼</span>
        <div class="dropdown">
            {% for ent in entities %}
                <div class="group flex justify-between items-center">
                    <span class="flex-grow" onclick="location.href='/?u={{user.username}}&eid={{ent.id}}'">{{ ent.code }}</span>
                    {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('entity', '{{ent.id}}', '{{ent.code}}')"></i>{% endif %}
                </div>
            {% endfor %}
            {% if is_sa %}<div class="text-green-500 font-bold" onclick="openPanel('entity', '')">+ NEW ENTITY</div>{% endif %}
        </div>
    </div>

    {% if curr_ent.code %}
    <span class="mx-2 text-gray-600 font-bold">/</span>
    <div class="bc-item relative">
        <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}'">{{ curr_dom.code or '---' }}</span><span class="bc-caret">▼</span>
        <div class="dropdown">
            {% for dom in domains %}
                <div class="group flex justify-between items-center">
                    <span class="flex-grow" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{dom.id}}'">{{ dom.code }}</span>
                    {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('domain', '{{dom.id}}', '{{dom.code}}')"></i>{% endif %}
                </div>
            {% endfor %}
            {% if is_sa %}<div class="text-green-500 font-bold" onclick="openPanel('domain', '')">+ NEW DOMAIN</div>{% endif %}
        </div>
    </div>
    {% endif %}

    <!-- RECURSIVE SUBS -->
    {% for sub in breadcrumb_subs %}
    <span class="mx-2 text-gray-600 font-bold">/</span>
    <div class="bc-item relative">
        <span class="bc-text" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ sub.path }}'">{{ sub.name }}</span><span class="bc-caret">▼</span>
        <div class="dropdown">
            {% for opt in sub.options %}
                {% set parts = sub.path.split('/')[:-1] %}
                {% set new_sid = (parts + [opt])|join('/') if parts else opt %}
                <div class="group flex justify-between items-center">
                    <span class="flex-grow" onclick="location.href='/?u={{user.username}}&eid={{eid}}&did={{did}}&sid={{ new_sid }}'">{{ opt }}</span>
                    {% if is_sa %}<i class="fas fa-minus-circle text-red-900 hover:text-red-600 ml-2 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" onclick="event.stopPropagation(); deleteItem('sub', '{{ new_sid }}', '{{ opt }}')"></i>{% endif %}
                </div>
            {% endfor %}
            {% if is_sa %}<div class="text-green-500 font-bold" onclick="openPanel('sub', '{{ '/'.join(sub.path.split('/')[:-1]) }}')">+ NEW SIBLING</div>{% endif %}
        </div>
    </div>
    {% endfor %}

    <span class="mx-2 text-gray-600 font-bold">/</span>
    {% if is_sa %}<span class="plus-btn" title="Create New Child" onclick="openPanel('sub', '{{ sid_path }}')">+</span>{% endif %}

    <div class="ml-6 flex items-center gap-2">
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
</div>

<script>
let currentLevel = '';
let factoryParentSid = '';

function openPanel(level, pSid) {
    currentLevel = level;
    factoryParentSid = pSid;
    document.getElementById('factory-context').innerText = (pSid || 'ROOT') + ' > NEW ' + level.toUpperCase();
    document.getElementById('factory-panel').style.display = 'block';
    document.querySelector('.overlay').style.display = 'block';
    document.getElementById('f-code').focus();
}
function closePanel() { document.getElementById('factory-panel').style.display = 'none'; document.querySelector('.overlay').style.display = 'none'; }

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
        use_template: document.getElementById('f-template').checked
    };

    fetch('/initialize_dna', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            if (currentLevel === 'sub') {
                const newSid = factoryParentSid ? (factoryParentSid + '/' + code) : code;
                location.href = `/?u={{user.username}}&eid={{eid}}&did={{did}}&sid=${newSid}`;
            } else {
                location.reload();
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
</body></html>""", shortcuts=shortcuts, eid=eid, did=did, sid_path=sid_path, breadcrumb_subs=breadcrumb_subs, entities=entities, domains=domains, user=user, is_sa=is_sa, dna=dna, shortcut_json=shortcut_json, curr_ent=curr_ent, curr_dom=curr_dom, sub_parts=sub_parts, pending_options=pending_options, base_path=base_path)

@app.route('/initialize_dna', methods=['POST'])
def initialize_dna():
    data = request.json
    level, code = data.get('level'), data.get('code').upper()
    peid, pdid, psid = data.get('parent_eid'), data.get('parent_did'), data.get('parent_sid', '')
    use_template = data.get('use_template', False)

    def create_template(base_path, folder_name):
        if use_template:
            for f in [f"{folder_name.lower()}_temp", f"{folder_name.lower()}_standardized", "script", "processed"]:
                os.makedirs(os.path.join(base_path, f), exist_ok=True)

    try:
        if level == 'entity':
            query_db("INSERT INTO entities (name, code) VALUES (%s, %s)", [data.get('name'), code])
            path = f"app/{code}"; os.makedirs(path, exist_ok=True); create_template(path, code)
        else:
            if not peid: return jsonify({"success": False, "message": "Missing Entity ID"})
            ent_res = query_db("SELECT code FROM entities WHERE id = %s", [int(peid)])
            if not ent_res: return jsonify({"success": False, "message": "Entity not found in DB"})
            ent_code = ent_res[0]['code']

            if level == 'domain':
                query_db("INSERT INTO domains (name, code) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING", [data.get('name'), code])
                dom_id_res = query_db("SELECT id FROM domains WHERE code = %s", [code])
                if not dom_id_res: return jsonify({"success": False, "message": "Failed to create/find domain"})
                dom_id = dom_id_res[0]['id']
                query_db("INSERT INTO dna_kernel (entity_id, domain_id, ui_config) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", [int(peid), dom_id, json.dumps({"prefix": f"{code.lower()}@", "primary_color": "#00ff00"})])
                path = f"app/{ent_code}/{code}"; os.makedirs(path, exist_ok=True); create_template(path, code)
            elif level == 'sub':
                if not pdid: return jsonify({"success": False, "message": "Missing Domain ID"})
                dom_res = query_db("SELECT code FROM domains WHERE id = %s", [int(pdid)])
                if not dom_res: return jsonify({"success": False, "message": "Domain not found in DB"})
                dom_code = dom_res[0]['code']
                # Path: app/ENT/DOM/SUB1/SUB2/NEW
                path = os.path.join(f"app/{ent_code}/{dom_code}", psid, code)
                os.makedirs(path, exist_ok=True); create_template(path, code)
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
                path = f"app/{ent_code}/{dom_code}"
                if os.path.exists(path): shutil.rmtree(path)

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

            # Delete from DB (including children recursively - though simple DELETE for now)
            # In production, we'd need a recursive CTE or child lookup
            query_db("DELETE FROM dna_structure WHERE entity_id = %s AND domain_id = %s AND code = %s AND " + ("parent_id IS NULL" if temp_p is None else f"parent_id = {temp_p}"), [int(peid), int(pdid), code_to_delete])

            # Physical delete
            full_base = f"app/{ent_code}/{dom_code}"
            path = os.path.join(full_base, target_id)
            if os.path.exists(path): shutil.rmtree(path)

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

if __name__ == '__main__': app.run(port=5001)
