from flask import Flask, request, jsonify, Response
import json, os
from datetime import datetime, timedelta

try:
    import requests as req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

app = Flask(__name__)

# ── Config ───────────────────────────────────────────────────
SB_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SB_KEY = os.environ.get('SUPABASE_KEY', '')

# Fallback to /tmp JSON if Supabase not configured
DATA_FILE = '/tmp/taskpro.json'

DEFAULT_DATA = {
    "tasks": [],
    "categories": [
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
    ],
    "notifications": [],
    "settings": {
        "default_reminder_low":60,
        "default_reminder_medium":30,
        "default_reminder_high":15,
        "sound_enabled":1,
        "popup_enabled":1,
        "browser_notif_enabled":1,
        "popup_duration_low":5,
        "popup_duration_medium":8,
        "popup_duration_high":12,
        "auto_snooze_mins":10,
        "check_interval_secs":30
    },
    "ids":{"tasks":1,"categories":11,"notifications":1}
}

USE_SUPABASE = bool(SB_URL and SB_KEY and HAS_REQUESTS)

# ── JSON Fallback (when Supabase not available) ───────────────
def ld():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,'r') as f:
                data = json.load(f)
                for k in DEFAULT_DATA:
                    if k not in data:
                        data[k] = DEFAULT_DATA[k]
                return data
    except:
        pass
    return json.loads(json.dumps(DEFAULT_DATA))

def sv(data):
    try:
        with open(DATA_FILE,'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Save error:", e)

def nid(data, col):
    v = data["ids"].get(col, 1)
    data["ids"][col] = v + 1
    return v

# ── Supabase Helpers ─────────────────────────────────────────
def sb_headers():
    return {
        'apikey': SB_KEY,
        'Authorization': 'Bearer ' + SB_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def sb_get(table, params=None):
    try:
        r = req.get(
            f'{SB_URL}/rest/v1/{table}',
            headers=sb_headers(),
            params=params or {},
            timeout=8
        )
        if r.status_code in (200, 206):
            return r.json()
        print(f"SB GET {table} error: {r.status_code} {r.text[:200]}")
        return []
    except Exception as e:
        print(f"SB GET error: {e}")
        return []

def sb_post(table, data):
    try:
        r = req.post(
            f'{SB_URL}/rest/v1/{table}',
            headers=sb_headers(),
            json=data,
            timeout=8
        )
        if r.status_code in (200, 201):
            res = r.json()
            return res[0] if isinstance(res, list) and res else res
        print(f"SB POST {table} error: {r.status_code} {r.text[:200]}")
        return None
    except Exception as e:
        print(f"SB POST error: {e}")
        return None

def sb_patch(table, match, data):
    try:
        params = {k: f'eq.{v}' for k, v in match.items()}
        r = req.patch(
            f'{SB_URL}/rest/v1/{table}',
            headers=sb_headers(),
            params=params,
            json=data,
            timeout=8
        )
        if r.status_code in (200, 204):
            try:
                res = r.json()
                return res[0] if isinstance(res, list) and res else res
            except:
                return data
        print(f"SB PATCH {table} error: {r.status_code} {r.text[:200]}")
        return None
    except Exception as e:
        print(f"SB PATCH error: {e}")
        return None

def sb_delete(table, match):
    try:
        params = {k: f'eq.{v}' for k, v in match.items()}
        r = req.delete(
            f'{SB_URL}/rest/v1/{table}',
            headers=sb_headers(),
            params=params,
            timeout=8
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"SB DELETE error: {e}")
        return False

# ── Now() ─────────────────────────────────────────────────────
def now():
    return datetime.now().isoformat()

# ── Notification Generator ────────────────────────────────────
def gen_notifs():
    try:
        n = datetime.now()
        td = n.strftime('%Y-%m-%d')
        tm = (n + timedelta(days=1)).strftime('%Y-%m-%d')

        if USE_SUPABASE:
            existing = sb_get('notifications', {
                'select': 'task_id,type',
                'is_dismissed': 'eq.0'
            }) or []
            tasks = sb_get('tasks', {
                'select': '*',
                'status': 'neq.completed'
            }) or []
        else:
            data = ld()
            existing = [x for x in data.get('notifications',[]) if not x.get('is_dismissed')]
            tasks = [t for t in data.get('tasks',[]) if t.get('status') != 'completed']

        ex = set()
        for x in existing:
            ex.add(f"{x.get('task_id','')}_{x.get('type','')}")

        for t in tasks:
            if not t.get('due_date'):
                continue
            tid = t['id']
            pri = t.get('priority','medium')
            u = '🔴' if pri=='high' else '🟡' if pri=='medium' else '🟢'
            dd = t.get('due_date','')

            if dd < td:
                k = f"{tid}_overdue"
                if k not in ex:
                    days = (n - datetime.strptime(dd,'%Y-%m-%d')).days
                    notif = {
                        'task_id':tid,
                        'message':f"{u} OVERDUE ({days}d): '{t['title']}'",
                        'type':'overdue','priority':pri,
                        'is_read':0,'is_dismissed':0,
                        'created_at':now(),
                        'task_title':t['title'],'task_priority':pri
                    }
                    if USE_SUPABASE:
                        sb_post('notifications', notif)
                    else:
                        data = ld()
                        notif['id'] = nid(data,'notifications')
                        data['notifications'].insert(0, notif)
                        sv(data)

            elif dd == td:
                k = f"{tid}_due_today"
                if k not in ex:
                    ti = f" at {t['due_time']}" if t.get('due_time') else ''
                    notif = {
                        'task_id':tid,
                        'message':f"{u} Due Today{ti}: '{t['title']}'",
                        'type':'due_today','priority':pri,
                        'is_read':0,'is_dismissed':0,
                        'created_at':now(),
                        'task_title':t['title'],'task_priority':pri
                    }
                    if USE_SUPABASE:
                        sb_post('notifications', notif)
                    else:
                        data = ld()
                        notif['id'] = nid(data,'notifications')
                        data['notifications'].insert(0, notif)
                        sv(data)

            if t.get('due_time') and not t.get('reminder_sent'):
                try:
                    due = datetime.strptime(f"{dd} {t['due_time']}", '%Y-%m-%d %H:%M')
                    rm = t.get('reminder_mins', 30) or 30
                    ra = due - timedelta(minutes=rm)
                    if n >= ra and n < due:
                        k = f"{tid}_reminder"
                        if k not in ex:
                            ml = max(0, int((due-n).total_seconds()/60))
                            notif = {
                                'task_id':tid,
                                'message':f"{u} REMINDER: '{t['title']}' in {ml} min!",
                                'type':'reminder','priority':pri,
                                'is_read':0,'is_dismissed':0,
                                'created_at':now(),
                                'task_title':t['title'],'task_priority':pri
                            }
                            if USE_SUPABASE:
                                sb_post('notifications', notif)
                                sb_patch('tasks',{'id':tid},{'reminder_sent':1})
                            else:
                                data = ld()
                                notif['id'] = nid(data,'notifications')
                                data['notifications'].insert(0, notif)
                                for task in data['tasks']:
                                    if task['id'] == tid:
                                        task['reminder_sent'] = 1
                                        break
                                sv(data)
                except:
                    pass

            if pri == 'high' and dd == tm:
                k = f"{tid}_upcoming_high"
                if k not in ex:
                    notif = {
                        'task_id':tid,
                        'message':f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'",
                        'type':'upcoming_high','priority':'high',
                        'is_read':0,'is_dismissed':0,
                        'created_at':now(),
                        'task_title':t['title'],'task_priority':'high'
                    }
                    if USE_SUPABASE:
                        sb_post('notifications', notif)
                    else:
                        data = ld()
                        notif['id'] = nid(data,'notifications')
                        data['notifications'].insert(0, notif)
                        sv(data)
    except Exception as e:
        print(f"gen_notifs error: {e}")

# ── CORS ──────────────────────────────────────────────────────
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return r

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        resp = jsonify({})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return resp, 200

# ── ROOT ─────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def home():
    return Response(get_html(), content_type='text/html; charset=utf-8')

# ── SETTINGS ─────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET','PUT'])
def settings_route():
    if USE_SUPABASE:
        if request.method == 'PUT':
            b = request.json or {}
            sb_patch('settings',{'id':1}, b)
        rows = sb_get('settings',{'id':'eq.1'}) or []
        return jsonify(rows[0] if rows else DEFAULT_DATA['settings'])
    else:
        data = ld()
        if request.method == 'PUT':
            b = request.json or {}
            for k,v in b.items():
                if k in data['settings']:
                    data['settings'][k] = v
            sv(data)
        return jsonify(data['settings'])

# ── TASKS ─────────────────────────────────────────────────────
@app.route('/api/tasks', methods=['GET','POST'])
def tasks_route():
    if USE_SUPABASE:
        return tasks_supabase()
    else:
        return tasks_local()

def tasks_supabase():
    if request.method == 'POST':
        b = request.json or {}
        pri = b.get('priority','medium')
        se = (sb_get('settings',{'id':'eq.1'}) or [{}])[0]
        dr = {
            'low':    se.get('default_reminder_low',60),
            'medium': se.get('default_reminder_medium',30),
            'high':   se.get('default_reminder_high',15)
        }
        ts = now()
        task_data = {
            'title':           b.get('title','Untitled'),
            'description':     b.get('description',''),
            'category':        b.get('category','General'),
            'priority':        pri,
            'status':          b.get('status','pending'),
            'due_date':        b.get('due_date') or None,
            'due_time':        b.get('due_time') or None,
            'reminder_mins':   b.get('reminder_mins', dr.get(pri,30)),
            'assigned_to':     b.get('assigned_to',''),
            'project':         b.get('project',''),
            'tags':            json.dumps(b.get('tags',[])),
            'notes':           b.get('notes',''),
            'estimated_hours': b.get('estimated_hours',0),
            'progress':        b.get('progress',0),
            'is_pinned':       1 if b.get('is_pinned') else 0,
            'created_at':      ts,
            'updated_at':      ts,
            'completed_at':    None,
            'reminder_sent':   0,
            'snooze_until':    None
        }
        task = sb_post('tasks', task_data)
        gen_notifs()
        return jsonify(task or task_data), 201

    # GET
    params = {
        'select': '*',
        'order':  'is_pinned.desc,created_at.desc'
    }
    st = request.args.get('status','')
    pr = request.args.get('priority','')
    ca = request.args.get('category','')
    se = request.args.get('search','')
    if st: params['status']   = f'eq.{st}'
    if pr: params['priority'] = f'eq.{pr}'
    if ca: params['category'] = f'eq.{ca}'

    tasks = sb_get('tasks', params) or []
    if se:
        sq = se.lower()
        tasks = [t for t in tasks
                 if sq in (t.get('title','') or '').lower()
                 or sq in (t.get('description','') or '').lower()]
    return jsonify(tasks)

def tasks_local():
    data = ld()
    if request.method == 'POST':
        b = request.json or {}
        pri = b.get('priority','medium')
        se = data['settings']
        dr = {
            'low':    se.get('default_reminder_low',60),
            'medium': se.get('default_reminder_medium',30),
            'high':   se.get('default_reminder_high',15)
        }
        ts = now()
        task = {
            'id':              nid(data,'tasks'),
            'title':           b.get('title','Untitled'),
            'description':     b.get('description',''),
            'category':        b.get('category','General'),
            'priority':        pri,
            'status':          b.get('status','pending'),
            'due_date':        b.get('due_date') or None,
            'due_time':        b.get('due_time') or None,
            'reminder_mins':   b.get('reminder_mins', dr.get(pri,30)),
            'assigned_to':     b.get('assigned_to',''),
            'project':         b.get('project',''),
            'tags':            json.dumps(b.get('tags',[])),
            'notes':           b.get('notes',''),
            'estimated_hours': b.get('estimated_hours',0),
            'progress':        b.get('progress',0),
            'is_pinned':       1 if b.get('is_pinned') else 0,
            'created_at':      ts,
            'updated_at':      ts,
            'completed_at':    None,
            'reminder_sent':   0,
            'snooze_until':    None
        }
        data['tasks'].insert(0, task)
        gen_notifs()
        sv(data)
        return jsonify(task), 201

    tasks = list(data['tasks'])
    st = request.args.get('status','')
    pr = request.args.get('priority','')
    ca = request.args.get('category','')
    se = request.args.get('search','')
    if st: tasks = [t for t in tasks if t.get('status')==st]
    if pr: tasks = [t for t in tasks if t.get('priority')==pr]
    if ca: tasks = [t for t in tasks if t.get('category')==ca]
    if se:
        sq = se.lower()
        tasks = [t for t in tasks
                 if sq in (t.get('title','') or '').lower()
                 or sq in (t.get('description','') or '').lower()]
    tasks.sort(key=lambda t: t.get('is_pinned',0), reverse=True)
    return jsonify(tasks)

# ── SINGLE TASK ───────────────────────────────────────────────
@app.route('/api/tasks/<int:tid>', methods=['GET','PUT','DELETE'])
def task_route(tid):
    if USE_SUPABASE:
        return task_supabase(tid)
    else:
        return task_local(tid)

def task_supabase(tid):
    if request.method == 'GET':
        rows = sb_get('tasks',{'id':f'eq.{tid}'}) or []
        return jsonify(rows[0]) if rows else (jsonify({'error':'Not found'}),404)

    if request.method == 'DELETE':
        sb_delete('notifications',{'task_id':tid})
        sb_delete('tasks',{'id':tid})
        return jsonify({'ok':True})

    # PUT
    b = request.json or {}
    rows = sb_get('tasks',{'id':f'eq.{tid}'}) or []
    if not rows:
        return jsonify({'error':'Not found'}),404
    cur = rows[0]

    update = {}
    for k in ['title','description','category','priority','status','due_date',
              'due_time','reminder_mins','assigned_to','project','notes',
              'estimated_hours','progress','is_pinned','snooze_until']:
        if k in b:
            update[k] = b[k]
    if 'tags' in b:
        update['tags'] = json.dumps(b['tags']) if isinstance(b['tags'],list) else b['tags']
    update['updated_at'] = now()

    ns = b.get('status', cur.get('status','pending'))
    if ns == 'completed' and cur.get('status') != 'completed':
        update['completed_at'] = now()
    elif ns != 'completed':
        update['completed_at'] = None
    if 'due_date' in b or 'due_time' in b:
        update['reminder_sent'] = 0

    result = sb_patch('tasks',{'id':tid}, update)
    gen_notifs()
    if result:
        return jsonify(result)
    # Return merged if patch returned nothing
    cur.update(update)
    return jsonify(cur)

def task_local(tid):
    data = ld()
    task = next((t for t in data['tasks'] if t['id']==tid), None)
    if not task:
        return jsonify({'error':'Not found'}),404

    if request.method == 'GET':
        return jsonify(task)

    if request.method == 'DELETE':
        data['tasks'] = [t for t in data['tasks'] if t['id']!=tid]
        data['notifications'] = [n for n in data.get('notifications',[]) if n.get('task_id')!=tid]
        sv(data)
        return jsonify({'ok':True})

    # PUT
    b = request.json or {}
    old_st = task['status']
    for k in ['title','description','category','priority','status','due_date',
              'due_time','reminder_mins','assigned_to','project','notes',
              'estimated_hours','progress','is_pinned','snooze_until']:
        if k in b:
            task[k] = b[k]
    if 'tags' in b:
        task['tags'] = json.dumps(b['tags']) if isinstance(b['tags'],list) else b['tags']
    task['updated_at'] = now()
    ns = task['status']
    if ns == 'completed' and old_st != 'completed':
        task['completed_at'] = now()
    elif ns != 'completed':
        task['completed_at'] = None
    if 'due_date' in b or 'due_time' in b:
        task['reminder_sent'] = 0
    gen_notifs()
    sv(data)
    return jsonify(task)

# ── SNOOZE ────────────────────────────────────────────────────
@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT'])
def snooze_route(tid):
    mins = (request.json or {}).get('minutes',10)
    snooze_until = (datetime.now()+timedelta(minutes=mins)).isoformat()
    if USE_SUPABASE:
        sb_patch('tasks',{'id':tid},{'snooze_until':snooze_until,'reminder_sent':0})
        sb_patch('notifications',{'task_id':tid,'type':'reminder'},{'is_dismissed':1})
    else:
        data = ld()
        for t in data['tasks']:
            if t['id']==tid:
                t['snooze_until'] = snooze_until
                t['reminder_sent'] = 0
                break
        data['notifications'] = [n for n in data.get('notifications',[])
                                  if not (n.get('task_id')==tid and n.get('type')=='reminder')]
        sv(data)
    return jsonify({'ok':True,'snoozed_until':snooze_until})

# ── PIN ───────────────────────────────────────────────────────
@app.route('/api/tasks/<int:tid>/pin', methods=['PUT'])
def pin_route(tid):
    if USE_SUPABASE:
        rows = sb_get('tasks',{'id':f'eq.{tid}'}) or []
        if not rows: return jsonify({'error':'Not found'}),404
        new_pin = 0 if rows[0].get('is_pinned') else 1
        sb_patch('tasks',{'id':tid},{'is_pinned':new_pin})
        return jsonify({'is_pinned':new_pin})
    else:
        data = ld()
        for t in data['tasks']:
            if t['id']==tid:
                t['is_pinned'] = 0 if t.get('is_pinned') else 1
                sv(data)
                return jsonify({'is_pinned':t['is_pinned']})
        return jsonify({'error':'Not found'}),404

# ── CATEGORIES ────────────────────────────────────────────────
@app.route('/api/categories', methods=['GET','POST'])
def cats_route():
    if USE_SUPABASE:
        if request.method == 'POST':
            b = request.json or {}
            cat = sb_post('categories',{'name':b.get('name'),'color':b.get('color','#6366f1')})
            return jsonify(cat or {}), 201
        return jsonify(sb_get('categories',{'order':'name.asc'}) or [])
    else:
        data = ld()
        if request.method == 'POST':
            b = request.json or {}
            name = b.get('name','')
            if any(c['name']==name for c in data['categories']):
                return jsonify({'error':'Exists'}),400
            cat = {'id':nid(data,'categories'),'name':name,'color':b.get('color','#6366f1')}
            data['categories'].append(cat)
            sv(data)
            return jsonify(cat),201
        return jsonify(data['categories'])

@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def cat_route(cid):
    if USE_SUPABASE:
        sb_delete('categories',{'id':cid})
    else:
        data = ld()
        data['categories'] = [c for c in data['categories'] if c['id']!=cid]
        sv(data)
    return jsonify({'ok':True})

# ── NOTIFICATIONS ─────────────────────────────────────────────
@app.route('/api/notifications', methods=['GET'])
def notifs_route():
    gen_notifs()
    if USE_SUPABASE:
        ns = sb_get('notifications',{
            'is_dismissed':'eq.0',
            'order':'created_at.desc',
            'limit':'80'
        }) or []
    else:
        data = ld()
        ns = [n for n in data.get('notifications',[]) if not n.get('is_dismissed')]
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/new', methods=['GET'])
def new_notifs():
    gen_notifs()
    if USE_SUPABASE:
        ns = sb_get('notifications',{
            'is_read':'eq.0',
            'is_dismissed':'eq.0',
            'order':'created_at.desc'
        }) or []
    else:
        data = ld()
        ns = [n for n in data.get('notifications',[])
              if not n.get('is_read') and not n.get('is_dismissed')]
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/<int:nid2>/read', methods=['PUT'])
def read_n(nid2):
    if USE_SUPABASE:
        sb_patch('notifications',{'id':nid2},{'is_read':1})
    else:
        data = ld()
        for n in data.get('notifications',[]):
            if n['id']==nid2:
                n['is_read']=1; break
        sv(data)
    return jsonify({'ok':True})

@app.route('/api/notifications/read-all', methods=['PUT'])
def read_all():
    if USE_SUPABASE:
        try:
            req.patch(
                f'{SB_URL}/rest/v1/notifications',
                headers=sb_headers(),
                params={'is_dismissed':'eq.0'},
                json={'is_read':1}, timeout=8
            )
        except:
            pass
    else:
        data = ld()
        for n in data.get('notifications',[]):
            n['is_read']=1
        sv(data)
    return jsonify({'ok':True})

@app.route('/api/notifications/clear-read', methods=['DELETE'])
def clear_read():
    if USE_SUPABASE:
        try:
            req.delete(
                f'{SB_URL}/rest/v1/notifications',
                headers=sb_headers(),
                params={'is_read':'eq.1'}, timeout=8
            )
        except:
            pass
    else:
        data = ld()
        data['notifications'] = [n for n in data.get('notifications',[]) if not n.get('is_read')]
        sv(data)
    return jsonify({'ok':True})

# ── STATISTICS ────────────────────────────────────────────────
@app.route('/api/statistics', methods=['GET'])
def stats_route():
    if USE_SUPABASE:
        tasks = sb_get('tasks',{'select':'status,priority,due_date'}) or []
    else:
        tasks = ld().get('tasks',[])

    td = datetime.now().strftime('%Y-%m-%d')
    total = len(tasks)
    comp  = sum(1 for t in tasks if t.get('status')=='completed')
    pend  = sum(1 for t in tasks if t.get('status')=='pending')
    prog  = sum(1 for t in tasks if t.get('status')=='in_progress')
    ov    = sum(1 for t in tasks if t.get('status')!='completed'
                and t.get('due_date') and t.get('due_date','') < td)
    dt    = sum(1 for t in tasks if t.get('status')!='completed'
                and t.get('due_date','') == td)
    hp    = sum(1 for t in tasks if t.get('priority')=='high'
                and t.get('status')!='completed')
    return jsonify({
        'total':total,'completed':comp,'pending':pend,
        'in_progress':prog,'overdue':ov,'due_today':dt,
        'high_priority':hp,
        'completion_rate': round(comp/total*100,1) if total>0 else 0
    })

# ── EXPORT / IMPORT ──────────────────────────────────────────
@app.route('/api/export', methods=['GET'])
def export_route():
    if USE_SUPABASE:
        tasks = sb_get('tasks',{'select':'*'}) or []
        cats  = sb_get('categories',{'select':'*'}) or []
    else:
        data  = ld()
        tasks = data.get('tasks',[])
        cats  = data.get('categories',[])
    return jsonify({'exported_at':now(),'tasks':tasks,'categories':cats})

@app.route('/api/import', methods=['POST'])
def import_route():
    inc = (request.json or {}).get('tasks',[])
    ts = now()
    count = 0
    if USE_SUPABASE:
        for t in inc:
            sb_post('tasks',{
                'title':         t.get('title','Imported'),
                'description':   t.get('description',''),
                'category':      t.get('category','General'),
                'priority':      t.get('priority','medium'),
                'status':        t.get('status','pending'),
                'due_date':      t.get('due_date'),
                'due_time':      t.get('due_time'),
                'reminder_mins': t.get('reminder_mins',30),
                'assigned_to':   t.get('assigned_to',''),
                'project':       t.get('project',''),
                'tags':          json.dumps(t.get('tags',[])),
                'notes':         t.get('notes',''),
                'created_at':    ts,'updated_at':ts,
                'reminder_sent': 0,'is_pinned':0,'progress':0
            })
            count += 1
    else:
        data = ld()
        for t in inc:
            task = {
                'id':            nid(data,'tasks'),
                'title':         t.get('title','Imported'),
                'description':   t.get('description',''),
                'category':      t.get('category','General'),
                'priority':      t.get('priority','medium'),
                'status':        t.get('status','pending'),
                'due_date':      t.get('due_date'),
                'due_time':      t.get('due_time'),
                'reminder_mins': t.get('reminder_mins',30),
                'assigned_to':   t.get('assigned_to',''),
                'project':       t.get('project',''),
                'tags':          json.dumps(t.get('tags',[])),
                'notes':         t.get('notes',''),
                'created_at':    ts,'updated_at':ts,
                'completed_at':  None,'reminder_sent':0,
                'is_pinned':0,'progress':0
            }
            data['tasks'].insert(0,task)
            count += 1
        sv(data)
    return jsonify({'imported':count})

# ── HEALTH CHECK ─────────────────────────────────────────────
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'supabase': USE_SUPABASE,
        'time': now()
    })

# ══════════════════════════════════════════════════════════════
#  HTML
# ══════════════════════════════════════════════════════════════
def get_html():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TaskPro — Dashboard</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --P:#5b5ef4;--PD:#4745d1;--PL:#a5b4fc;--S:#06b6d4;
  --OK:#10b981;--WA:#f59e0b;--ER:#ef4444;
  --bg:#eef2ff;--card:#fff;--inp:#f8fafc;
  --tx:#1e1b4b;--txm:#6b7280;--bdr:#e5e7eb;
  --sh:0 2px 12px rgba(91,94,244,.08);
  --sh2:0 8px 40px rgba(91,94,244,.15);
  --r:14px;--sw:238px;--hh:60px
}
body.dark{
  --bg:#0d0f1a;--card:#161b2e;--inp:#0d0f1a;
  --tx:#e2e8ff;--txm:#8892b0;--bdr:#1e2a45;
  --sh:0 2px 12px rgba(0,0,0,.3);--sh2:0 8px 40px rgba(0,0,0,.5)
}
body{font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--tx);font-size:14px;overflow:hidden;height:100vh}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:2px}
.app{display:flex;width:100vw;height:100vh}

/* SIDEBAR */
.sb{width:var(--sw);flex-shrink:0;background:var(--card);border-right:1px solid var(--bdr);display:flex;flex-direction:column;height:100vh;transition:width .28s ease;overflow:hidden;z-index:50}
.sb.slim{width:58px}
.sb-br{height:var(--hh);display:flex;align-items:center;gap:11px;padding:0 15px;border-bottom:1px solid var(--bdr);flex-shrink:0}
.sb-lo{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;flex-shrink:0;box-shadow:0 4px 12px rgba(91,94,244,.3)}
.sb-nm{font-size:16px;font-weight:800;white-space:nowrap;background:linear-gradient(135deg,var(--P),var(--S));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sb.slim .sb-nm{display:none}
.sb-nv{flex:1;overflow-y:auto;padding:10px 6px}
.nsec{margin-bottom:16px}
.nlbl{font-size:9px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:var(--txm);padding:0 10px;margin-bottom:5px;white-space:nowrap}
.sb.slim .nlbl{opacity:0}
.nbt{width:100%;display:flex;align-items:center;gap:9px;padding:9px 10px;border:none;background:none;border-radius:9px;cursor:pointer;color:var(--txm);transition:all .2s;text-align:left;white-space:nowrap;overflow:hidden;font-size:12.5px;font-weight:500}
.nbt i{width:16px;text-align:center;font-size:13px;flex-shrink:0}
.nbt .nt{flex:1}
.nbt .nc{background:var(--bg);color:var(--txm);font-size:9px;padding:2px 7px;border-radius:10px;flex-shrink:0;font-weight:700}
.nbt:hover{background:rgba(91,94,244,.08);color:var(--P)}
.nbt.on{background:linear-gradient(135deg,var(--P),var(--PD));color:#fff;box-shadow:0 4px 12px rgba(91,94,244,.25)}
.nbt.on .nc{background:rgba(255,255,255,.25);color:#fff}
.sb.slim .nbt .nt,.sb.slim .nbt .nc{display:none}
.sb.slim .nbt{justify-content:center;padding:10px}

/* MAIN */
.rt{flex:1;display:flex;flex-direction:column;min-width:0;height:100vh;overflow:hidden}
.hd{height:var(--hh);background:var(--card);border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px;padding:0 20px;flex-shrink:0}
.hbt{width:36px;height:36px;border:none;background:var(--bg);border-radius:9px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--txm);position:relative;transition:all .2s;flex-shrink:0;font-size:13px}
.hbt:hover{background:var(--P);color:#fff;transform:translateY(-1px)}
.bdg{position:absolute;top:-4px;right:-4px;background:var(--ER);color:#fff;font-size:8px;min-width:17px;height:17px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800}
.sw{flex:1;max-width:480px;display:flex;align-items:center;gap:8px;background:var(--bg);border:1.5px solid var(--bdr);border-radius:10px;padding:0 14px;transition:all .2s}
.sw:focus-within{border-color:var(--P);background:var(--card);box-shadow:0 0 0 3px rgba(91,94,244,.1)}
.sw i{color:var(--txm);font-size:12px}
.sw input{flex:1;border:none;background:none;outline:none;padding:9px 0;color:var(--tx);font-size:13px}
.sw input::placeholder{color:var(--txm)}
.hrt{margin-left:auto;display:flex;align-items:center;gap:7px}
.ava{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:13px;cursor:pointer}

/* CONTENT */
.ctn{flex:1;overflow-y:auto;padding:22px 24px}
.pg{display:none;flex-direction:column;gap:16px;min-height:100%}
.pg.on{display:flex}
.pgh{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px}
.pgh h1{font-size:22px;font-weight:800;margin-bottom:3px}
.pgh p{color:var(--txm);font-size:12px}
.pghr{display:flex;gap:8px;flex-wrap:wrap}

/* BUTTONS */
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border:none;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap}
.bp{background:linear-gradient(135deg,var(--P),var(--PD));color:#fff;box-shadow:0 4px 12px rgba(91,94,244,.28)}
.bp:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(91,94,244,.38)}
.bg2{background:var(--bg);color:var(--tx);border:1.5px solid var(--bdr)}
.bg2:hover{background:var(--bdr)}
.bok{background:var(--OK);color:#fff}
.bsm{padding:6px 13px;font-size:12px}

/* STATS */
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.sc{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);padding:18px;display:flex;align-items:center;gap:14px;transition:all .25s;position:relative;overflow:hidden;box-shadow:var(--sh)}
.sc::before{content:"";position:absolute;top:0;left:0;right:0;height:3px}
.sc.c1::before{background:linear-gradient(90deg,var(--P),var(--PL))}
.sc.c2::before{background:linear-gradient(90deg,var(--OK),#34d399)}
.sc.c3::before{background:linear-gradient(90deg,var(--S),#67e8f9)}
.sc.c4::before{background:linear-gradient(90deg,var(--ER),#fca5a5)}
.sc.c5::before{background:linear-gradient(90deg,var(--WA),#fde68a)}
.sc:hover{transform:translateY(-4px);box-shadow:var(--sh2)}
.sc-i{width:42px;height:42px;border-radius:11px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:17px}
.c1 .sc-i{background:rgba(91,94,244,.1);color:var(--P)}
.c2 .sc-i{background:rgba(16,185,129,.1);color:var(--OK)}
.c3 .sc-i{background:rgba(6,182,212,.1);color:var(--S)}
.c4 .sc-i{background:rgba(239,68,68,.1);color:var(--ER)}
.c5 .sc-i{background:rgba(245,158,11,.1);color:var(--WA)}
.sc-v{font-size:26px;font-weight:800;line-height:1}
.sc-l{color:var(--txm);font-size:10.5px;margin-top:3px}

/* GRID */
.dg{display:grid;grid-template-columns:1fr 260px;gap:16px;flex:1;min-height:0}
@media(max-width:1050px){.dg{grid-template-columns:1fr}.dps{display:none!important}}

/* CARD */
.crd{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--sh)}
.crh{padding:14px 18px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0}
.crh h2{font-size:14px;font-weight:700}
.crb{padding:14px;flex:1;overflow-y:auto}

/* FILTERS */
.flt{display:flex;gap:6px;flex-wrap:wrap}
.flt select{padding:6px 10px;border:1.5px solid var(--bdr);border-radius:7px;background:var(--inp);color:var(--tx);font-size:11px;cursor:pointer;outline:none;transition:all .2s;font-weight:500}
.flt select:focus{border-color:var(--P)}

/* TASK LIST */
.tl{overflow-y:auto;flex:1}
.tr{display:flex;align-items:flex-start;gap:12px;padding:14px 18px;border-bottom:1px solid var(--bdr);transition:background .15s;cursor:pointer}
.tr:last-child{border-bottom:none}
.tr:hover{background:rgba(91,94,244,.03)}
.tr.dn{opacity:.5}
.tr.ovr{border-left:3px solid var(--ER)}
.tr.pnd{border-left:3px solid var(--WA)}
.ck{width:20px;height:20px;border:2.5px solid var(--bdr);border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer;margin-top:2px;transition:all .2s}
.ck:hover{border-color:var(--P)}
.ck.dn{background:var(--OK);border-color:var(--OK);color:#fff}
.tif{flex:1;min-width:0}
.tnm{font-weight:600;font-size:13px;margin-bottom:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;line-height:1.4}
.tr.dn .tnm{text-decoration:line-through;color:var(--txm)}
.tds{font-size:11px;color:var(--txm);margin-bottom:7px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.5}
.tmt{display:flex;gap:10px;flex-wrap:wrap;font-size:10px;color:var(--txm)}
.tmt i{margin-right:3px;font-size:9px}
.ovtx{color:var(--ER)!important;font-weight:700}
.tg{padding:2px 8px;background:rgba(91,94,244,.08);border-radius:20px;font-size:8px;color:var(--P);margin-top:4px;margin-right:3px;display:inline-flex;font-weight:600}
.prb{padding:2px 7px;border-radius:5px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.prh{background:rgba(239,68,68,.1);color:var(--ER)}
.prm{background:rgba(245,158,11,.1);color:var(--WA)}
.prl{background:rgba(16,185,129,.1);color:var(--OK)}
.stb2{padding:2px 9px;border-radius:20px;font-size:8px;font-weight:700}
.stp2{background:rgba(245,158,11,.1);color:var(--WA)}
.sti2{background:rgba(91,94,244,.1);color:var(--P)}
.stc2{background:rgba(16,185,129,.1);color:var(--OK)}
.tac{display:flex;gap:4px;flex-shrink:0;opacity:0;transition:opacity .2s}
.tr:hover .tac{opacity:1}
.abt{width:28px;height:28px;border:none;border-radius:7px;background:var(--bg);cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;font-size:11px;transition:all .2s}
.abt:hover{background:var(--P);color:#fff}
.abt.dl:hover{background:var(--ER);color:#fff}

/* EMPTY */
.emp{padding:50px 20px;text-align:center;color:var(--txm)}
.emp-ic{width:68px;height:68px;border-radius:18px;background:linear-gradient(135deg,rgba(91,94,244,.1),rgba(6,182,212,.1));display:flex;align-items:center;justify-content:center;font-size:26px;margin:0 auto 16px;color:var(--P)}
.emp h3{font-size:15px;font-weight:700;margin-bottom:6px;color:var(--tx)}
.emp p{font-size:12px;margin-bottom:14px}

/* PROGRESS RING */
.rw{display:flex;align-items:center;justify-content:center;gap:18px;padding:10px 0}
.rc{position:relative;width:80px;height:80px}
.rc svg{transform:rotate(-90deg)}
.rm{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}
.rp{font-size:16px;font-weight:800}
.rl{font-size:9px;color:var(--txm)}
.rs{display:flex;flex-direction:column;gap:6px}
.ri{display:flex;align-items:center;gap:6px;font-size:11px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

/* CAT PANEL */
.cpit{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;cursor:pointer;transition:background .15s}
.cpit:hover{background:rgba(91,94,244,.06)}
.cpd{width:9px;height:9px;border-radius:50%}
.cpn{flex:1;font-size:11.5px;font-weight:500}
.cpc{font-size:10px;color:var(--txm);background:var(--bg);padding:1px 7px;border-radius:10px;font-weight:600}

/* NOTIFICATION DROPDOWN */
.ndp{position:fixed;top:calc(var(--hh)+6px);right:14px;width:340px;background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);box-shadow:var(--sh2);z-index:999;opacity:0;pointer-events:none;transform:translateY(10px);transition:all .25s}
.ndp.on{opacity:1;pointer-events:all;transform:translateY(0)}
.ndph{padding:14px 16px;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.ndph h3{font-size:13px;font-weight:700}
.ndpa{display:flex;gap:6px}
.ndpl{font-size:10px;color:var(--P);cursor:pointer;background:none;border:none;font-weight:600}
.ndpl:hover{text-decoration:underline}
.ndpl.er{color:var(--ER)}
.ndps{max-height:360px;overflow-y:auto}
.ndpi{display:flex;gap:10px;padding:12px 16px;border-bottom:1px solid var(--bdr);cursor:pointer;transition:background .15s}
.ndpi:last-child{border-bottom:none}
.ndpi:hover{background:var(--bg)}
.ndpi.ur{background:rgba(91,94,244,.04)}
.ndpi.hp{border-left:3px solid var(--ER)}
.ndpi.mp{border-left:3px solid var(--WA)}
.ndi{width:34px;height:34px;border-radius:9px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:13px}
.ndi.overdue,.ndi.upcoming_high{background:rgba(239,68,68,.1);color:var(--ER)}
.ndi.due_today{background:rgba(245,158,11,.1);color:var(--WA)}
.ndi.reminder{background:rgba(91,94,244,.1);color:var(--P)}
.ndi.created{background:rgba(16,185,129,.1);color:var(--OK)}
.ndt{flex:1;min-width:0}
.ndm{font-size:12px;margin-bottom:2px;line-height:1.4}
.ndd{font-size:9px;color:var(--txm)}
.ndpe{padding:30px;text-align:center;color:var(--txm);font-size:12px}
.ndpe i{font-size:28px;margin-bottom:8px;display:block;opacity:.35}

/* MODALS */
.mov{position:fixed;inset:0;background:rgba(0,0,0,.48);display:flex;align-items:center;justify-content:center;z-index:600;opacity:0;pointer-events:none;transition:all .25s;backdrop-filter:blur(3px)}
.mov.on{opacity:1;pointer-events:all}
.mdl{background:var(--card);border-radius:18px;width:92%;max-width:520px;max-height:90vh;display:flex;flex-direction:column;transform:scale(.92) translateY(20px);transition:all .28s cubic-bezier(.34,1.56,.64,1);box-shadow:0 20px 60px rgba(0,0,0,.22)}
.mov.on .mdl{transform:scale(1) translateY(0)}
.mh{padding:18px 22px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.mh h2{font-size:16px;font-weight:700}
.mc{width:32px;height:32px;border:none;background:var(--bg);border-radius:8px;cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;transition:all .2s;font-size:13px}
.mc:hover{background:var(--ER);color:#fff}
.mb{padding:22px;overflow-y:auto;flex:1}
.mf{padding:14px 22px;border-top:1px solid var(--bdr);display:flex;justify-content:flex-end;gap:8px;flex-shrink:0}
.fg{margin-bottom:14px}
.fl{display:block;font-size:10px;font-weight:700;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;color:var(--txm)}
.fi,.fs,.fta{width:100%;padding:10px 13px;border:1.5px solid var(--bdr);border-radius:9px;background:var(--inp);color:var(--tx);font-size:13px;outline:none;transition:all .2s;font-family:inherit}
.fi:focus,.fs:focus,.fta:focus{border-color:var(--P);box-shadow:0 0 0 3px rgba(91,94,244,.1)}
.fta{min-height:65px;resize:vertical;line-height:1.5}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:480px){.frow{grid-template-columns:1fr}}

/* SETTINGS */
.sets{margin-bottom:22px}
.sets h3{font-size:13px;font-weight:700;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--bdr)}
.setr{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--bdr)}
.setr:last-child{border-bottom:none}
.seti h4{font-size:12.5px;margin-bottom:2px;font-weight:600}
.seti p{font-size:10px;color:var(--txm)}
.tgl{position:relative;width:44px;height:24px;flex-shrink:0}
.tgl input{opacity:0;width:0;height:0}
.tgls{position:absolute;cursor:pointer;inset:0;background:var(--bdr);border-radius:24px;transition:all .25s}
.tgls::before{position:absolute;content:"";width:18px;height:18px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:all .25s;box-shadow:0 1px 4px rgba(0,0,0,.2)}
.tgl input:checked+.tgls{background:var(--P)}
.tgl input:checked+.tgls::before{transform:translateX(20px)}

/* TOAST */
.tw{position:fixed;top:16px;right:16px;display:flex;flex-direction:column;gap:8px;z-index:2000;pointer-events:none}
.tst{display:flex;align-items:center;gap:10px;background:var(--card);border-radius:11px;padding:13px 16px;box-shadow:var(--sh2);min-width:240px;border-left:4px solid var(--P);animation:tsin .3s cubic-bezier(.34,1.56,.64,1);pointer-events:all}
.tst.ok{border-left-color:var(--OK)}.tst.er{border-left-color:var(--ER)}.tst.wa{border-left-color:var(--WA)}
.tsti{font-size:16px}.tst.ok .tsti{color:var(--OK)}.tst.er .tsti{color:var(--ER)}.tst.wa .tsti{color:var(--WA)}
.tstm{flex:1;font-size:13px;font-weight:500}
.tstc{background:none;border:none;cursor:pointer;color:var(--txm);font-size:14px}
@keyframes tsin{from{opacity:0;transform:translateX(60px)}to{opacity:1;transform:translateX(0)}}

/* ALERT POPUP */
.alp{position:fixed;bottom:24px;right:24px;width:340px;background:var(--card);border-radius:16px;box-shadow:0 16px 50px rgba(0,0,0,.18);border:1px solid var(--bdr);z-index:3000;overflow:hidden;transform:translateY(140%);transition:transform .45s cubic-bezier(.34,1.56,.64,1)}
.alp.on{transform:translateY(0)}
.alp-s{height:5px;width:100%}
.alp-s.high{background:linear-gradient(90deg,var(--ER),#fca5a5)}
.alp-s.medium{background:linear-gradient(90deg,var(--WA),#fde68a)}
.alp-s.low{background:linear-gradient(90deg,var(--OK),#6ee7b7)}
.alp-s.created{background:linear-gradient(90deg,var(--P),var(--PL))}
.alp-b{padding:16px 18px;display:flex;gap:13px;align-items:flex-start}
.alp-i{width:44px;height:44px;border-radius:12px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:20px}
.alp-i.high{background:rgba(239,68,68,.12);color:var(--ER)}
.alp-i.medium{background:rgba(245,158,11,.12);color:var(--WA)}
.alp-i.low{background:rgba(16,185,129,.12);color:var(--OK)}
.alp-i.created{background:rgba(91,94,244,.12);color:var(--P)}
.alp-t{flex:1;min-width:0}
.alp-tt{font-size:13px;font-weight:700;margin-bottom:4px}
.alp-mg{font-size:11.5px;color:var(--txm);line-height:1.5}
.alp-pr{display:inline-flex;padding:2px 9px;border-radius:20px;font-size:9px;font-weight:800;text-transform:uppercase;margin-top:6px}
.alp-pr.high{background:rgba(239,68,68,.1);color:var(--ER)}
.alp-pr.medium{background:rgba(245,158,11,.1);color:var(--WA)}
.alp-pr.low{background:rgba(16,185,129,.1);color:var(--OK)}
.alp-cl{width:26px;height:26px;border:none;background:var(--bg);border-radius:7px;cursor:pointer;color:var(--txm);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;transition:all .2s}
.alp-cl:hover{background:var(--ER);color:#fff}
.alp-pg{height:3px;background:var(--bdr);overflow:hidden}
.alp-bar{height:100%;background:linear-gradient(90deg,var(--P),var(--S));width:100%;transform-origin:left;will-change:transform}
.alp-ft{padding:10px 18px;border-top:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.alp-tm{font-size:9px;color:var(--txm)}
.alp-ac{display:flex;gap:6px}
.alp-btn{font-size:10px;cursor:pointer;font-weight:700;background:none;border:none;padding:5px 12px;border-radius:7px;transition:all .2s}
.alp-btn.snz{background:var(--bg);color:var(--tx);border:1px solid var(--bdr)}
.alp-btn.snz:hover{background:var(--bdr)}
.alp-btn.dm{color:var(--P);background:rgba(91,94,244,.08)}
.alp-btn.dm:hover{background:rgba(91,94,244,.15)}

@media(max-width:768px){.sb{position:fixed;left:-100%;z-index:200}.sb.mob{left:0}.ctn{padding:12px}}
</style>
</head>
<body>
<div class="app">

<!-- SIDEBAR -->
<aside class="sb" id="sb">
<div class="sb-br">
  <div class="sb-lo"><i class="fas fa-layer-group"></i></div>
  <span class="sb-nm">TaskPro</span>
</div>
<nav class="sb-nv">
  <div class="nsec">
    <div class="nlbl">Main</div>
    <button class="nbt on" data-p="db" onclick="go('db',this)"><i class="fas fa-th-large"></i><span class="nt">Dashboard</span></button>
    <button class="nbt" data-p="all" onclick="go('all',this)"><i class="fas fa-list-check"></i><span class="nt">All Tasks</span><span class="nc" id="nc-all">0</span></button>
    <button class="nbt" data-p="td" onclick="go('td',this)"><i class="fas fa-calendar-day"></i><span class="nt">Due Today</span><span class="nc" id="nc-td">0</span></button>
    <button class="nbt" data-p="ov" onclick="go('ov',this)"><i class="fas fa-exclamation-circle"></i><span class="nt">Overdue</span><span class="nc" id="nc-ov" style="background:var(--ER);color:#fff">0</span></button>
    <button class="nbt" data-p="cm" onclick="go('cm',this)"><i class="fas fa-check-double"></i><span class="nt">Completed</span></button>
  </div>
  <div class="nsec">
    <div class="nlbl">Categories</div>
    <div id="sbC"></div>
    <button class="nbt" onclick="openCM()"><i class="fas fa-plus"></i><span class="nt">Add Category</span></button>
  </div>
</nav>
</aside>

<!-- RIGHT -->
<div class="rt">
<header class="hd">
  <button class="hbt" onclick="toggleSB()"><i class="fas fa-bars"></i></button>
  <div class="sw"><i class="fas fa-search"></i><input id="si" placeholder="Search tasks... (Ctrl+K)" oninput="onSrch()"></div>
  <div class="hrt">
    <button class="hbt" onclick="toggleThm()"><i class="fas fa-moon" id="thmI"></i></button>
    <button class="hbt" id="bellBtn" onclick="toggleND()"><i class="fas fa-bell"></i><span class="bdg" id="nBdg" style="display:none">0</span></button>
    <button class="hbt" onclick="openSM()"><i class="fas fa-cog"></i></button>
    <button class="hbt" onclick="openEI()"><i class="fas fa-database"></i></button>
    <div class="ava">JD</div>
  </div>
</header>

<!-- NOTIF DROPDOWN -->
<div class="ndp" id="ndp">
  <div class="ndph"><h3><i class="fas fa-bell" style="margin-right:7px;color:var(--WA)"></i>Notifications</h3>
  <div class="ndpa">
    <button class="ndpl" onclick="markAll()">Read all</button>
    <button class="ndpl er" onclick="clearRd()">Clear</button>
  </div></div>
  <div class="ndps" id="ndps"></div>
</div>

<div class="ctn">

<!-- DASHBOARD -->
<div class="pg on" id="pg-db">
  <div class="pgh">
    <div><h1 id="grt">Hello!</h1><p id="tDt">Loading date...</p></div>
    <div class="pghr">
      <button class="btn bg2" onclick="loadAll()"><i class="fas fa-sync-alt"></i> Refresh</button>
      <button class="btn bp" onclick="openTM(null)"><i class="fas fa-plus"></i> New Task</button>
    </div>
  </div>
  <div class="sg">
    <div class="sc c1"><div class="sc-i"><i class="fas fa-tasks"></i></div><div><div class="sc-v" id="s-t">0</div><div class="sc-l">Total Tasks</div></div></div>
    <div class="sc c2"><div class="sc-i"><i class="fas fa-check-circle"></i></div><div><div class="sc-v" id="s-d">0</div><div class="sc-l">Completed</div></div></div>
    <div class="sc c3"><div class="sc-i"><i class="fas fa-spinner"></i></div><div><div class="sc-v" id="s-p">0</div><div class="sc-l">In Progress</div></div></div>
    <div class="sc c4"><div class="sc-i"><i class="fas fa-exclamation-triangle"></i></div><div><div class="sc-v" id="s-o">0</div><div class="sc-l">Overdue</div></div></div>
    <div class="sc c5"><div class="sc-i"><i class="fas fa-calendar-check"></i></div><div><div class="sc-v" id="s-td">0</div><div class="sc-l">Due Today</div></div></div>
  </div>
  <div class="dg" style="flex:1;min-height:0">
    <div class="crd" style="min-height:0">
      <div class="crh"><h2>📋 Recent Tasks</h2>
        <div class="flt">
          <select id="d-st" onchange="rDB()"><option value="">All Status</option><option value="pending">Pending</option><option value="in_progress">In Progress</option><option value="completed">Done</option></select>
          <select id="d-pr" onchange="rDB()"><option value="">All Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
        </div>
      </div>
      <div class="tl" id="dbL"></div>
    </div>
    <div class="dps" style="display:flex;flex-direction:column;gap:14px;overflow-y:auto">
      <div class="crd">
        <div class="crh"><h2>📊 Progress</h2></div>
        <div class="crb">
          <div class="rw">
            <div class="rc">
              <svg width="80" height="80" viewBox="0 0 80 80">
                <circle cx="40" cy="40" r="34" fill="none" stroke="var(--bdr)" stroke-width="8"/>
                <circle id="rngC" cx="40" cy="40" r="34" fill="none" stroke="url(#rg1)" stroke-width="8" stroke-linecap="round" stroke-dasharray="214" stroke-dashoffset="214" style="transition:stroke-dashoffset .7s ease"/>
                <defs><linearGradient id="rg1" x1="0%" y1="0%" x2="100%"><stop offset="0%" stop-color="#5b5ef4"/><stop offset="100%" stop-color="#06b6d4"/></linearGradient></defs>
              </svg>
              <div class="rm"><div class="rp" id="rPct">0%</div><div class="rl">done</div></div>
            </div>
            <div class="rs">
              <div class="ri"><span class="dot" style="background:var(--OK)"></span><span>Done: <b id="rD">0</b></span></div>
              <div class="ri"><span class="dot" style="background:var(--P)"></span><span>Progress: <b id="rI">0</b></span></div>
              <div class="ri"><span class="dot" style="background:var(--WA)"></span><span>Pending: <b id="rPn">0</b></span></div>
              <div class="ri"><span class="dot" style="background:var(--ER)"></span><span>Overdue: <b id="rO">0</b></span></div>
            </div>
          </div>
        </div>
      </div>
      <div class="crd">
        <div class="crh"><h2>📁 Categories</h2><button class="btn bg2 bsm" onclick="openCM()"><i class="fas fa-plus"></i></button></div>
        <div class="crb" style="padding:8px 10px"><div id="cpnl"></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ALL TASKS -->
<div class="pg" id="pg-all">
  <div class="pgh"><div><h1>All Tasks</h1><p>Manage and search all tasks</p></div><div class="pghr"><button class="btn bp" onclick="openTM(null)"><i class="fas fa-plus"></i> New Task</button></div></div>
  <div class="crd" style="flex:1">
    <div class="crh">
      <div class="flt">
        <select id="a-st" onchange="rAll()"><option value="">All Status</option><option value="pending">Pending</option><option value="in_progress">In Progress</option><option value="completed">Done</option></select>
        <select id="a-pr" onchange="rAll()"><option value="">All Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
        <select id="a-ca" onchange="rAll()"><option value="">All Categories</option></select>
      </div>
    </div>
    <div class="tl" id="allL" style="flex:1"></div>
  </div>
</div>

<!-- TODAY -->
<div class="pg" id="pg-td">
  <div class="pgh"><div><h1>Due Today</h1><p>Tasks for today</p></div><div class="pghr"><button class="btn bp" onclick="openTM(null)"><i class="fas fa-plus"></i> New Task</button></div></div>
  <div class="crd" style="flex:1"><div class="tl" id="tdL" style="flex:1"></div></div>
</div>

<!-- OVERDUE -->
<div class="pg" id="pg-ov">
  <div class="pgh"><div><h1>⚠️ Overdue</h1><p>Tasks past due date</p></div></div>
  <div class="crd" style="flex:1"><div class="tl" id="ovL" style="flex:1"></div></div>
</div>

<!-- COMPLETED -->
<div class="pg" id="pg-cm">
  <div class="pgh"><div><h1>✅ Completed</h1><p>All finished tasks</p></div></div>
  <div class="crd" style="flex:1"><div class="tl" id="cmL" style="flex:1"></div></div>
</div>

</div><!-- /ctn -->
</div><!-- /rt -->
</div><!-- /app -->

<!-- ALERT POPUP -->
<div class="alp" id="alp">
  <div class="alp-s" id="alps"></div>
  <div class="alp-b">
    <div class="alp-i" id="alpi"><i class="fas fa-bell" id="alpii"></i></div>
    <div class="alp-t">
      <div class="alp-tt" id="alptt">Notification</div>
      <div class="alp-mg" id="alpmg">Update</div>
      <div class="alp-pr" id="alppr">MEDIUM</div>
    </div>
    <button class="alp-cl" onclick="closeAP()"><i class="fas fa-times"></i></button>
  </div>
  <div class="alp-pg"><div class="alp-bar" id="alpbar"></div></div>
  <div class="alp-ft">
    <span class="alp-tm" id="alptm">Now</span>
    <div class="alp-ac">
      <button class="alp-btn snz" onclick="doSnooze()"><i class="fas fa-clock"></i> Snooze</button>
      <button class="alp-btn dm" onclick="closeAP()">Dismiss</button>
    </div>
  </div>
</div>

<!-- TASK MODAL -->
<div class="mov" id="tMov">
  <div class="mdl">
    <div class="mh"><h2 id="mTi">New Task</h2><button class="mc" onclick="closeTM()"><i class="fas fa-times"></i></button></div>
    <div class="mb">
      <input type="hidden" id="fid">
      <div class="fg"><label class="fl">Title *</label><input class="fi" id="ftit" placeholder="What needs to be done?"></div>
      <div class="fg"><label class="fl">Description</label><textarea class="fta" id="fdsc" placeholder="Add more details..."></textarea></div>
      <div class="frow">
        <div class="fg"><label class="fl">Category</label><select class="fs" id="fcat"></select></div>
        <div class="fg"><label class="fl">Priority</label><select class="fs" id="fpri"><option value="low">🟢 Low</option><option value="medium" selected>🟡 Medium</option><option value="high">🔴 High</option></select></div>
      </div>
      <div class="frow">
        <div class="fg"><label class="fl">Due Date</label><input type="date" class="fi" id="fdt"></div>
        <div class="fg"><label class="fl">Due Time</label><input type="time" class="fi" id="ftm2"></div>
      </div>
      <div class="frow">
        <div class="fg"><label class="fl">Status</label><select class="fs" id="fst"><option value="pending">⏳ Pending</option><option value="in_progress">🔄 In Progress</option><option value="completed">✅ Done</option></select></div>
        <div class="fg"><label class="fl">Remind Before</label><select class="fs" id="frm"><option value="5">5 min</option><option value="10">10 min</option><option value="15">15 min</option><option value="30" selected>30 min</option><option value="60">1 hour</option><option value="1440">1 day</option></select></div>
      </div>
      <div class="fg"><label class="fl">Assigned To</label><input class="fi" id="fasn" placeholder="Name"></div>
      <div class="fg"><label class="fl">Tags (comma separated)</label><input class="fi" id="ftgs" placeholder="e.g. urgent, client"></div>
      <div class="fg"><label class="fl">Notes</label><textarea class="fta" id="fnts" placeholder="Additional notes..."></textarea></div>
    </div>
    <div class="mf"><button class="btn bg2" onclick="closeTM()">Cancel</button><button class="btn bp" onclick="saveT()"><i class="fas fa-save"></i> Save Task</button></div>
  </div>
</div>

<!-- CATEGORY MODAL -->
<div class="mov" id="cMov">
  <div class="mdl" style="max-width:340px">
    <div class="mh"><h2>📁 New Category</h2><button class="mc" onclick="closeCM()"><i class="fas fa-times"></i></button></div>
    <div class="mb">
      <div class="fg"><label class="fl">Name</label><input class="fi" id="cnm" placeholder="Category name"></div>
      <div class="fg"><label class="fl">Color</label><input type="color" class="fi" id="ccl" value="#5b5ef4" style="height:42px;padding:6px;cursor:pointer"></div>
    </div>
    <div class="mf"><button class="btn bg2" onclick="closeCM()">Cancel</button><button class="btn bp" onclick="saveC()">Save</button></div>
  </div>
</div>

<!-- SETTINGS MODAL -->
<div class="mov" id="sMov">
  <div class="mdl" style="max-width:480px">
    <div class="mh"><h2>⚙️ Settings</h2><button class="mc" onclick="closeSM()"><i class="fas fa-times"></i></button></div>
    <div class="mb">
      <div class="sets"><h3>🔔 Notifications</h3>
        <div class="setr"><div class="seti"><h4>Sound Alerts</h4><p>Play beep on notification</p></div><label class="tgl"><input type="checkbox" id="ss" checked onchange="saveSt()"><span class="tgls"></span></label></div>
        <div class="setr"><div class="seti"><h4>Popup Alerts</h4><p>Show popup window</p></div><label class="tgl"><input type="checkbox" id="sp" checked onchange="saveSt()"><span class="tgls"></span></label></div>
        <div class="setr"><div class="seti"><h4>Browser Notifications</h4><p>OS-level alerts</p></div><label class="tgl"><input type="checkbox" id="sb2" checked onchange="saveSt()"><span class="tgls"></span></label></div>
        <div class="setr"><div class="seti"><h4>Poll Interval</h4><p>How often to check</p></div><select class="fs" id="sint" style="width:85px" onchange="saveSt()"><option value="15">15s</option><option value="30" selected>30s</option><option value="60">60s</option></select></div>
      </div>
      <div class="sets"><h3>⏰ Default Reminders by Priority</h3>
        <div class="setr"><div class="seti"><h4>🔴 High</h4></div><select class="fs" id="srh" style="width:110px" onchange="saveSt()"><option value="5">5 min</option><option value="10">10 min</option><option value="15" selected>15 min</option><option value="30">30 min</option></select></div>
        <div class="setr"><div class="seti"><h4>🟡 Medium</h4></div><select class="fs" id="srm" style="width:110px" onchange="saveSt()"><option value="15">15 min</option><option value="30" selected>30 min</option><option value="60">1 hour</option></select></div>
        <div class="setr"><div class="seti"><h4>🟢 Low</h4></div><select class="fs" id="srl" style="width:110px" onchange="saveSt()"><option value="30">30 min</option><option value="60" selected>1 hour</option><option value="120">2 hours</option></select></div>
      </div>
      <div class="sets"><h3>🪟 Popup Duration</h3>
        <div class="setr"><div class="seti"><h4>🔴 High</h4></div><select class="fs" id="sdh" style="width:90px" onchange="saveSt()"><option value="10">10s</option><option value="12" selected>12s</option><option value="15">15s</option></select></div>
        <div class="setr"><div class="seti"><h4>🟡 Medium</h4></div><select class="fs" id="sdm" style="width:90px" onchange="saveSt()"><option value="5">5s</option><option value="8" selected>8s</option><option value="10">10s</option></select></div>
        <div class="setr"><div class="seti"><h4>🟢 Low</h4></div><select class="fs" id="sdl" style="width:90px" onchange="saveSt()"><option value="3">3s</option><option value="5" selected>5s</option><option value="8">8s</option></select></div>
        <div class="setr"><div class="seti"><h4>Snooze Duration</h4></div><select class="fs" id="ssnz" style="width:110px" onchange="saveSt()"><option value="5">5 min</option><option value="10" selected>10 min</option><option value="15">15 min</option><option value="30">30 min</option></select></div>
      </div>
    </div>
    <div class="mf"><button class="btn bp" onclick="closeSM()">Done</button></div>
  </div>
</div>

<!-- EXPORT/IMPORT MODAL -->
<div class="mov" id="eiMov">
  <div class="mdl" style="max-width:380px">
    <div class="mh"><h2>🗄️ Data</h2><button class="mc" onclick="closeEI()"><i class="fas fa-times"></i></button></div>
    <div class="mb" style="display:flex;flex-direction:column;gap:14px">
      <div style="background:var(--bg);border-radius:10px;padding:16px;border:1px solid var(--bdr)">
        <h3 style="font-size:13px;margin-bottom:6px;font-weight:700"><i class="fas fa-download" style="color:var(--OK);margin-right:7px"></i>Export</h3>
        <p style="color:var(--txm);font-size:11px;margin-bottom:12px">Download all tasks as JSON backup</p>
        <button class="btn bok bsm" onclick="doExp()"><i class="fas fa-download"></i> Export Now</button>
      </div>
      <div style="background:var(--bg);border-radius:10px;padding:16px;border:1px solid var(--bdr)">
        <h3 style="font-size:13px;margin-bottom:6px;font-weight:700"><i class="fas fa-upload" style="color:var(--P);margin-right:7px"></i>Import</h3>
        <p style="color:var(--txm);font-size:11px;margin-bottom:12px">Restore from JSON backup file</p>
        <input type="file" id="impF" accept=".json" style="display:none" onchange="doImp(event)">
        <button class="btn bp bsm" onclick="document.getElementById('impF').click()"><i class="fas fa-upload"></i> Choose File</button>
      </div>
    </div>
    <div class="mf"><button class="btn bg2" onclick="closeEI()">Close</button></div>
  </div>
</div>

<div class="tw" id="tw"></div>

<script>
// ═══════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════
var AP = '/api';
var T=[], C=[], ST={}, NF=[], SE={};
var pg = 'db', kN = {}, aQ = [], aSh = false, aTmr = null, pTmr = null, aTid = null;

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function() {
  setGrt();
  loadThm();
  loadAll();
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
  setInterval(clientReminderCheck, 60000);
});

function loadAll() {
  Promise.all([fT(), fC(), fS(), fN(), fSE()]).then(function() {
    render();
    rSB();
  });
}

// ═══════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════
function G(i) { return document.getElementById(i); }
function SV(i, v) { var e = G(i); if (e) e.value = v; }
function TV(i, v) { var e = G(i); if (e) e.textContent = v; }
function todStr() { return new Date().toISOString().split('T')[0]; }
function isOv(t) { return t.due_date && t.due_date < todStr() && t.status !== 'completed'; }
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function tAgo(s) {
  if (!s) return '';
  var d = Math.floor((Date.now() - new Date(s)) / 1000);
  if (d < 60) return 'Just now';
  if (d < 3600) return Math.floor(d/60) + 'm ago';
  if (d < 86400) return Math.floor(d/3600) + 'h ago';
  return Math.floor(d/86400) + 'd ago';
}
function fmtD(s) {
  if (!s) return '';
  return new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
}
function pTg(t) { try { return JSON.parse(t || '[]'); } catch(e) { return []; } }
function fillSl(id, items, ph) {
  var el = G(id); if (!el) return;
  var cv = el.value;
  var h = ph ? '<option value="">' + ph + '</option>' : '';
  for (var i = 0; i < items.length; i++) {
    h += '<option value="' + esc(items[i].v) + '">' + esc(items[i].l) + '</option>';
  }
  el.innerHTML = h;
  if (cv) el.value = cv;
}

// ═══════════════════════════════════════════
// API
// ═══════════════════════════════════════════
function api(p, m, b) {
  m = m || 'GET';
  var o = { method: m, headers: { 'Content-Type': 'application/json' } };
  if (b) o.body = JSON.stringify(b);
  return fetch(AP + p, o)
    .then(function(r) {
      if (!r.ok) {
        return r.text().then(function(txt) {
          console.error('API error ' + r.status + ':', txt);
          return null;
        });
      }
      return r.json();
    })
    .catch(function(e) {
      console.error('Fetch error:', e);
      toast('Connection error', 'er');
      return null;
    });
}

function fT() { return api('/tasks?sort=created_at&order=desc').then(function(r) { T = r || []; }); }
function fC() { return api('/categories').then(function(r) { C = r || []; }); }
function fS() { return api('/statistics').then(function(r) { ST = r || {}; }); }
function fN() {
  return api('/notifications').then(function(r) {
    NF = r || []; updBdg(); rNL();
  });
}
function fSE() {
  return api('/settings').then(function(r) {
    if (!r) return;
    SE = r;
    if (G('ss'))   G('ss').checked   = SE.sound_enabled   !== 0;
    if (G('sp'))   G('sp').checked   = SE.popup_enabled   !== 0;
    if (G('sb2'))  G('sb2').checked  = SE.browser_notif_enabled !== 0;
    SV('sint', SE.check_interval_secs     || 30);
    SV('srh',  SE.default_reminder_high   || 15);
    SV('srm',  SE.default_reminder_medium || 30);
    SV('srl',  SE.default_reminder_low    || 60);
    SV('sdh',  SE.popup_duration_high   || 12);
    SV('sdm',  SE.popup_duration_medium || 8);
    SV('sdl',  SE.popup_duration_low    || 5);
    SV('ssnz', SE.auto_snooze_mins || 10);
    startPoll();
  });
}

function saveSt() {
  var d = {
    sound_enabled:           G('ss').checked  ? 1 : 0,
    popup_enabled:           G('sp').checked  ? 1 : 0,
    browser_notif_enabled:   G('sb2').checked ? 1 : 0,
    check_interval_secs:     parseInt(G('sint').value),
    default_reminder_high:   parseInt(G('srh').value),
    default_reminder_medium: parseInt(G('srm').value),
    default_reminder_low:    parseInt(G('srl').value),
    popup_duration_high:     parseInt(G('sdh').value),
    popup_duration_medium:   parseInt(G('sdm').value),
    popup_duration_low:      parseInt(G('sdl').value),
    auto_snooze_mins:        parseInt(G('ssnz').value)
  };
  api('/settings','PUT',d).then(function(r) {
    if (r) { SE = r; startPoll(); toast('Settings saved ✅','ok'); }
  });
}

// ═══════════════════════════════════════════
// POLLING
// ═══════════════════════════════════════════
function startPoll() {
  if (pTmr) clearInterval(pTmr);
  var iv = (SE.check_interval_secs || 30) * 1000;
  pTmr = setInterval(pollN, iv);
}

function pollN() {
  api('/notifications/new').then(function(nw) {
    if (!nw) return;
    var fr = nw.filter(function(n) { return !kN['srv_' + n.id]; });
    fr.forEach(function(n) { kN['srv_' + n.id] = true; aQ.push(n); });
    if (fr.length > 0) { fN(); processQ(); }
  });
}

// ═══════════════════════════════════════════
// CLIENT REMINDER CHECK (every 60s)
// ═══════════════════════════════════════════
function clientReminderCheck() {
  var now = new Date();
  T.forEach(function(t) {
    if (t.status === 'completed' || !t.due_date || !t.due_time) return;
    var rKey = 'cli_' + t.id;
    if (kN[rKey]) return;
    try {
      var due = new Date(t.due_date + 'T' + t.due_time + ':00');
      var rmins = t.reminder_mins || 30;
      var remAt = new Date(due.getTime() - rmins * 60000);
      if (now >= remAt && now < due) {
        kN[rKey] = true;
        var ml = Math.max(0, Math.round((due - now) / 60000));
        var pri = t.priority || 'medium';
        var u = pri === 'high' ? '🔴' : pri === 'medium' ? '🟡' : '🟢';
        aQ.push({
          task_id: t.id,
          message: u + ' REMINDER: "' + t.title + '" due in ' + ml + ' min!',
          type: 'reminder', priority: pri,
          created_at: now.toISOString(), task_title: t.title
        });
        processQ();
      }
    } catch(e) {}
  });
}

// ═══════════════════════════════════════════
// ALERT POPUP
// ═══════════════════════════════════════════
function processQ() {
  if (aSh || aQ.length === 0) return;
  var n = aQ.shift();
  var pr = n.priority || 'medium';
  if (SE.popup_enabled !== 0) showAP(n, pr);
}

function showAP(n, pr) {
  aSh = true;
  clearTimeout(aTmr);
  aTid = n.task_id || null;

  var cfgMap = {
    overdue:       { t: '⚠️ OVERDUE',     i: 'fa-exclamation-circle' },
    due_today:     { t: '📅 Due Today',    i: 'fa-calendar-check'     },
    reminder:      { t: '⏰ Reminder',     i: 'fa-bell'               },
    upcoming_high: { t: '🔴 Tomorrow!',   i: 'fa-fire'               },
    created:       { t: '✅ Task Saved',   i: 'fa-check-circle'       }
  };
  var cf = cfgMap[n.type] || { t: '🔔 Alert', i: 'fa-bell' };
  var ic = (n.type === 'created') ? 'created' : pr;

  G('alps').className    = 'alp-s ' + ic;
  G('alpi').className    = 'alp-i ' + ic;
  G('alpii').className   = 'fas '   + cf.i;
  G('alptt').textContent = cf.t;
  G('alpmg').textContent = n.message || 'Update';
  G('alppr').className   = 'alp-pr ' + pr;
  G('alppr').textContent = pr.toUpperCase() + ' PRIORITY';
  G('alptm').textContent = tAgo(n.created_at);

  var durs = {
    high:   SE.popup_duration_high   || 12,
    medium: SE.popup_duration_medium || 8,
    low:    SE.popup_duration_low    || 5
  };
  var dur = durs[pr] || 8;

  var bar = G('alpbar');
  bar.style.transition = 'none';
  bar.style.transform  = 'scaleX(1)';
  bar.offsetHeight;
  bar.style.transition = dur > 0 ? 'transform ' + dur + 's linear' : 'none';
  bar.style.transform  = dur > 0 ? 'scaleX(0)' : 'scaleX(1)';

  G('alp').classList.add('on');

  if (SE.sound_enabled !== 0) playBeep(pr);
  if (SE.browser_notif_enabled !== 0 &&
      'Notification' in window &&
      Notification.permission === 'granted') {
    try {
      var bn = new Notification('TaskPro: ' + cf.t, { body: n.message || '' });
      bn.onclick = function() { window.focus(); bn.close(); };
    } catch(e) {}
  }

  if (dur > 0) {
    aTmr = setTimeout(function() { closeAP(); setTimeout(processQ, 400); }, dur * 1000);
  }
}

function closeAP() {
  G('alp').classList.remove('on');
  clearTimeout(aTmr);
  aTid = null;
  setTimeout(function() { aSh = false; processQ(); }, 400);
}

function doSnooze() {
  if (aTid) {
    var mins = SE.auto_snooze_mins || 10;
    api('/tasks/' + aTid + '/snooze', 'PUT', { minutes: mins });
    toast('Snoozed for ' + mins + ' min ⏰', 'wa');
  }
  closeAP();
}

// ═══════════════════════════════════════════
// 2-SECOND ALERT BEEP
// ═══════════════════════════════════════════
var axCtx;
function playBeep(pri) {
  try {
    if (!axCtx) axCtx = new (window.AudioContext || window.webkitAudioContext)();
    var c = axCtx;
    var n = c.currentTime;

    if (pri === 'high') {
      // Urgent: 6 fast beeps over 2s
      [0, 0.3, 0.6, 0.9, 1.2, 1.5].forEach(function(t) {
        var o = c.createOscillator(), g = c.createGain();
        o.connect(g); g.connect(c.destination);
        o.type = 'square'; o.frequency.value = 900;
        g.gain.setValueAtTime(0, n+t);
        g.gain.linearRampToValueAtTime(0.28, n+t+0.02);
        g.gain.setValueAtTime(0.28, n+t+0.15);
        g.gain.linearRampToValueAtTime(0, n+t+0.22);
        o.start(n+t); o.stop(n+t+0.25);
      });
    } else if (pri === 'medium') {
      // Medium: 3 beeps over 2s
      [0, 0.6, 1.2].forEach(function(t) {
        var o = c.createOscillator(), g = c.createGain();
        o.connect(g); g.connect(c.destination);
        o.type = 'sine'; o.frequency.value = 660;
        g.gain.setValueAtTime(0, n+t);
        g.gain.linearRampToValueAtTime(0.22, n+t+0.04);
        g.gain.setValueAtTime(0.22, n+t+0.28);
        g.gain.linearRampToValueAtTime(0, n+t+0.45);
        o.start(n+t); o.stop(n+t+0.5);
      });
    } else {
      // Low: 2 gentle beeps over 2s
      [0.1, 1.0].forEach(function(t) {
        var o = c.createOscillator(), g = c.createGain();
        o.connect(g); g.connect(c.destination);
        o.type = 'sine'; o.frequency.value = 440;
        g.gain.setValueAtTime(0, n+t);
        g.gain.linearRampToValueAtTime(0.15, n+t+0.06);
        g.gain.setValueAtTime(0.15, n+t+0.38);
        g.gain.linearRampToValueAtTime(0, n+t+0.58);
        o.start(n+t); o.stop(n+t+0.65);
      });
    }
  } catch(e) { console.warn('Audio error:', e); }
}

// ═══════════════════════════════════════════
// TASK ROW
// ═══════════════════════════════════════════
function tRow(t) {
  var ov  = isOv(t);
  var tgs = pTg(t.tags).map(function(g) { return '<span class="tg">#' + esc(g) + '</span>'; }).join('');
  var pc  = {high:'prh', medium:'prm', low:'prl'}[t.priority] || 'prm';
  var sc  = {pending:'stp2', in_progress:'sti2', completed:'stc2'}[t.status] || 'stp2';
  var rc  = (t.status === 'completed' ? ' dn' : '') + (ov ? ' ovr' : '') + (t.is_pinned ? ' pnd' : '');

  var h = '<div class="tr' + rc + '">';
  h += '<div class="ck ' + (t.status === 'completed' ? 'dn' : '') + '" onclick="togSt(' + t.id + ',event)">';
  if (t.status === 'completed') h += '<i class="fas fa-check" style="font-size:9px"></i>';
  h += '</div>';
  h += '<div class="tif" onclick="edT(' + t.id + ')">';
  h += '<div class="tnm">';
  if (t.is_pinned) h += '<i class="fas fa-thumbtack" style="color:var(--WA);font-size:10px"></i> ';
  h += esc(t.title);
  h += ' <span class="prb ' + pc + '">' + esc(t.priority) + '</span>';
  h += ' <span class="stb2 ' + sc + '">' + esc(t.status.replace(/_/g,' ')) + '</span>';
  h += '</div>';
  if (t.description) h += '<div class="tds">' + esc(t.description) + '</div>';
  h += '<div class="tmt">';
  if (t.due_date) {
    h += '<span class="' + (ov ? 'ovtx' : '') + '"><i class="fas fa-calendar-alt"></i>' + fmtD(t.due_date);
    if (t.due_time) h += ' ' + t.due_time;
    if (ov) h += ' ⚠️';
    h += '</span>';
  }
  h += '<span><i class="fas fa-folder"></i>' + esc(t.category) + '</span>';
  if (t.assigned_to) h += '<span><i class="fas fa-user"></i>' + esc(t.assigned_to) + '</span>';
  h += '<span><i class="fas fa-bell"></i>' + (t.reminder_mins || 30) + 'm</span>';
  h += '</div>';
  if (tgs) h += '<div style="margin-top:5px">' + tgs + '</div>';
  h += '</div>';
  h += '<div class="tac">';
  h += '<button class="abt" onclick="pinT(' + t.id + ',event)" title="' + (t.is_pinned ? 'Unpin' : 'Pin') + '"><i class="fas fa-thumbtack"></i></button>';
  h += '<button class="abt" onclick="edT(' + t.id + ')" title="Edit"><i class="fas fa-pen"></i></button>';
  h += '<button class="abt dl" onclick="dlT(' + t.id + ',event)" title="Delete"><i class="fas fa-trash"></i></button>';
  h += '</div></div>';
  return h;
}

function empSt(msg) {
  return '<div class="emp">' +
    '<div class="emp-ic"><i class="fas fa-clipboard-list"></i></div>' +
    '<h3>' + (msg || 'No tasks found') + '</h3>' +
    '<p>Click "New Task" to get started</p>' +
    '<button class="btn bp" onclick="openTM(null)"><i class="fas fa-plus"></i> New Task</button>' +
    '</div>';
}

function setL(id, l) {
  var e = G(id); if (!e) return;
  e.innerHTML = l && l.length ? l.map(tRow).join('') : empSt();
}

// ═══════════════════════════════════════════
// PAGE RENDERS
// ═══════════════════════════════════════════
function render() {
  updSt(); updRng(); updBdg(); updCnts();
  switch(pg) {
    case 'db':  rDB();  break;
    case 'all': rAll(); break;
    case 'td':  rTd();  break;
    case 'ov':  rOv();  break;
    case 'cm':  rCm();  break;
  }
}

function rDB() {
  var s = G('d-st') ? G('d-st').value : '';
  var p = G('d-pr') ? G('d-pr').value : '';
  var l = T.slice();
  if (s) l = l.filter(function(t) { return t.status === s; });
  if (p) l = l.filter(function(t) { return t.priority === p; });
  setL('dbL', l.slice(0, 25));
}

function rAll() {
  var s = G('a-st') ? G('a-st').value : '';
  var p = G('a-pr') ? G('a-pr').value : '';
  var c = G('a-ca') ? G('a-ca').value : '';
  var q = G('si')   ? G('si').value.toLowerCase() : '';
  var l = T.slice();
  if (s) l = l.filter(function(t) { return t.status === s; });
  if (p) l = l.filter(function(t) { return t.priority === p; });
  if (c) l = l.filter(function(t) { return t.category === c; });
  if (q) l = l.filter(function(t) {
    return (t.title + ' ' + (t.description || '')).toLowerCase().indexOf(q) !== -1;
  });
  setL('allL', l);
}

function rTd() {
  var d = todStr();
  var l = T.filter(function(t) { return t.due_date === d && t.status !== 'completed'; });
  var e = G('tdL'); if (!e) return;
  e.innerHTML = l.length ? l.map(tRow).join('') :
    '<div class="emp"><div class="emp-ic"><i class="fas fa-sun"></i></div><h3>Nothing due today!</h3><p>Enjoy your day 🎉</p></div>';
}

function rOv() {
  var l = T.filter(function(t) { return isOv(t); });
  var e = G('ovL'); if (!e) return;
  e.innerHTML = l.length ? l.map(tRow).join('') :
    '<div class="emp"><div class="emp-ic"><i class="fas fa-trophy"></i></div><h3>All caught up!</h3><p>No overdue tasks 🎉</p></div>';
}

function rCm() {
  var l = T.filter(function(t) { return t.status === 'completed'; });
  l.sort(function(a, b) { return (b.completed_at || '').localeCompare(a.completed_at || ''); });
  setL('cmL', l);
}

// ═══════════════════════════════════════════
// STATS
// ═══════════════════════════════════════════
function updSt() {
  TV('s-t',  ST.total        || 0);
  TV('s-d',  ST.completed    || 0);
  TV('s-p',  ST.in_progress  || 0);
  TV('s-o',  ST.overdue      || 0);
  TV('s-td', ST.due_today    || 0);
}

function updRng() {
  var t = ST.total || 0, c = ST.completed || 0;
  var pct = t > 0 ? Math.round(c / t * 100) : 0;
  TV('rPct', pct + '%');
  TV('rD',   ST.completed   || 0);
  TV('rI',   ST.in_progress || 0);
  TV('rPn',  ST.pending     || 0);
  TV('rO',   ST.overdue     || 0);
  var r = G('rngC');
  if (r) r.style.strokeDashoffset = 214 - (pct / 100) * 214;
}

function updCnts() {
  var d = todStr();
  TV('nc-all', T.filter(function(t) { return t.status !== 'completed'; }).length);
  TV('nc-td',  T.filter(function(t) { return t.due_date === d && t.status !== 'completed'; }).length);
  TV('nc-ov',  T.filter(function(t) { return isOv(t); }).length);
}

function updBdg() {
  var u = NF.filter(function(n) { return !n.is_read; }).length;
  var b = G('nBdg'); if (!b) return;
  b.textContent = u;
  b.style.display = u > 0 ? 'flex' : 'none';
}

// ═══════════════════════════════════════════
// NOTIFICATION LIST
// ═══════════════════════════════════════════
function rNL() {
  var e = G('ndps'); if (!e) return;
  if (!NF || NF.length === 0) {
    e.innerHTML = '<div class="ndpe"><i class="fas fa-bell-slash"></i><br>No notifications</div>';
    return;
  }
  var h = '';
  NF.slice(0, 40).forEach(function(n) {
    var pc = n.priority === 'high' ? 'hp' : n.priority === 'medium' ? 'mp' : '';
    var ic = (n.type === 'overdue' || n.type === 'upcoming_high')
      ? 'fa-exclamation-circle'
      : n.type === 'due_today' ? 'fa-calendar-check'
      : n.type === 'created'   ? 'fa-check-circle' : 'fa-bell';
    h += '<div class="ndpi ' + (n.is_read ? '' : 'ur') + ' ' + pc + '" onclick="rdN(' + n.id + ')">';
    h += '<div class="ndi ' + esc(n.type || 'reminder') + '"><i class="fas ' + ic + '"></i></div>';
    h += '<div class="ndt"><div class="ndm">' + esc(n.message || '') + '</div>';
    h += '<div class="ndd">' + tAgo(n.created_at) + '</div></div></div>';
  });
  e.innerHTML = h;
}

// ═══════════════════════════════════════════
// SIDEBAR RENDER
// ═══════════════════════════════════════════
function rSB() {
  var ce = G('sbC');
  if (ce) {
    var h = '';
    C.forEach(function(c) {
      var cnt = T.filter(function(t) { return t.category === c.name && t.status !== 'completed'; }).length;
      h += '<button class="nbt" onclick="fCat(\'' + esc(c.name) + '\')">';
      h += '<span style="width:9px;height:9px;border-radius:50%;background:' + c.color + ';display:inline-block;flex-shrink:0"></span>';
      h += '<span class="nt">' + esc(c.name) + '</span>';
      h += '<span class="nc">' + cnt + '</span></button>';
    });
    ce.innerHTML = h;
  }

  var cp = G('cpnl');
  if (cp) {
    var h2 = '';
    C.forEach(function(c) {
      var cnt = T.filter(function(t) { return t.category === c.name && t.status !== 'completed'; }).length;
      h2 += '<div class="cpit" onclick="fCat(\'' + esc(c.name) + '\')">';
      h2 += '<span class="cpd" style="background:' + c.color + '"></span>';
      h2 += '<span class="cpn">' + esc(c.name) + '</span>';
      h2 += '<span class="cpc">' + cnt + '</span></div>';
    });
    cp.innerHTML = h2;
  }

  fillSl('a-ca', C.map(function(c) { return { v: c.name, l: c.name }; }), 'All Categories');
  fillSl('fcat', C.map(function(c) { return { v: c.name, l: c.name }; }));
}

// ═══════════════════════════════════════════
// NOTIFICATION ACTIONS
// ═══════════════════════════════════════════
function toggleND() { G('ndp').classList.toggle('on'); }
function rdN(id) { api('/notifications/' + id + '/read','PUT').then(fN); }
function markAll() { api('/notifications/read-all','PUT').then(function() { fN(); toast('All read','ok'); }); }
function clearRd() { api('/notifications/clear-read','DELETE').then(function() { fN(); toast('Cleared','ok'); }); }

// ═══════════════════════════════════════════
// TASK MODAL
// ═══════════════════════════════════════════
function openTM(t) {
  var fields = ['fid','ftit','fdsc','fdt','ftm2','fasn','ftgs','fnts'];
  fields.forEach(function(id) { var e = G(id); if (e) e.value = ''; });
  G('fpri').value = 'medium';
  G('fst').value  = 'pending';
  G('frm').value  = SE.default_reminder_medium || 30;
  G('mTi').textContent = '✨ New Task';
  fillSl('fcat', C.map(function(c) { return { v: c.name, l: c.name }; }));
  if (t) {
    G('mTi').textContent = '✏️ Edit Task';
    G('fid').value  = t.id;
    G('ftit').value = t.title        || '';
    G('fdsc').value = t.description  || '';
    G('fcat').value = t.category     || 'General';
    G('fpri').value = t.priority     || 'medium';
    G('fdt').value  = t.due_date     || '';
    G('ftm2').value = t.due_time     || '';
    G('fst').value  = t.status       || 'pending';
    G('frm').value  = t.reminder_mins || 30;
    G('fasn').value = t.assigned_to  || '';
    G('ftgs').value = pTg(t.tags).join(', ');
    G('fnts').value = t.notes        || '';
  }
  G('tMov').classList.add('on');
  setTimeout(function() { var f = G('ftit'); if (f) f.focus(); }, 150);
}

function closeTM() { G('tMov').classList.remove('on'); }
function edT(id) {
  var t = T.filter(function(x) { return x.id === id; })[0];
  if (t) openTM(t);
}

G('fpri').addEventListener('change', function() {
  var rm = {
    high:   SE.default_reminder_high   || 15,
    medium: SE.default_reminder_medium || 30,
    low:    SE.default_reminder_low    || 60
  };
  G('frm').value = rm[this.value] || 30;
});

function saveT() {
  var id  = G('fid').value;
  var tt  = G('ftit').value.trim();
  if (!tt) { toast('Title is required!','er'); return; }
  var tgsRaw = G('ftgs').value;
  var tgs = tgsRaw ? tgsRaw.split(',').map(function(s) { return s.trim(); }).filter(Boolean) : [];
  var pl = {
    title:         tt,
    description:   G('fdsc').value,
    category:      G('fcat').value,
    priority:      G('fpri').value,
    status:        G('fst').value,
    due_date:      G('fdt').value  || null,
    due_time:      G('ftm2').value || null,
    reminder_mins: parseInt(G('frm').value),
    assigned_to:   G('fasn').value,
    tags:          tgs,
    notes:         G('fnts').value
  };
  var url = id ? '/tasks/' + id : '/tasks';
  var mth = id ? 'PUT' : 'POST';
  api(url, mth, pl).then(function(r) {
    if (r && !r.error) {
      toast(id ? 'Task updated ✅' : 'Task created 🎉', 'ok');
      showAP({
        type: 'created', priority: pl.priority,
        message: '"' + tt + '" ' + (id ? 'updated' : 'created'),
        created_at: new Date().toISOString()
      }, pl.priority);
      closeTM();
      loadAll();
    } else {
      toast('Failed to save task', 'er');
    }
  });
}

function togSt(id, e) {
  e.stopPropagation();
  var t = T.filter(function(x) { return x.id === id; })[0];
  if (!t) return;
  var ns = t.status === 'completed' ? 'pending' : 'completed';
  api('/tasks/' + id, 'PUT', { status: ns }).then(function(r) {
    if (r) {
      toast(ns === 'completed' ? 'Task completed! 🎉' : 'Task reopened', 'ok');
      if (ns === 'completed') playBeep('low');
      loadAll();
    }
  });
}

function dlT(id, e) {
  e.stopPropagation();
  var t = T.filter(function(x) { return x.id === id; })[0];
  if (!t) return;
  if (!confirm('Delete "' + t.title + '"?\nThis cannot be undone.')) return;
  api('/tasks/' + id, 'DELETE').then(function(r) {
    if (r) { toast('Task deleted','ok'); loadAll(); }
  });
}

function pinT(id, e) {
  e.stopPropagation();
  api('/tasks/' + id + '/pin', 'PUT').then(function(r) {
    if (r) loadAll();
  });
}

// ═══════════════════════════════════════════
// CATEGORIES
// ═══════════════════════════════════════════
function openCM() { G('cMov').classList.add('on'); }
function closeCM() { G('cMov').classList.remove('on'); }
function saveC() {
  var n = G('cnm').value.trim();
  if (!n) { toast('Name required','er'); return; }
  api('/categories','POST',{ name: n, color: G('ccl').value }).then(function(r) {
    if (r && !r.error) {
      toast('"' + n + '" created','ok');
      closeCM(); G('cnm').value = '';
      loadAll();
    } else { toast('Error creating category','er'); }
  });
}

// ═══════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════
function openSM() { G('sMov').classList.add('on'); }
function closeSM() { G('sMov').classList.remove('on'); }

// ═══════════════════════════════════════════
// EXPORT / IMPORT
// ═══════════════════════════════════════════
function openEI() { G('eiMov').classList.add('on'); }
function closeEI() { G('eiMov').classList.remove('on'); }
function doExp() {
  api('/export').then(function(data) {
    if (!data) return;
    var b = new Blob([JSON.stringify(data,null,2)], { type:'application/json' });
    var u = URL.createObjectURL(b);
    var a = document.createElement('a');
    a.href = u; a.download = 'taskpro_' + todStr() + '.json'; a.click();
    URL.revokeObjectURL(u);
    toast('Exported!','ok');
  });
}
function doImp(ev) {
  var f = ev.target.files[0]; if (!f) return;
  var rd = new FileReader();
  rd.onload = function(e) {
    try {
      var data = JSON.parse(e.target.result);
      api('/import','POST',data).then(function(r) {
        if (r) { toast('Imported ' + r.imported + ' tasks!','ok'); closeEI(); loadAll(); }
      });
    } catch(err) { toast('Invalid file','er'); }
  };
  rd.readAsText(f);
  ev.target.value = '';
}

// ═══════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════
function go(p, btn) {
  pg = p;
  document.querySelectorAll('.pg').forEach(function(x) { x.classList.remove('on'); });
  document.querySelectorAll('.nbt').forEach(function(x) { x.classList.remove('on'); });
  var el = G('pg-' + p); if (el) el.classList.add('on');
  if (btn) btn.classList.add('on');
  render();
  if (window.innerWidth <= 768) G('sb').classList.remove('mob');
}

function fCat(n) {
  go('all', document.querySelector('[data-p="all"]'));
  setTimeout(function() {
    var s = G('a-ca');
    if (s) { s.value = n; rAll(); }
  }, 50);
}

var srT;
function onSrch() {
  clearTimeout(srT);
  srT = setTimeout(function() {
    if (pg !== 'all') go('all', document.querySelector('[data-p="all"]'));
    else rAll();
  }, 300);
}

// ═══════════════════════════════════════════
// SIDEBAR & THEME
// ═══════════════════════════════════════════
function toggleSB() {
  var s = G('sb');
  if (window.innerWidth <= 768) s.classList.toggle('mob');
  else s.classList.toggle('slim');
}

function toggleThm() {
  document.body.classList.toggle('dark');
  G('thmI').className = document.body.classList.contains('dark') ? 'fas fa-sun' : 'fas fa-moon';
  localStorage.setItem('tpt', document.body.classList.contains('dark') ? 'dark' : 'light');
}

function loadThm() {
  if (localStorage.getItem('tpt') === 'dark') {
    document.body.classList.add('dark');
    G('thmI').className = 'fas fa-sun';
  }
}

// ═══════════════════════════════════════════
// GREETING
// ═══════════════════════════════════════════
function setGrt() {
  var h = new Date().getHours();
  TV('grt', h<12 ? 'Good Morning! ☀️' : h<17 ? 'Good Afternoon! 🌤️' : 'Good Evening! 🌙');
  TV('tDt', new Date().toLocaleDateString('en-US', {
    weekday:'long', year:'numeric', month:'long', day:'numeric'
  }));
}

// ═══════════════════════════════════════════
// TOAST
// ═══════════════════════════════════════════
function toast(m, tp) {
  tp = tp || 'ok';
  var w = G('tw');
  var e = document.createElement('div');
  e.className = 'tst ' + tp;
  var ic = { ok:'fa-check-circle', er:'fa-times-circle', wa:'fa-exclamation-triangle' }[tp] || 'fa-info-circle';
  e.innerHTML = '<i class="fas ' + ic + ' tsti"></i><span class="tstm">' + m + '</span>' +
    '<button class="tstc" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>';
  w.appendChild(e);
  setTimeout(function() {
    e.style.opacity = '0';
    e.style.transform = 'translateX(60px)';
    e.style.transition = 'all .3s';
    setTimeout(function() { if (e.parentNode) e.remove(); }, 300);
  }, 4500);
}

// ═══════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey||e.metaKey) && e.key === 'k') { e.preventDefault(); var s=G('si'); if(s) s.focus(); }
  if ((e.ctrlKey||e.metaKey) && e.key === 'n') { e.preventDefault(); openTM(null); }
  if (e.key === 'Escape') {
    document.querySelectorAll('.mov.on, .ndp.on').forEach(function(el) { el.classList.remove('on'); });
  }
});

document.addEventListener('click', function(e) {
  if (!e.target.closest('#bellBtn') && !e.target.closest('#ndp')) {
    var nd = G('ndp'); if (nd) nd.classList.remove('on');
  }
});
</script>
</body>
</html>'''