from flask import Flask, request, jsonify, Response
import json, os, hashlib, uuid, time
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE = '/tmp/taskpro_v3.json'
SECRET = os.environ.get('APP_SECRET', 'taskpro2024secret')

DEFAULT_CATS = [
    {"id":1,"name":"General","color":"#6366f1"},
    {"id":2,"name":"Work","color":"#0ea5e9"},
    {"id":3,"name":"Personal","color":"#f59e0b"},
    {"id":4,"name":"Meetings","color":"#8b5cf6"},
    {"id":5,"name":"Development","color":"#10b981"},
    {"id":6,"name":"Design","color":"#ec4899"},
    {"id":7,"name":"Marketing","color":"#f97316"},
    {"id":8,"name":"Finance","color":"#14b8a6"},
    {"id":9,"name":"HR","color":"#6b7280"},
    {"id":10,"name":"Urgent","color":"#ef4444"}
]

DEFAULT_SETTINGS = {
    "default_reminder_low":60,"default_reminder_medium":30,
    "default_reminder_high":15,"sound_enabled":1,"popup_enabled":1,
    "browser_notif_enabled":1,"popup_duration_low":5,
    "popup_duration_medium":8,"popup_duration_high":12,
    "auto_snooze_mins":10,"check_interval_secs":30
}

def load_db():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"DB load error: {e}")
    return {"users":{}}

def save_db(db):
    try:
        with open(DATA_FILE,'w') as f:
            json.dump(db, f)
    except Exception as e:
        print(f"DB save error: {e}")

def hash_pw(pw):
    return hashlib.sha256((pw + SECRET).encode()).hexdigest()

def make_token(uid):
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{uid}:{SECRET}:{ts}".encode()).hexdigest()[:32]
    return f"{h}{ts}.{uid}"

def parse_token(token):
    if not token or '.' not in token:
        return None
    try:
        parts = token.rsplit('.', 1)
        if len(parts) != 2:
            return None
        uid = parts[1]
        db = load_db()
        if uid in db.get('users', {}):
            return uid
    except:
        pass
    return None

def get_uid():
    auth = request.headers.get('Authorization', '')
    token = auth[7:] if auth.startswith('Bearer ') else request.args.get('token', '')
    return parse_token(token)

def now():
    return datetime.now().isoformat()

def nxt(udata, col):
    v = udata['ids'].get(col, 1)
    udata['ids'][col] = v + 1
    return v

def blank_user(name, email, pw_hash, role):
    return {
        "name": name, "email": email, "password": pw_hash, "role": role,
        "created_at": now(), "tasks": [],
        "categories": json.loads(json.dumps(DEFAULT_CATS)),
        "notifications": [],
        "settings": json.loads(json.dumps(DEFAULT_SETTINGS)),
        "ids": {"tasks":1,"categories":11,"notifications":1}
    }

def run_notifs(ud):
    n = datetime.now()
    td = n.strftime('%Y-%m-%d')
    tm = (n + timedelta(days=1)).strftime('%Y-%m-%d')
    ex_keys = set(
        f"{x.get('task_id')}_{x.get('type')}"
        for x in ud.get('notifications', [])
        if not x.get('is_dismissed')
    )
    for t in ud.get('tasks', []):
        if t.get('status') == 'completed' or not t.get('due_date'):
            continue
        tid = t['id']; pri = t.get('priority','medium')
        em = '🔴' if pri=='high' else '🟡' if pri=='medium' else '🟢'
        dd = t.get('due_date','')
        if dd < td:
            k = f"{tid}_overdue"
            if k not in ex_keys:
                days = max(1,(n - datetime.strptime(dd,'%Y-%m-%d')).days)
                ud['notifications'].insert(0,{
                    'id':nxt(ud,'notifications'),'task_id':tid,
                    'message':f"{em} OVERDUE ({days}d): '{t['title']}'",
                    'type':'overdue','priority':pri,'is_read':0,'is_dismissed':0,
                    'created_at':now(),'task_title':t['title'],'task_priority':pri})
        elif dd == td:
            k = f"{tid}_due_today"
            if k not in ex_keys:
                ti = f" at {t['due_time']}" if t.get('due_time') else ''
                ud['notifications'].insert(0,{
                    'id':nxt(ud,'notifications'),'task_id':tid,
                    'message':f"{em} Due Today{ti}: '{t['title']}'",
                    'type':'due_today','priority':pri,'is_read':0,'is_dismissed':0,
                    'created_at':now(),'task_title':t['title'],'task_priority':pri})
        if t.get('due_time') and not t.get('reminder_sent'):
            try:
                due = datetime.strptime(f"{dd} {t['due_time']}",'%Y-%m-%d %H:%M')
                rm = t.get('reminder_mins',30) or 30
                ra = due - timedelta(minutes=rm)
                if n >= ra and n < due:
                    k = f"{tid}_reminder"
                    if k not in ex_keys:
                        ml = max(0,int((due-n).total_seconds()/60))
                        ud['notifications'].insert(0,{
                            'id':nxt(ud,'notifications'),'task_id':tid,
                            'message':f"{em} REMINDER: '{t['title']}' in {ml} min!",
                            'type':'reminder','priority':pri,'is_read':0,'is_dismissed':0,
                            'created_at':now(),'task_title':t['title'],'task_priority':pri})
                        t['reminder_sent'] = 1
            except: pass
        if pri == 'high' and dd == tm:
            k = f"{tid}_upcoming_high"
            if k not in ex_keys:
                ud['notifications'].insert(0,{
                    'id':nxt(ud,'notifications'),'task_id':tid,
                    'message':f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'",
                    'type':'upcoming_high','priority':'high','is_read':0,'is_dismissed':0,
                    'created_at':now(),'task_title':t['title'],'task_priority':'high'})
    ud['notifications'] = ud['notifications'][:80]

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return r

@app.before_request
def preflight():
    if request.method == 'OPTIONS':
        r = jsonify({})
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return r, 200

@app.route('/')
def serve():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static','app.html')
    try:
        with open(p,'r',encoding='utf-8') as f:
            return Response(f.read(), content_type='text/html; charset=utf-8')
    except Exception as e:
        return Response(f'<h1>Error: {e}</h1>', content_type='text/html')

# ── AUTH ─────────────────────────────────────────────
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    b = request.json or {}
    name = b.get('name','').strip()
    email = b.get('email','').strip().lower()
    password = b.get('password','')
    role = b.get('role','Member').strip() or 'Member'
    if not name or not email or not password:
        return jsonify({'error':'Name, email and password are required'}), 400
    if len(password) < 4:
        return jsonify({'error':'Password must be at least 4 characters'}), 400
    db = load_db()
    for u in db.get('users',{}).values():
        if u.get('email','').lower() == email:
            return jsonify({'error':'Email already registered'}), 400
    uid = str(uuid.uuid4())[:12]
    db['users'][uid] = blank_user(name, email, hash_pw(password), role)
    save_db(db)
    token = make_token(uid)
    return jsonify({'token':token,'user':{'id':uid,'name':name,'email':email,'role':role}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    b = request.json or {}
    email = b.get('email','').strip().lower()
    password = b.get('password','')
    if not email or not password:
        return jsonify({'error':'Email and password required'}), 400
    db = load_db()
    for uid, u in db.get('users',{}).items():
        if u.get('email','').lower() == email and u.get('password') == hash_pw(password):
            token = make_token(uid)
            return jsonify({'token':token,'user':{'id':uid,'name':u['name'],'email':u['email'],'role':u.get('role','Member')}})
    return jsonify({'error':'Invalid email or password'}), 401

@app.route('/api/auth/guest', methods=['POST'])
def guest():
    db = load_db()
    gid = 'g_' + str(uuid.uuid4())[:8]
    em = f"{gid}@guest.tp"
    db['users'][gid] = blank_user('Guest User', em, '', 'Guest')
    save_db(db)
    token = make_token(gid)
    return jsonify({'token':token,'user':{'id':gid,'name':'Guest User','email':em,'role':'Guest'}})

@app.route('/api/auth/me')
def me():
    uid = get_uid()
    if not uid:
        return jsonify({'error':'Not authenticated'}), 401
    db = load_db()
    u = db['users'].get(uid)
    if not u:
        return jsonify({'error':'User not found'}), 404
    return jsonify({'user':{'id':uid,'name':u['name'],'email':u['email'],'role':u.get('role','Member')}})

@app.route('/api/auth/profile', methods=['PUT'])
def update_profile():
    uid = get_uid()
    if not uid:
        return jsonify({'error':'Not authenticated'}), 401
    db = load_db()
    u = db['users'].get(uid)
    if not u:
        return jsonify({'error':'User not found'}), 404
    b = request.json or {}
    if b.get('name','').strip():
        u['name'] = b['name'].strip()
    if b.get('role') is not None:
        u['role'] = b['role'].strip()
    if b.get('email','').strip():
        u['email'] = b['email'].strip().lower()
    save_db(db)
    return jsonify({'user':{'id':uid,'name':u['name'],'email':u['email'],'role':u.get('role','Member')}})

# ── HELPERS ──────────────────────────────────────────
def auth_user():
    uid = get_uid()
    if not uid:
        return None, None
    db = load_db()
    ud = db['users'].get(uid)
    return uid, ud

def save_user(uid, ud):
    db = load_db()
    db['users'][uid] = ud
    save_db(db)

# ── SETTINGS ─────────────────────────────────────────
@app.route('/api/settings', methods=['GET','PUT'])
def settings():
    uid, ud = auth_user()
    if not uid:
        return jsonify({'error':'Auth required'}), 401
    if request.method == 'PUT':
        b = request.json or {}
        for k,v in b.items():
            if k in ud['settings']:
                ud['settings'][k] = v
        save_user(uid, ud)
    return jsonify(ud['settings'])

# ── TASKS ─────────────────────────────────────────────
@app.route('/api/tasks', methods=['GET','POST'])
def tasks():
    uid, ud = auth_user()
    if not uid:
        return jsonify({'error':'Auth required'}), 401
    if request.method == 'POST':
        b = request.json or {}
        pri = b.get('priority','medium')
        dr = {'low':ud['settings'].get('default_reminder_low',60),
              'medium':ud['settings'].get('default_reminder_medium',30),
              'high':ud['settings'].get('default_reminder_high',15)}
        ts = now()
        task = {
            'id':nxt(ud,'tasks'),'title':b.get('title','Untitled'),
            'description':b.get('description',''),'category':b.get('category','General'),
            'priority':pri,'status':b.get('status','pending'),
            'due_date':b.get('due_date') or None,'due_time':b.get('due_time') or None,
            'reminder_mins':b.get('reminder_mins', dr.get(pri,30)),
            'assigned_to':b.get('assigned_to',''),'project':b.get('project',''),
            'tags':json.dumps(b.get('tags',[])),'notes':b.get('notes',''),
            'progress':b.get('progress',0),'is_pinned':1 if b.get('is_pinned') else 0,
            'created_at':ts,'updated_at':ts,'completed_at':None,
            'reminder_sent':0,'snooze_until':None
        }
        ud['tasks'].insert(0, task)
        run_notifs(ud)
        save_user(uid, ud)
        return jsonify(task), 201
    tl = list(ud['tasks'])
    for arg in ['status','priority','category']:
        v = request.args.get(arg,'')
        if v: tl = [t for t in tl if t.get(arg)==v]
    q = request.args.get('search','').lower()
    if q: tl = [t for t in tl if q in (t.get('title','') or '').lower() or q in (t.get('description','') or '').lower()]
    tl.sort(key=lambda t: t.get('is_pinned',0), reverse=True)
    return jsonify(tl)

@app.route('/api/tasks/<int:tid>', methods=['GET','PUT','DELETE'])
def task(tid):
    uid, ud = auth_user()
    if not uid:
        return jsonify({'error':'Auth required'}), 401
    t = next((x for x in ud['tasks'] if x['id']==tid), None)
    if not t:
        return jsonify({'error':'Not found'}), 404
    if request.method == 'GET':
        return jsonify(t)
    if request.method == 'DELETE':
        ud['tasks'] = [x for x in ud['tasks'] if x['id']!=tid]
        ud['notifications'] = [n for n in ud.get('notifications',[]) if n.get('task_id')!=tid]
        save_user(uid, ud)
        return jsonify({'ok':True})
    b = request.json or {}
    old_st = t['status']
    for k in ['title','description','category','priority','status','due_date','due_time',
              'reminder_mins','assigned_to','project','notes','progress','is_pinned','snooze_until']:
        if k in b: t[k] = b[k]
    if 'tags' in b:
        t['tags'] = json.dumps(b['tags']) if isinstance(b['tags'],list) else b['tags']
    t['updated_at'] = now()
    ns = t['status']
    if ns == 'completed' and old_st != 'completed': t['completed_at'] = now()
    elif ns != 'completed': t['completed_at'] = None
    if 'due_date' in b or 'due_time' in b: t['reminder_sent'] = 0
    run_notifs(ud)
    save_user(uid, ud)
    return jsonify(t)

@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT'])
def snooze(tid):
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    mins = (request.json or {}).get('minutes', 10)
    su = (datetime.now() + timedelta(minutes=mins)).isoformat()
    for t in ud['tasks']:
        if t['id'] == tid:
            t['snooze_until'] = su; t['reminder_sent'] = 0; break
    ud['notifications'] = [n for n in ud.get('notifications',[])
                           if not (n.get('task_id')==tid and n.get('type')=='reminder')]
    save_user(uid, ud)
    return jsonify({'ok':True})

@app.route('/api/tasks/<int:tid>/pin', methods=['PUT'])
def pin(tid):
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    for t in ud['tasks']:
        if t['id'] == tid:
            t['is_pinned'] = 0 if t.get('is_pinned') else 1
            save_user(uid, ud)
            return jsonify({'is_pinned':t['is_pinned']})
    return jsonify({'error':'Not found'}), 404

# ── CATEGORIES ────────────────────────────────────────
@app.route('/api/categories', methods=['GET','POST'])
def categories():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    if request.method == 'POST':
        b = request.json or {}
        name = b.get('name','').strip()
        if not name: return jsonify({'error':'Name required'}), 400
        if any(c['name']==name for c in ud['categories']):
            return jsonify({'error':'Already exists'}), 400
        cat = {'id':nxt(ud,'categories'),'name':name,'color':b.get('color','#6366f1')}
        ud['categories'].append(cat)
        save_user(uid, ud)
        return jsonify(cat), 201
    return jsonify(ud['categories'])

@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def del_cat(cid):
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    ud['categories'] = [c for c in ud['categories'] if c['id']!=cid]
    save_user(uid, ud)
    return jsonify({'ok':True})

# ── NOTIFICATIONS ─────────────────────────────────────
@app.route('/api/notifications')
def notifs():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    run_notifs(ud); save_user(uid, ud)
    ns = [n for n in ud.get('notifications',[]) if not n.get('is_dismissed')]
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/new')
def notifs_new():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    run_notifs(ud); save_user(uid, ud)
    ns = [n for n in ud.get('notifications',[])
          if not n.get('is_read') and not n.get('is_dismissed') and n.get('type')!='created']
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
def read_notif(nid):
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    for n in ud.get('notifications',[]):
        if n['id'] == nid: n['is_read'] = 1; break
    save_user(uid, ud)
    return jsonify({'ok':True})

@app.route('/api/notifications/read-all', methods=['PUT'])
def read_all():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    for n in ud.get('notifications',[]): n['is_read'] = 1
    save_user(uid, ud)
    return jsonify({'ok':True})

@app.route('/api/notifications/clear-read', methods=['DELETE'])
def clear_read():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    ud['notifications'] = [n for n in ud.get('notifications',[]) if not n.get('is_read')]
    save_user(uid, ud)
    return jsonify({'ok':True})

# ── STATS ─────────────────────────────────────────────
@app.route('/api/statistics')
def stats():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    tl = ud.get('tasks',[])
    td = datetime.now().strftime('%Y-%m-%d')
    total = len(tl)
    comp = sum(1 for t in tl if t.get('status')=='completed')
    pend = sum(1 for t in tl if t.get('status')=='pending')
    prog = sum(1 for t in tl if t.get('status')=='in_progress')
    ov = sum(1 for t in tl if t.get('status')!='completed' and t.get('due_date') and t.get('due_date','')<td)
    dt = sum(1 for t in tl if t.get('status')!='completed' and t.get('due_date')==td)
    hp = sum(1 for t in tl if t.get('priority')=='high' and t.get('status')!='completed')
    return jsonify({'total':total,'completed':comp,'pending':pend,'in_progress':prog,
                    'overdue':ov,'due_today':dt,'high_priority':hp,
                    'completion_rate':round(comp/total*100,1) if total>0 else 0})

# ── EXPORT/IMPORT ─────────────────────────────────────
@app.route('/api/export')
def export():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    return jsonify({'exported_at':now(),'tasks':ud.get('tasks',[]),'categories':ud.get('categories',[])})

@app.route('/api/import', methods=['POST'])
def import_data():
    uid, ud = auth_user()
    if not uid: return jsonify({'error':'Auth required'}), 401
    inc = (request.json or {}).get('tasks',[])
    ts = now(); count = 0
    for t in inc:
        ud['tasks'].insert(0, {
            'id':nxt(ud,'tasks'),'title':t.get('title','Imported'),
            'description':t.get('description',''),'category':t.get('category','General'),
            'priority':t.get('priority','medium'),'status':t.get('status','pending'),
            'due_date':t.get('due_date'),'due_time':t.get('due_time'),
            'reminder_mins':t.get('reminder_mins',30),'assigned_to':t.get('assigned_to',''),
            'project':t.get('project',''),'tags':json.dumps(t.get('tags',[])),
            'notes':t.get('notes',''),'created_at':ts,'updated_at':ts,
            'completed_at':None,'reminder_sent':0,'is_pinned':0,'progress':0,'snooze_until':None
        })
        count += 1
    save_user(uid, ud)
    return jsonify({'imported':count})

@app.route('/api/health')
def health():
    return jsonify({'status':'ok','time':now()})