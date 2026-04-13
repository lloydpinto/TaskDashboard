from flask import Flask, request, jsonify, Response
import json, os
from datetime import datetime, timedelta

try:
    import requests as req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

app = Flask(__name__)

SB_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SB_KEY = os.environ.get('SUPABASE_KEY', '')
DATA_FILE = '/tmp/taskpro.json'
USE_SUPABASE = bool(SB_URL and SB_KEY and HAS_REQUESTS)

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
        "default_reminder_low":60,"default_reminder_medium":30,
        "default_reminder_high":15,"sound_enabled":1,"popup_enabled":1,
        "browser_notif_enabled":1,"popup_duration_low":5,
        "popup_duration_medium":8,"popup_duration_high":12,
        "auto_snooze_mins":10,"check_interval_secs":30
    },
    "ids":{"tasks":1,"categories":11,"notifications":1}
}

def ld():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,'r') as f:
                data = json.load(f)
                for k in DEFAULT_DATA:
                    if k not in data:
                        data[k] = DEFAULT_DATA[k]
                return data
    except Exception as e:
        print("Load error:", e)
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

def sb_headers():
    return {
        'apikey': SB_KEY,
        'Authorization': 'Bearer ' + SB_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def sb_get(table, params=None):
    try:
        r = req.get(f'{SB_URL}/rest/v1/{table}',
                    headers=sb_headers(), params=params or {}, timeout=8)
        if r.status_code in (200, 206):
            return r.json()
        print(f"SB GET {table} {r.status_code}: {r.text[:150]}")
        return []
    except Exception as e:
        print(f"SB GET error: {e}")
        return []

def sb_post(table, data):
    try:
        r = req.post(f'{SB_URL}/rest/v1/{table}',
                     headers=sb_headers(), json=data, timeout=8)
        if r.status_code in (200, 201):
            res = r.json()
            return res[0] if isinstance(res, list) and res else res
        print(f"SB POST {table} {r.status_code}: {r.text[:150]}")
        return None
    except Exception as e:
        print(f"SB POST error: {e}")
        return None

def sb_patch(table, match, data):
    try:
        params = {k: f'eq.{v}' for k, v in match.items()}
        r = req.patch(f'{SB_URL}/rest/v1/{table}',
                      headers=sb_headers(), params=params, json=data, timeout=8)
        if r.status_code in (200, 204):
            try:
                res = r.json()
                return res[0] if isinstance(res, list) and res else (res or data)
            except:
                return data
        print(f"SB PATCH {table} {r.status_code}: {r.text[:150]}")
        return None
    except Exception as e:
        print(f"SB PATCH error: {e}")
        return None

def sb_delete(table, match):
    try:
        params = {k: f'eq.{v}' for k, v in match.items()}
        r = req.delete(f'{SB_URL}/rest/v1/{table}',
                       headers=sb_headers(), params=params, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"SB DELETE error: {e}")
        return False

def now():
    return datetime.now().isoformat()

def gen_notifs_local(data):
    """
    Generate overdue / due_today / reminder notifications.
    Does NOT generate 'created' type — that is handled client-side.
    """
    n = datetime.now()
    td = n.strftime('%Y-%m-%d')
    tm = (n + timedelta(days=1)).strftime('%Y-%m-%d')

    existing = [x for x in data.get('notifications', []) if not x.get('is_dismissed')]
    ex = set(f"{x.get('task_id')}_{x.get('type')}" for x in existing)

    tasks = [t for t in data.get('tasks', [])
             if t.get('status') != 'completed' and t.get('due_date')]

    for t in tasks:
        tid = t['id']
        pri = t.get('priority', 'medium')
        u   = '🔴' if pri == 'high' else '🟡' if pri == 'medium' else '🟢'
        dd  = t.get('due_date', '')

        # Overdue
        if dd < td:
            k = f"{tid}_overdue"
            if k not in ex:
                days = (n - datetime.strptime(dd, '%Y-%m-%d')).days
                notif = {
                    'id': nid(data, 'notifications'), 'task_id': tid,
                    'message': f"{u} OVERDUE ({days}d): '{t['title']}'",
                    'type': 'overdue', 'priority': pri,
                    'is_read': 0, 'is_dismissed': 0,
                    'created_at': now(),
                    'task_title': t['title'], 'task_priority': pri
                }
                data['notifications'].insert(0, notif)

        # Due today
        elif dd == td:
            k = f"{tid}_due_today"
            if k not in ex:
                ti = f" at {t['due_time']}" if t.get('due_time') else ''
                notif = {
                    'id': nid(data, 'notifications'), 'task_id': tid,
                    'message': f"{u} Due Today{ti}: '{t['title']}'",
                    'type': 'due_today', 'priority': pri,
                    'is_read': 0, 'is_dismissed': 0,
                    'created_at': now(),
                    'task_title': t['title'], 'task_priority': pri
                }
                data['notifications'].insert(0, notif)

        # Time-based reminder
        if t.get('due_time') and not t.get('reminder_sent'):
            try:
                due = datetime.strptime(f"{dd} {t['due_time']}", '%Y-%m-%d %H:%M')
                rm  = t.get('reminder_mins', 30) or 30
                ra  = due - timedelta(minutes=rm)
                if n >= ra and n < due:
                    k = f"{tid}_reminder"
                    if k not in ex:
                        ml = max(0, int((due - n).total_seconds() / 60))
                        notif = {
                            'id': nid(data, 'notifications'), 'task_id': tid,
                            'message': f"{u} REMINDER: '{t['title']}' in {ml} min!",
                            'type': 'reminder', 'priority': pri,
                            'is_read': 0, 'is_dismissed': 0,
                            'created_at': now(),
                            'task_title': t['title'], 'task_priority': pri
                        }
                        data['notifications'].insert(0, notif)
                        t['reminder_sent'] = 1
            except:
                pass

        # High priority tomorrow
        if pri == 'high' and dd == tm:
            k = f"{tid}_upcoming_high"
            if k not in ex:
                notif = {
                    'id': nid(data, 'notifications'), 'task_id': tid,
                    'message': f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'",
                    'type': 'upcoming_high', 'priority': 'high',
                    'is_read': 0, 'is_dismissed': 0,
                    'created_at': now(),
                    'task_title': t['title'], 'task_priority': 'high'
                }
                data['notifications'].insert(0, notif)

    data['notifications'] = data['notifications'][:80]


def gen_notifs_supabase():
    """Supabase version — same logic, no 'created' type"""
    try:
        n  = datetime.now()
        td = n.strftime('%Y-%m-%d')
        tm = (n + timedelta(days=1)).strftime('%Y-%m-%d')

        existing = sb_get('notifications', {
            'is_dismissed': 'eq.0', 'select': 'task_id,type'
        }) or []
        ex = set(f"{x.get('task_id')}_{x.get('type')}" for x in existing)

        tasks = sb_get('tasks', {'status': 'neq.completed', 'select': '*'}) or []

        for t in tasks:
            if not t.get('due_date'):
                continue
            tid = t['id']
            pri = t.get('priority', 'medium')
            u   = '🔴' if pri == 'high' else '🟡' if pri == 'medium' else '🟢'
            dd  = t.get('due_date', '')

            if dd < td:
                k = f"{tid}_overdue"
                if k not in ex:
                    days = (n - datetime.strptime(dd, '%Y-%m-%d')).days
                    sb_post('notifications', {
                        'task_id': tid,
                        'message': f"{u} OVERDUE ({days}d): '{t['title']}'",
                        'type': 'overdue', 'priority': pri,
                        'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                        'task_title': t['title'], 'task_priority': pri
                    })

            elif dd == td:
                k = f"{tid}_due_today"
                if k not in ex:
                    ti = f" at {t['due_time']}" if t.get('due_time') else ''
                    sb_post('notifications', {
                        'task_id': tid,
                        'message': f"{u} Due Today{ti}: '{t['title']}'",
                        'type': 'due_today', 'priority': pri,
                        'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                        'task_title': t['title'], 'task_priority': pri
                    })

            if t.get('due_time') and not t.get('reminder_sent'):
                try:
                    due = datetime.strptime(f"{dd} {t['due_time']}", '%Y-%m-%d %H:%M')
                    rm  = t.get('reminder_mins', 30) or 30
                    ra  = due - timedelta(minutes=rm)
                    if n >= ra and n < due:
                        k = f"{tid}_reminder"
                        if k not in ex:
                            ml = max(0, int((due - n).total_seconds() / 60))
                            sb_post('notifications', {
                                'task_id': tid,
                                'message': f"{u} REMINDER: '{t['title']}' in {ml} min!",
                                'type': 'reminder', 'priority': pri,
                                'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                                'task_title': t['title'], 'task_priority': pri
                            })
                            sb_patch('tasks', {'id': tid}, {'reminder_sent': 1})
                except:
                    pass

            if pri == 'high' and dd == tm:
                k = f"{tid}_upcoming_high"
                if k not in ex:
                    sb_post('notifications', {
                        'task_id': tid,
                        'message': f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'",
                        'type': 'upcoming_high', 'priority': 'high',
                        'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                        'task_title': t['title'], 'task_priority': 'high'
                    })
    except Exception as e:
        print(f"gen_notifs_supabase error: {e}")


# ── CORS ──────────────────────────────────────────────────────
@app.after_request
def add_cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return r

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        r = jsonify({})
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return r, 200


# ── ROOT ──────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def root():
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'static', 'app.html'
    )
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return Response(f.read(), content_type='text/html; charset=utf-8')
    except Exception as e:
        return Response(f'<h1>Error: {e}</h1>', content_type='text/html')


# ── SETTINGS ──────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET', 'PUT'])
def api_settings():
    if USE_SUPABASE:
        if request.method == 'PUT':
            sb_patch('settings', {'id': 1}, request.json or {})
        rows = sb_get('settings', {'id': 'eq.1'})
        return jsonify(rows[0] if rows else DEFAULT_DATA['settings'])
    data = ld()
    if request.method == 'PUT':
        b = request.json or {}
        for k, v in b.items():
            if k in data['settings']:
                data['settings'][k] = v
        sv(data)
    return jsonify(data['settings'])


# ── TASKS ─────────────────────────────────────────────────────
@app.route('/api/tasks', methods=['GET', 'POST'])
def api_tasks():
    if USE_SUPABASE:
        return _tasks_sb()
    return _tasks_local()


def _tasks_sb():
    if request.method == 'POST':
        b   = request.json or {}
        pri = b.get('priority', 'medium')
        se  = (sb_get('settings', {'id': 'eq.1'}) or [{}])[0]
        dr  = {
            'low':    se.get('default_reminder_low',    60),
            'medium': se.get('default_reminder_medium', 30),
            'high':   se.get('default_reminder_high',   15)
        }
        ts = now()
        td = {
            'title':           b.get('title', 'Untitled'),
            'description':     b.get('description', ''),
            'category':        b.get('category', 'General'),
            'priority':        pri,
            'status':          b.get('status', 'pending'),
            'due_date':        b.get('due_date') or None,
            'due_time':        b.get('due_time') or None,
            'reminder_mins':   b.get('reminder_mins', dr.get(pri, 30)),
            'assigned_to':     b.get('assigned_to', ''),
            'project':         b.get('project', ''),
            'tags':            json.dumps(b.get('tags', [])),
            'notes':           b.get('notes', ''),
            'estimated_hours': b.get('estimated_hours', 0),
            'progress':        b.get('progress', 0),
            'is_pinned':       1 if b.get('is_pinned') else 0,
            'created_at':      ts, 'updated_at': ts,
            'completed_at':    None, 'reminder_sent': 0, 'snooze_until': None
        }
        task = sb_post('tasks', td)
        # NOTE: no 'created' notification pushed — client handles it once
        gen_notifs_supabase()
        return jsonify(task or td), 201

    params = {'select': '*', 'order': 'is_pinned.desc,created_at.desc'}
    for arg, col in [('status','status'),('priority','priority'),('category','category')]:
        v = request.args.get(arg, '')
        if v: params[col] = f'eq.{v}'
    tasks = sb_get('tasks', params) or []
    se = request.args.get('search', '')
    if se:
        sq = se.lower()
        tasks = [t for t in tasks
                 if sq in (t.get('title','') or '').lower()
                 or sq in (t.get('description','') or '').lower()]
    return jsonify(tasks)


def _tasks_local():
    data = ld()
    if request.method == 'POST':
        b   = request.json or {}
        pri = b.get('priority', 'medium')
        dr  = {
            'low':    data['settings'].get('default_reminder_low',    60),
            'medium': data['settings'].get('default_reminder_medium', 30),
            'high':   data['settings'].get('default_reminder_high',   15)
        }
        ts = now()
        task = {
            'id':              nid(data, 'tasks'),
            'title':           b.get('title', 'Untitled'),
            'description':     b.get('description', ''),
            'category':        b.get('category', 'General'),
            'priority':        pri,
            'status':          b.get('status', 'pending'),
            'due_date':        b.get('due_date') or None,
            'due_time':        b.get('due_time') or None,
            'reminder_mins':   b.get('reminder_mins', dr.get(pri, 30)),
            'assigned_to':     b.get('assigned_to', ''),
            'project':         b.get('project', ''),
            'tags':            json.dumps(b.get('tags', [])),
            'notes':           b.get('notes', ''),
            'estimated_hours': b.get('estimated_hours', 0),
            'progress':        b.get('progress', 0),
            'is_pinned':       1 if b.get('is_pinned') else 0,
            'created_at':      ts, 'updated_at': ts,
            'completed_at':    None, 'reminder_sent': 0, 'snooze_until': None
        }
        data['tasks'].insert(0, task)
        # NOTE: no 'created' notification pushed server-side
        gen_notifs_local(data)
        sv(data)
        return jsonify(task), 201

    tasks = list(data['tasks'])
    for arg in ['status', 'priority', 'category']:
        v = request.args.get(arg, '')
        if v: tasks = [t for t in tasks if t.get(arg) == v]
    se = request.args.get('search', '').lower()
    if se:
        tasks = [t for t in tasks
                 if se in (t.get('title','') or '').lower()
                 or se in (t.get('description','') or '').lower()]
    tasks.sort(key=lambda t: t.get('is_pinned', 0), reverse=True)
    return jsonify(tasks)


@app.route('/api/tasks/<int:tid>', methods=['GET', 'PUT', 'DELETE'])
def api_task(tid):
    if USE_SUPABASE:
        return _task_sb(tid)
    return _task_local(tid)


def _task_sb(tid):
    if request.method == 'GET':
        rows = sb_get('tasks', {'id': f'eq.{tid}'})
        return jsonify(rows[0]) if rows else (jsonify({'error': 'Not found'}), 404)

    if request.method == 'DELETE':
        sb_delete('notifications', {'task_id': tid})
        sb_delete('tasks', {'id': tid})
        return jsonify({'ok': True})

    b    = request.json or {}
    rows = sb_get('tasks', {'id': f'eq.{tid}'})
    if not rows:
        return jsonify({'error': 'Not found'}), 404
    cur = rows[0]

    update = {}
    for k in ['title','description','category','priority','status','due_date','due_time',
              'reminder_mins','assigned_to','project','notes','estimated_hours',
              'progress','is_pinned','snooze_until']:
        if k in b:
            update[k] = b[k]
    if 'tags' in b:
        update['tags'] = json.dumps(b['tags']) if isinstance(b['tags'], list) else b['tags']
    update['updated_at'] = now()

    ns = b.get('status', cur.get('status', 'pending'))
    if ns == 'completed' and cur.get('status') != 'completed':
        update['completed_at'] = now()
    elif ns != 'completed':
        update['completed_at'] = None

    if 'due_date' in b or 'due_time' in b:
        update['reminder_sent'] = 0

    result = sb_patch('tasks', {'id': tid}, update)
    gen_notifs_supabase()

    if result:
        return jsonify(result)
    cur.update(update)
    return jsonify(cur)


def _task_local(tid):
    data = ld()
    task = next((t for t in data['tasks'] if t['id'] == tid), None)
    if not task:
        return jsonify({'error': 'Not found'}), 404

    if request.method == 'GET':
        return jsonify(task)

    if request.method == 'DELETE':
        data['tasks']         = [t for t in data['tasks'] if t['id'] != tid]
        data['notifications'] = [n for n in data.get('notifications', [])
                                  if n.get('task_id') != tid]
        sv(data)
        return jsonify({'ok': True})

    b      = request.json or {}
    old_st = task['status']
    for k in ['title','description','category','priority','status','due_date','due_time',
              'reminder_mins','assigned_to','project','notes','estimated_hours',
              'progress','is_pinned','snooze_until']:
        if k in b:
            task[k] = b[k]
    if 'tags' in b:
        task['tags'] = json.dumps(b['tags']) if isinstance(b['tags'], list) else b['tags']

    task['updated_at'] = now()
    ns = task['status']
    if ns == 'completed' and old_st != 'completed':
        task['completed_at'] = now()
    elif ns != 'completed':
        task['completed_at'] = None

    if 'due_date' in b or 'due_time' in b:
        task['reminder_sent'] = 0

    gen_notifs_local(data)
    sv(data)
    return jsonify(task)


@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT'])
def api_snooze(tid):
    mins          = (request.json or {}).get('minutes', 10)
    snooze_until  = (datetime.now() + timedelta(minutes=mins)).isoformat()
    if USE_SUPABASE:
        sb_patch('tasks', {'id': tid}, {'snooze_until': snooze_until, 'reminder_sent': 0})
        sb_patch('notifications', {'task_id': tid, 'type': 'reminder'}, {'is_dismissed': 1})
    else:
        data = ld()
        for t in data['tasks']:
            if t['id'] == tid:
                t['snooze_until'] = snooze_until
                t['reminder_sent'] = 0
                break
        data['notifications'] = [
            n for n in data.get('notifications', [])
            if not (n.get('task_id') == tid and n.get('type') == 'reminder')
        ]
        sv(data)
    return jsonify({'ok': True, 'snoozed_until': snooze_until})


@app.route('/api/tasks/<int:tid>/pin', methods=['PUT'])
def api_pin(tid):
    if USE_SUPABASE:
        rows = sb_get('tasks', {'id': f'eq.{tid}'})
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        new_pin = 0 if rows[0].get('is_pinned') else 1
        sb_patch('tasks', {'id': tid}, {'is_pinned': new_pin})
        return jsonify({'is_pinned': new_pin})

    data = ld()
    for t in data['tasks']:
        if t['id'] == tid:
            t['is_pinned'] = 0 if t.get('is_pinned') else 1
            sv(data)
            return jsonify({'is_pinned': t['is_pinned']})
    return jsonify({'error': 'Not found'}), 404


# ── CATEGORIES ────────────────────────────────────────────────
@app.route('/api/categories', methods=['GET', 'POST'])
def api_categories():
    if USE_SUPABASE:
        if request.method == 'POST':
            b   = request.json or {}
            cat = sb_post('categories', {'name': b.get('name'), 'color': b.get('color', '#6366f1')})
            return jsonify(cat or {}), 201
        return jsonify(sb_get('categories', {'order': 'name.asc'}) or [])

    data = ld()
    if request.method == 'POST':
        b    = request.json or {}
        name = b.get('name', '')
        if any(c['name'] == name for c in data['categories']):
            return jsonify({'error': 'Already exists'}), 400
        cat = {'id': nid(data, 'categories'), 'name': name, 'color': b.get('color', '#6366f1')}
        data['categories'].append(cat)
        sv(data)
        return jsonify(cat), 201
    return jsonify(data['categories'])


@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def api_category(cid):
    if USE_SUPABASE:
        sb_delete('categories', {'id': cid})
    else:
        data = ld()
        data['categories'] = [c for c in data['categories'] if c['id'] != cid]
        sv(data)
    return jsonify({'ok': True})


# ── NOTIFICATIONS ─────────────────────────────────────────────
@app.route('/api/notifications', methods=['GET'])
def api_notifications():
    if USE_SUPABASE:
        gen_notifs_supabase()
        ns = sb_get('notifications', {
            'is_dismissed': 'eq.0',
            'order':        'created_at.desc',
            'limit':        '80'
        }) or []
    else:
        data = ld()
        gen_notifs_local(data)
        sv(data)
        ns = [n for n in data.get('notifications', []) if not n.get('is_dismissed')]

    po = {'high': 0, 'medium': 1, 'low': 2}
    ns.sort(key=lambda n: po.get(n.get('priority', 'medium'), 1))
    return jsonify(ns)


@app.route('/api/notifications/new', methods=['GET'])
def api_notifications_new():
    """
    Returns only UNREAD notifications that are NOT type 'created'.
    This prevents duplicate popups when polling — new-task popup is
    shown once immediately by the client, not re-fired on next poll.
    """
    if USE_SUPABASE:
        gen_notifs_supabase()
        ns = sb_get('notifications', {
            'is_read':      'eq.0',
            'is_dismissed': 'eq.0',
            'order':        'created_at.desc'
        }) or []
    else:
        data = ld()
        gen_notifs_local(data)
        sv(data)
        ns = [n for n in data.get('notifications', [])
              if not n.get('is_read') and not n.get('is_dismissed')]

    # Filter out 'created' type — those are handled client-side only
    ns = [n for n in ns if n.get('type') != 'created']

    po = {'high': 0, 'medium': 1, 'low': 2}
    ns.sort(key=lambda n: po.get(n.get('priority', 'medium'), 1))
    return jsonify(ns)


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
def api_notif_read(nid):
    if USE_SUPABASE:
        sb_patch('notifications', {'id': nid}, {'is_read': 1})
    else:
        data = ld()
        for n in data.get('notifications', []):
            if n['id'] == nid:
                n['is_read'] = 1
                break
        sv(data)
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['PUT'])
def api_notifs_read_all():
    if USE_SUPABASE:
        try:
            req.patch(f'{SB_URL}/rest/v1/notifications',
                      headers=sb_headers(),
                      params={'is_dismissed': 'eq.0'},
                      json={'is_read': 1}, timeout=8)
        except Exception as e:
            print(f"read-all error: {e}")
    else:
        data = ld()
        for n in data.get('notifications', []):
            n['is_read'] = 1
        sv(data)
    return jsonify({'ok': True})


@app.route('/api/notifications/clear-read', methods=['DELETE'])
def api_notifs_clear():
    if USE_SUPABASE:
        try:
            req.delete(f'{SB_URL}/rest/v1/notifications',
                       headers=sb_headers(),
                       params={'is_read': 'eq.1'}, timeout=8)
        except Exception as e:
            print(f"clear-read error: {e}")
    else:
        data = ld()
        data['notifications'] = [
            n for n in data.get('notifications', []) if not n.get('is_read')
        ]
        sv(data)
    return jsonify({'ok': True})


# ── STATISTICS ────────────────────────────────────────────────
@app.route('/api/statistics', methods=['GET'])
def api_statistics():
    if USE_SUPABASE:
        tasks = sb_get('tasks', {'select': 'status,priority,due_date'}) or []
    else:
        tasks = ld().get('tasks', [])

    td    = datetime.now().strftime('%Y-%m-%d')
    total = len(tasks)
    comp  = sum(1 for t in tasks if t.get('status') == 'completed')
    pend  = sum(1 for t in tasks if t.get('status') == 'pending')
    prog  = sum(1 for t in tasks if t.get('status') == 'in_progress')
    ov    = sum(1 for t in tasks
                if t.get('status') != 'completed'
                and t.get('due_date') and t.get('due_date', '') < td)
    dt    = sum(1 for t in tasks
                if t.get('status') != 'completed' and t.get('due_date') == td)
    hp    = sum(1 for t in tasks
                if t.get('priority') == 'high' and t.get('status') != 'completed')

    return jsonify({
        'total': total, 'completed': comp, 'pending': pend,
        'in_progress': prog, 'overdue': ov, 'due_today': dt,
        'high_priority': hp,
        'completion_rate': round(comp / total * 100, 1) if total > 0 else 0
    })


# ── EXPORT / IMPORT ───────────────────────────────────────────
@app.route('/api/export', methods=['GET'])
def api_export():
    if USE_SUPABASE:
        tasks = sb_get('tasks',      {'select': '*'}) or []
        cats  = sb_get('categories', {'select': '*'}) or []
    else:
        data  = ld()
        tasks = data.get('tasks', [])
        cats  = data.get('categories', [])
    return jsonify({'exported_at': now(), 'tasks': tasks, 'categories': cats})


@app.route('/api/import', methods=['POST'])
def api_import():
    inc   = (request.json or {}).get('tasks', [])
    ts    = now()
    count = 0

    if USE_SUPABASE:
        for t in inc:
            sb_post('tasks', {
                'title':         t.get('title', 'Imported'),
                'description':   t.get('description', ''),
                'category':      t.get('category', 'General'),
                'priority':      t.get('priority', 'medium'),
                'status':        t.get('status', 'pending'),
                'due_date':      t.get('due_date'),
                'due_time':      t.get('due_time'),
                'reminder_mins': t.get('reminder_mins', 30),
                'assigned_to':   t.get('assigned_to', ''),
                'project':       t.get('project', ''),
                'tags':          json.dumps(t.get('tags', [])),
                'notes':         t.get('notes', ''),
                'created_at':    ts, 'updated_at': ts,
                'reminder_sent': 0, 'is_pinned': 0, 'progress': 0
            })
            count += 1
    else:
        data = ld()
        for t in inc:
            task = {
                'id':            nid(data, 'tasks'),
                'title':         t.get('title', 'Imported'),
                'description':   t.get('description', ''),
                'category':      t.get('category', 'General'),
                'priority':      t.get('priority', 'medium'),
                'status':        t.get('status', 'pending'),
                'due_date':      t.get('due_date'),
                'due_time':      t.get('due_time'),
                'reminder_mins': t.get('reminder_mins', 30),
                'assigned_to':   t.get('assigned_to', ''),
                'project':       t.get('project', ''),
                'tags':          json.dumps(t.get('tags', [])),
                'notes':         t.get('notes', ''),
                'created_at':    ts, 'updated_at': ts,
                'completed_at':  None, 'reminder_sent': 0,
                'is_pinned': 0, 'progress': 0, 'snooze_until': None
            }
            data['tasks'].insert(0, task)
            count += 1
        sv(data)

    return jsonify({'imported': count})


# ── HEALTH ────────────────────────────────────────────────────
@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({'status': 'ok', 'supabase': USE_SUPABASE, 'time': now()})