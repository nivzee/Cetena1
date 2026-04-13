from flask import (Flask, render_template_string, jsonify, request,
                   redirect, url_for)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os, functools, math

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cetena-secret-change-me-2026')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

DB_CONFIG = {"dbname": "purchasing", "user": "c"}
USERS_PER_PAGE = 20


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(10) NOT NULL DEFAULT 'user'
                CHECK (role IN ('admin', 'user')),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname VARCHAR(100)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_order INT DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspace_subs (
            id SERIAL PRIMARY KEY,
            workspace_name VARCHAR(50) NOT NULL REFERENCES workspaces(name) ON DELETE CASCADE,
            sub_name VARCHAR(100) NOT NULL,
            display_order INT DEFAULT 0,
            UNIQUE(workspace_name, sub_name)
        )
    """)
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (username, nickname, password_hash, role) VALUES (%s,%s,%s,'admin')",
            ('admin', 'admin', generate_password_hash('Admin@2026'))
        )
        print("✅ Tài khoản admin mặc định: admin / Admin@2026")
    cur.execute("SELECT COUNT(*) FROM workspaces")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO workspaces (name, display_order) VALUES ('pur',1),('fin',2)")
        cur.execute("""
            INSERT INTO workspace_subs (workspace_name, sub_name, display_order) VALUES
            ('pur','quotations',1),('pur','report',2),('pur','comparisons',3),
            ('fin','accounting',1),('fin','tax',2)
        """)
    conn.commit()
    cur.close()
    conn.close()


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row['id'])
        self.username = row['username']
        self.nickname = row.get('nickname') or row['username']
        self.role = row['role']
        self._active = row['is_active']

    @property
    def is_active(self):
        return self._active

    def is_admin(self):
        return self.role == 'admin'

    @property
    def prompt_color(self):
        return '#3B82F6' if self.role == 'admin' else '#4ADE80'


@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (int(user_id),))
        row = cur.fetchone()
        cur.close(); conn.close()
        return User(row) if row else None
    except Exception:
        return None


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_admin():
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


# ─── LOGIN ───────────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Cetena – Đăng nhập</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background: linear-gradient(135deg,#2c001e 0%,#4c1a41 50%,#3b0a34 100%); min-height:100vh; }
  </style>
</head>
<body class="flex items-center justify-center min-h-screen font-sans">
  <div class="flex flex-col items-center space-y-5 w-80">
    <div class="w-20 h-20 rounded-full bg-orange-500 flex items-center justify-center text-4xl shadow-2xl border-4 border-white/20">🛒</div>
    <h1 class="text-white text-2xl font-light tracking-wide">Cetena Dashboard</h1>
    {% if error %}
    <div class="w-full bg-red-500/20 border border-red-400/50 text-red-200 text-sm px-4 py-2 rounded-lg text-center">{{ error }}</div>
    {% endif %}
    <form method="POST" class="w-full flex flex-col space-y-3">
      <input type="text" name="username" value="{{ username or '' }}" placeholder="Tên đăng nhập" required
             class="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-orange-400 transition" autofocus>
      <input type="password" name="password" placeholder="Mật khẩu" required
             class="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-orange-400 transition">
      <button type="submit" class="w-full py-3 rounded-lg bg-orange-500 hover:bg-orange-600 text-white font-semibold transition shadow-lg mt-2">Đăng nhập</button>
    </form>
  </div>
</body>
</html>"""


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Cetena</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0d1117;color:#e6edf3;font-family:'JetBrains Mono','Courier New',monospace;height:100vh;display:flex;flex-direction:column;overflow:hidden}

    #prompt-bar{flex-shrink:0;background:#161b22;border-bottom:1px solid #21262d;padding:9px 16px;display:flex;align-items:center;justify-content:space-between;font-size:14px;user-select:none}
    #prompt-left{display:flex;align-items:center}
    #prompt-nick{font-weight:500}
    #prompt-at{color:#8b949e;text-decoration:none}
    #prompt-at:hover{color:#58a6ff}
    #prompt-ws{color:#e6edf3;cursor:pointer;padding:0 1px}
    #prompt-ws:hover{color:#58a6ff}
    #prompt-sep{color:#f97316;cursor:pointer;padding:0 1px}
    #prompt-sep:hover{color:#fb923c}
    #prompt-path{color:#8b949e}
    #prompt-dollar{color:#e6edf3;margin-left:4px}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
    #prompt-cursor{color:#e6edf3;animation:blink 1s step-end infinite}
    #prompt-right{display:flex;align-items:center;gap:16px;font-size:12px;color:#8b949e}
    #prompt-right a{color:#8b949e;text-decoration:none}
    #prompt-right a:hover{color:#e6edf3}
    .admin-link{color:#f97316 !important}
    .admin-link:hover{color:#fb923c !important}

    #ws-menu,#sub-menu{position:fixed;background:#161b22;border:1px solid #58a6ff;border-radius:4px;z-index:9999;min-width:160px;display:none;box-shadow:0 8px 24px rgba(0,0,0,.6)}
    .m-item{padding:8px 14px;cursor:pointer;color:#e6edf3;font-size:13px;border-bottom:1px solid #21262d}
    .m-item:last-child{border-bottom:none}
    .m-item:hover{background:#21262d;color:#58a6ff}
    .m-add{padding:8px 14px;cursor:pointer;color:#58a6ff;font-size:13px;border-top:1px solid #21262d}
    .m-add:hover{background:#21262d}
    .m-add-row{display:flex;align-items:center;gap:6px;padding:6px 10px;border-top:1px solid #21262d}
    .m-add-row input{background:#0d1117;border:1px solid #58a6ff;color:#e6edf3;padding:4px 8px;font-size:12px;font-family:inherit;border-radius:3px;width:100px;outline:none}
    .m-add-row button{background:#238636;color:#fff;border:none;padding:4px 8px;font-size:12px;cursor:pointer;border-radius:3px}

    #content{flex:1;overflow:auto;padding:16px}
    .ws-panel{display:none;height:100%;flex-direction:column}
    .ws-panel.active{display:flex}
    .sub-panel{display:none;flex:1;flex-direction:column}
    .sub-panel.active{display:flex}
    .placeholder{flex:1;display:flex;align-items:center;justify-content:center;color:#30363d;font-size:16px;letter-spacing:1px}

    table{width:100%;border-collapse:collapse;font-size:13px}
    thead th{padding:10px 12px;text-align:left;color:#8b949e;border-bottom:1px solid #21262d;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
    tbody tr{border-bottom:1px solid #161b22}
    tbody tr:hover{background:#161b22}
    tbody td{padding:10px 12px;color:#e6edf3}
    .td-id{color:#484f58;font-size:11px}
    .td-price{text-align:right;color:#f97316;font-weight:500}
    .td-qty{text-align:center;color:#8b949e}
    .td-amount{text-align:right;color:#8b949e}
  </style>
</head>
<body>
  <div id="prompt-bar">
    <div id="prompt-left">
      <span id="prompt-nick" style="color:{{ current_user.prompt_color }}">{{ current_user.nickname }}</span>
      <a id="prompt-at" href="https://www.youtube.com" target="_blank">@</a>
      <span id="prompt-ws" onclick="toggleWsMenu(event)"></span>
      <span id="prompt-sep" onclick="toggleSubMenu(event)">:::~/</span>
      <span id="prompt-path"></span>
      <span id="prompt-dollar">$</span>
      <span id="prompt-cursor">▌</span>
    </div>
    <div id="prompt-right">
      {% if current_user.is_admin() %}<a href="/admin" class="admin-link">⚙ admin</a>{% endif %}
      <span>{{ current_user.username }}</span>
      <a href="/logout">logout</a>
    </div>
  </div>

  <div id="ws-menu"></div>
  <div id="sub-menu"></div>
  <div id="content"></div>

  <script>
    const IS_ADMIN = {{ 'true' if current_user.is_admin() else 'false' }};
    let WORKSPACES = [], WS_SUBS = {}, currentWs = null, currentSub = null;

    // ── Init ──────────────────────────────────────────────────────────
    async function loadConfig() {
      try {
        const data = await (await fetch('/api/workspaces')).json();
        WORKSPACES = data.workspaces;
        WS_SUBS = data.subs;
        ensureWsDivs();
        if (WORKSPACES.length > 0) {
          const ws = WORKSPACES[0];
          const sub = (WS_SUBS[ws] || [])[0] || null;
          switchWs(ws, sub);
        }
      } catch(e) { console.error('loadConfig:', e); }
    }

    function ensureWsDivs() {
      const content = document.getElementById('content');
      for (const ws of WORKSPACES) {
        if (!document.getElementById('ws-' + ws)) {
          const d = document.createElement('div');
          d.id = 'ws-' + ws;
          d.className = 'ws-panel';
          content.appendChild(d);
        }
        for (const sub of (WS_SUBS[ws] || [])) ensureSubDiv(ws, sub);
      }
    }

    function ensureSubDiv(ws, sub) {
      const wsDiv = document.getElementById('ws-' + ws);
      if (!wsDiv) return;
      const id = 'sub-' + ws + '-' + sub;
      if (document.getElementById(id)) return;
      const d = document.createElement('div');
      d.id = id;
      d.className = 'sub-panel';
      if (ws === 'pur' && sub === 'quotations') {
        d.innerHTML = '<div style="overflow:auto;flex:1"><table><thead><tr>' +
          '<th>ID</th><th>Sản phẩm</th><th style="text-align:right">Đơn giá</th>' +
          '<th style="text-align:center">SL</th><th style="text-align:right">Thành tiền</th>' +
          '</tr></thead><tbody id="tbl-quotations"></tbody></table></div>';
      } else {
        d.innerHTML = '<div class="placeholder">' + ws + ' / ' + sub + '</div>';
      }
      wsDiv.appendChild(d);
    }

    // ── Switch ────────────────────────────────────────────────────────
    function switchWs(ws, sub) {
      document.querySelectorAll('.ws-panel').forEach(d => d.classList.remove('active'));
      const wsDiv = document.getElementById('ws-' + ws);
      if (wsDiv) wsDiv.classList.add('active');
      currentWs = ws;
      document.getElementById('prompt-ws').textContent = ws;
      const s = sub || (WS_SUBS[ws] || [])[0] || null;
      switchSub(ws, s);
    }

    function switchSub(ws, sub) {
      const wsDiv = document.getElementById('ws-' + ws);
      if (!wsDiv) return;
      wsDiv.querySelectorAll('.sub-panel').forEach(d => d.classList.remove('active'));
      if (sub) {
        const d = document.getElementById('sub-' + ws + '-' + sub);
        if (d) {
          d.classList.add('active');
          if (ws === 'pur' && sub === 'quotations') loadQuotations();
        }
      }
      currentSub = sub;
      document.getElementById('prompt-path').textContent = sub || '';
    }

    async function loadQuotations() {
      const tbody = document.getElementById('tbl-quotations');
      if (!tbody) return;
      try {
        const data = await (await fetch('/api/data')).json();
        tbody.innerHTML = data.map(r =>
          '<tr>' +
          '<td class="td-id">' + r.id + '</td>' +
          '<td>' + (r.product_name || 'N/A') + '</td>' +
          '<td class="td-price">' + Number(r.unit_price||0).toLocaleString('vi-VN') + ' ₫</td>' +
          '<td class="td-qty">' + (r.quantity || 0) + '</td>' +
          '<td class="td-amount">' + (r.amount ? Number(r.amount).toLocaleString('vi-VN') + ' ₫' : '—') + '</td>' +
          '</tr>'
        ).join('');
      } catch(e) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="color:#f85149;padding:12px">Lỗi tải dữ liệu</td></tr>';
      }
    }

    // ── Workspace menu ────────────────────────────────────────────────
    function toggleWsMenu(e) {
      e.stopPropagation();
      const menu = document.getElementById('ws-menu');
      if (menu.style.display === 'block') { menu.style.display = 'none'; return; }
      closeMenus();
      let html = WORKSPACES.filter(w => w !== currentWs)
        .map(w => '<div class="m-item" onclick="selectWs(\'' + w + '\')">' + w + '</div>').join('');
      if (IS_ADMIN) html += '<div class="m-add" onclick="showAddInput(\'ws\')">＋ workspace</div>';
      if (!html) return;
      menu.innerHTML = html;
      positionMenu(menu, e.currentTarget);
      menu.style.display = 'block';
    }

    function selectWs(ws) {
      closeMenus();
      switchWs(ws, null);
    }

    // ── Sub menu ──────────────────────────────────────────────────────
    function toggleSubMenu(e) {
      e.stopPropagation();
      const menu = document.getElementById('sub-menu');
      if (menu.style.display === 'block') { menu.style.display = 'none'; return; }
      closeMenus();
      const subs = WS_SUBS[currentWs] || [];
      let html = subs.filter(s => s !== currentSub)
        .map(s => '<div class="m-item" onclick="selectSub(\'' + s + '\')">' + s + '</div>').join('');
      if (IS_ADMIN) html += '<div class="m-add" onclick="showAddInput(\'sub\')">＋ sub-option</div>';
      if (!html) return;
      menu.innerHTML = html;
      positionMenu(menu, e.currentTarget);
      menu.style.display = 'block';
    }

    function selectSub(sub) {
      closeMenus();
      ensureSubDiv(currentWs, sub);
      switchSub(currentWs, sub);
    }

    // ── Add input ─────────────────────────────────────────────────────
    function showAddInput(type) {
      const menu = document.getElementById(type === 'ws' ? 'ws-menu' : 'sub-menu');
      const addEl = menu.querySelector('.m-add');
      if (!addEl) return;
      addEl.outerHTML = '<div class="m-add-row">' +
        '<input id="ai-' + type + '" type="text" placeholder="' + (type === 'ws' ? 'tên workspace' : 'tên sub') + '"' +
        ' onkeydown="if(event.key===\'Enter\')confirmAdd(\'' + type + '\')">' +
        '<button onclick="confirmAdd(\'' + type + '\')">OK</button></div>';
      const inp = document.getElementById('ai-' + type);
      if (inp) { inp.focus(); inp.addEventListener('click', e => e.stopPropagation()); }
    }

    async function confirmAdd(type) {
      const inp = document.getElementById('ai-' + type);
      if (!inp) return;
      const name = inp.value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '');
      if (!name) return;
      const url = type === 'ws' ? '/api/workspaces' : '/api/workspaces/' + currentWs + '/subs';
      const body = type === 'ws' ? {name} : {sub_name: name};
      try {
        const res = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const json = await res.json();
        if (!res.ok) { alert('Lỗi: ' + json.error); return; }
        if (type === 'ws') {
          WORKSPACES.push(name); WS_SUBS[name] = [];
          ensureWsDivs(); switchWs(name, null);
        } else {
          WS_SUBS[currentWs] = WS_SUBS[currentWs] || [];
          WS_SUBS[currentWs].push(name);
          ensureSubDiv(currentWs, name); switchSub(currentWs, name);
        }
        closeMenus();
      } catch(e) { alert('Lỗi kết nối: ' + e.message); }
    }

    // ── Helpers ───────────────────────────────────────────────────────
    function positionMenu(menu, anchor) {
      const r = anchor.getBoundingClientRect();
      menu.style.left = r.left + 'px';
      menu.style.top = (r.bottom + 4) + 'px';
    }
    function closeMenus() {
      document.getElementById('ws-menu').style.display = 'none';
      document.getElementById('sub-menu').style.display = 'none';
    }
    document.addEventListener('click', closeMenus);

    loadConfig();
  </script>
</body>
</html>"""


# ─── ADMIN ───────────────────────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Admin – Cetena</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body{background:#f8f9fa;font-family:system-ui,sans-serif}
    .badge-admin{background:#3B82F6;color:#fff;padding:1px 8px;border-radius:999px;font-size:11px}
    .badge-user{background:#4ADE80;color:#064e3b;padding:1px 8px;border-radius:999px;font-size:11px}
    .prompt-pre{font-family:'Courier New',monospace;font-size:12px}
  </style>
</head>
<body class="p-6">
  <div class="max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <a href="/" class="text-gray-400 hover:text-gray-700 text-sm">← Dashboard</a>
        <h1 class="text-xl font-bold">Quản lý người dùng</h1>
      </div>
      <span class="text-sm text-gray-400">Tổng: {{ total_users }} tài khoản</span>
    </div>

    <div class="grid grid-cols-2 gap-5 mb-5">
      <!-- Search -->
      <div class="bg-white rounded-lg p-4 shadow-sm border">
        <h2 class="font-semibold mb-3 text-gray-600 text-sm">Tìm kiếm</h2>
        <form method="GET" class="flex gap-2">
          <input type="text" name="q" value="{{ q or '' }}" placeholder="Username hoặc nickname…"
                 class="flex-1 px-3 py-2 border rounded text-sm focus:outline-none focus:border-blue-400">
          <button type="submit" class="px-4 py-2 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">Tìm</button>
          {% if q %}<a href="/admin" class="px-3 py-2 bg-gray-200 rounded text-sm hover:bg-gray-300 flex items-center">✕</a>{% endif %}
        </form>
      </div>

      <!-- Add user -->
      <div class="bg-white rounded-lg p-4 shadow-sm border">
        <h2 class="font-semibold mb-3 text-gray-600 text-sm">Thêm tài khoản</h2>
        {% if add_error %}<p class="text-red-500 text-xs mb-2">{{ add_error }}</p>{% endif %}
        {% if add_ok %}<p class="text-green-600 text-xs mb-2">✅ Đã tạo: {{ add_ok }}</p>{% endif %}
        <form method="POST" action="/admin/users/add" class="grid grid-cols-2 gap-2">
          <input type="text" name="username" placeholder="Username" required class="px-3 py-2 border rounded text-sm focus:outline-none">
          <input type="text" name="nickname" placeholder="Nickname (tuỳ chọn)" class="px-3 py-2 border rounded text-sm focus:outline-none">
          <input type="password" name="password" placeholder="Mật khẩu" required class="px-3 py-2 border rounded text-sm focus:outline-none">
          <select name="role" class="px-3 py-2 border rounded text-sm bg-white focus:outline-none">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <button type="submit" class="col-span-2 py-2 bg-green-500 text-white rounded text-sm hover:bg-green-600">＋ Tạo tài khoản</button>
        </form>
      </div>
    </div>

    <!-- Table -->
    <div class="bg-white rounded-lg shadow-sm border overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b">
          <tr class="text-xs text-gray-400 uppercase">
            <th class="px-4 py-3 text-left">ID</th>
            <th class="px-4 py-3 text-left">Prompt</th>
            <th class="px-4 py-3 text-left">Username</th>
            <th class="px-4 py-3 text-left">Role</th>
            <th class="px-4 py-3 text-left">Trạng thái</th>
            <th class="px-4 py-3 text-left">Tạo lúc</th>
            <th class="px-4 py-3 text-right">Thao tác</th>
          </tr>
        </thead>
        <tbody>
        {% for u in users %}
        <tr class="border-b hover:bg-gray-50">
          <td class="px-4 py-3 text-gray-400 font-mono text-xs">{{ u['id'] }}</td>
          <td class="px-4 py-3">
            <span class="prompt-pre" style="color:{{ '#3B82F6' if u['role']=='admin' else '#4ADE80' }}">{{ u['nickname'] or u['username'] }}</span>
            <span class="prompt-pre text-gray-400">@ws:::~/sub$</span>
          </td>
          <td class="px-4 py-3 font-medium">{{ u['username'] }}</td>
          <td class="px-4 py-3"><span class="badge-{{ u['role'] }}">{{ u['role'] }}</span></td>
          <td class="px-4 py-3">
            {% if u['is_active'] %}<span class="text-green-600 text-xs">● active</span>
            {% else %}<span class="text-red-500 text-xs">○ inactive</span>{% endif %}
          </td>
          <td class="px-4 py-3 text-gray-400 text-xs">{{ u['created_at'].strftime('%d/%m/%Y') if u['created_at'] else '—' }}</td>
          <td class="px-4 py-3 text-right">
            {% if u['id']|string != current_user.id %}
            <div class="flex gap-2 justify-end">
              <form method="POST" action="/admin/users/{{ u['id'] }}/toggle-role" class="inline">
                <button class="px-2 py-1 bg-blue-100 text-blue-600 rounded text-xs hover:bg-blue-200 cursor-pointer">
                  → {{ 'user' if u['role']=='admin' else 'admin' }}
                </button>
              </form>
              <form method="POST" action="/admin/users/{{ u['id'] }}/toggle-active" class="inline">
                <button class="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs hover:bg-yellow-200 cursor-pointer">
                  {{ 'Khóa' if u['is_active'] else 'Mở' }}
                </button>
              </form>
              <form method="POST" action="/admin/users/{{ u['id'] }}/delete" class="inline"
                    onsubmit="return confirm('Xóa tài khoản {{ u[\'username\'] }}?')">
                <button class="px-2 py-1 bg-red-100 text-red-600 rounded text-xs hover:bg-red-200 cursor-pointer">Xóa</button>
              </form>
            </div>
            {% else %}
            <span class="text-gray-300 text-xs">(bạn)</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      {% if total_pages > 1 %}
      <div class="flex justify-center items-center gap-3 p-4 border-t">
        {% if page > 1 %}
        <a href="?page={{ page-1 }}{% if q %}&q={{ q }}{% endif %}" class="px-3 py-1 bg-gray-200 rounded text-sm hover:bg-gray-300">← Trước</a>
        {% endif %}
        <span class="text-sm text-gray-500">{{ page }} / {{ total_pages }}</span>
        {% if page < total_pages %}
        <a href="?page={{ page+1 }}{% if q %}&q={{ q }}{% endif %}" class="px-3 py-1 bg-gray-200 rounded text-sm hover:bg-gray-300">Tiếp →</a>
        {% endif %}
      </div>
      {% endif %}
    </div>
  </div>
</body>
</html>"""


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def home():
    return render_template_string(DASHBOARD_HTML)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    error = None
    username = ''
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        try:
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            cur.close(); conn.close()
            if row and check_password_hash(row['password_hash'], password):
                if not row['is_active']:
                    error = 'Tài khoản bị vô hiệu hóa.'
                else:
                    login_user(User(row))
                    return redirect(url_for('home'))
            else:
                error = 'Sai tài khoản hoặc mật khẩu.'
        except Exception as e:
            error = str(e)
    return render_template_string(LOGIN_HTML, error=error, username=username)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/api/data')
@login_required
def get_data():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT d.id, m.product_name, d.unit_price, d.quantity, d.amount
            FROM quotation_details d
            LEFT JOIN products_master m ON d.product_id = m.product_id
            ORDER BY d.id DESC LIMIT 200
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workspaces', methods=['GET'])
@login_required
def api_get_workspaces():
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT name FROM workspaces ORDER BY display_order, name")
        workspaces = [r['name'] for r in cur.fetchall()]
        cur.execute("SELECT workspace_name, sub_name FROM workspace_subs ORDER BY workspace_name, display_order, sub_name")
        subs = {}
        for r in cur.fetchall():
            subs.setdefault(r['workspace_name'], []).append(r['sub_name'])
        cur.close()
        return jsonify({'workspaces': workspaces, 'subs': subs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/workspaces', methods=['POST'])
@admin_required
def api_add_workspace():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip().lower()
    if not name:
        return jsonify({'error': 'Tên không hợp lệ'}), 400
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO workspaces (name) VALUES (%s)", (name,))
        conn.commit(); cur.close()
        return jsonify({'ok': True, 'name': name})
    except Exception as e:
        if conn: conn.rollback()
        msg = 'Workspace đã tồn tại' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'error': msg}), 409
    finally:
        if conn: conn.close()


@app.route('/api/workspaces/<ws>/subs', methods=['POST'])
@admin_required
def api_add_sub(ws):
    data = request.get_json() or {}
    sub_name = (data.get('sub_name') or '').strip().lower()
    if not sub_name:
        return jsonify({'error': 'Tên không hợp lệ'}), 400
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO workspace_subs (workspace_name, sub_name) VALUES (%s,%s)", (ws, sub_name))
        conn.commit(); cur.close()
        return jsonify({'ok': True, 'ws': ws, 'sub_name': sub_name})
    except Exception as e:
        if conn: conn.rollback()
        msg = 'Sub đã tồn tại' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'error': msg}), 409
    finally:
        if conn: conn.close()


# ─── Admin panel ─────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_panel():
    q = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    add_error = request.args.get('add_error')
    add_ok = request.args.get('add_ok')
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        like = f'%{q}%'
        if q:
            cur.execute("SELECT COUNT(*) FROM users WHERE username ILIKE %s OR nickname ILIKE %s", (like, like))
        else:
            cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()['count']
        total_pages = max(1, math.ceil(total_users / USERS_PER_PAGE))
        page = min(page, total_pages)
        offset = (page - 1) * USERS_PER_PAGE
        if q:
            cur.execute("SELECT * FROM users WHERE username ILIKE %s OR nickname ILIKE %s ORDER BY id LIMIT %s OFFSET %s",
                        (like, like, USERS_PER_PAGE, offset))
        else:
            cur.execute("SELECT * FROM users ORDER BY id LIMIT %s OFFSET %s", (USERS_PER_PAGE, offset))
        users = cur.fetchall()
        cur.close()
        return render_template_string(ADMIN_HTML, users=users, page=page,
                                      total_pages=total_pages, total_users=total_users,
                                      q=q, add_error=add_error, add_ok=add_ok)
    except Exception as e:
        return f'<pre style="color:red">DB Error: {e}</pre>', 500
    finally:
        if conn: conn.close()


@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    username = request.form.get('username', '').strip()
    nickname = request.form.get('nickname', '').strip() or None
    password = request.form.get('password', '')
    role = request.form.get('role', 'user')
    if not username or not password:
        return redirect(url_for('admin_panel', add_error='Username và mật khẩu không được rỗng.'))
    if role not in ('admin', 'user'):
        role = 'user'
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, nickname, password_hash, role) VALUES (%s,%s,%s,%s)",
            (username, nickname, generate_password_hash(password), role)
        )
        conn.commit(); cur.close()
        return redirect(url_for('admin_panel', add_ok=username))
    except Exception as e:
        if conn: conn.rollback()
        msg = f'Username "{username}" đã tồn tại.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return redirect(url_for('admin_panel', add_error=msg))
    finally:
        if conn: conn.close()


@app.route('/admin/users/<int:uid>/toggle-role', methods=['POST'])
@admin_required
def admin_toggle_role(uid):
    if str(uid) == current_user.id:
        return redirect(url_for('admin_panel'))
    conn = None
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE users SET role=CASE WHEN role='admin' THEN 'user' ELSE 'admin' END WHERE id=%s", (uid,))
        conn.commit(); cur.close()
    except Exception:
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:uid>/toggle-active', methods=['POST'])
@admin_required
def admin_toggle_active(uid):
    if str(uid) == current_user.id:
        return redirect(url_for('admin_panel'))
    conn = None
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE users SET is_active=NOT is_active WHERE id=%s", (uid,))
        conn.commit(); cur.close()
    except Exception:
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    if str(uid) == current_user.id:
        return redirect(url_for('admin_panel'))
    conn = None
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit(); cur.close()
    except Exception:
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5001, debug=False)
