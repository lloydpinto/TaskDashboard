from flask import Flask, request, jsonify, Response
import json, os
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE = '/tmp/tp_data.json'

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
}


def read_db():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                for key in ['tasks','categories','notifications','settings','ids']:
                    if key not in data:
                        data[key] = get_defaults()[key]
                return data
    except Exception as e:
        print(f"read_db error: {e}")
    return get_defaults()


def get_defaults():
    return {
        "tasks": [],
        "categories": json.loads(json.dumps(DEFAULT_CATS)),
        "notifications": [],
        "settings": json.loads(json.dumps(DEFAULT_SETTINGS)),
        "ids": {"tasks":1,"categories":11,"notifications":1}
    }


def write_db(db):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(db, f)
    except Exception as e:
        print(f"write_db error: {e}")


def now():
    return datetime.now().isoformat()


def nxt(db, col):
    v = db['ids'].get(col, 1)
    db['ids'][col] = v + 1
    return v


def run_notifications(db):
    n = datetime.now()
    today = n.strftime('%Y-%m-%d')
    tomorrow = (n + timedelta(days=1)).strftime('%Y-%m-%d')

    existing_keys = set()
    for x in db.get('notifications', []):
        if not x.get('is_dismissed'):
            existing_keys.add(f"{x.get('task_id')}_{x.get('type')}")

    for t in db.get('tasks', []):
        if t.get('status') == 'completed' or not t.get('due_date'):
            continue
        tid = t['id']
        pri = t.get('priority', 'medium')
        em = '🔴' if pri == 'high' else '🟡' if pri == 'medium' else '🟢'
        dd = t['due_date']

        if dd < today:
            k = f"{tid}_overdue"
            if k not in existing_keys:
                days = max(1, (n - datetime.strptime(dd, '%Y-%m-%d')).days)
                db['notifications'].insert(0, {
                    'id': nxt(db, 'notifications'), 'task_id': tid,
                    'message': f"{em} OVERDUE ({days}d): '{t['title']}'",
                    'type': 'overdue', 'priority': pri,
                    'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                    'task_title': t['title'], 'task_priority': pri
                })

        elif dd == today:
            k = f"{tid}_due_today"
            if k not in existing_keys:
                ti = f" at {t['due_time']}" if t.get('due_time') else ''
                db['notifications'].insert(0, {
                    'id': nxt(db, 'notifications'), 'task_id': tid,
                    'message': f"{em} Due Today{ti}: '{t['title']}'",
                    'type': 'due_today', 'priority': pri,
                    'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                    'task_title': t['title'], 'task_priority': pri
                })

        if t.get('due_time') and not t.get('reminder_sent'):
            try:
                due = datetime.strptime(f"{dd} {t['due_time']}", '%Y-%m-%d %H:%M')
                rm = t.get('reminder_mins', 30) or 30
                ra = due - timedelta(minutes=rm)
                if ra <= n < due:
                    k = f"{tid}_reminder"
                    if k not in existing_keys:
                        ml = max(0, int((due - n).total_seconds() / 60))
                        db['notifications'].insert(0, {
                            'id': nxt(db, 'notifications'), 'task_id': tid,
                            'message': f"{em} REMINDER: '{t['title']}' in {ml} min!",
                            'type': 'reminder', 'priority': pri,
                            'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                            'task_title': t['title'], 'task_priority': pri
                        })
                        t['reminder_sent'] = 1
            except Exception:
                pass

        if pri == 'high' and dd == tomorrow:
            k = f"{tid}_upcoming_high"
            if k not in existing_keys:
                db['notifications'].insert(0, {
                    'id': nxt(db, 'notifications'), 'task_id': tid,
                    'message': f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'",
                    'type': 'upcoming_high', 'priority': 'high',
                    'is_read': 0, 'is_dismissed': 0, 'created_at': now(),
                    'task_title': t['title'], 'task_priority': 'high'
                })

    db['notifications'] = db['notifications'][:80]


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return r


@app.before_request
def preflight():
    if request.method == 'OPTIONS':
        r = jsonify({})
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return r, 200


@app.route('/')
def serve():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'app.html')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return Response(f.read(), content_type='text/html; charset=utf-8')
    except Exception as e:
        return Response(f'<h1>Error: {e}</h1>', content_type='text/html')


@app.route('/api/settings', methods=['GET', 'PUT'])
def settings():
    db = read_db()
    if request.method == 'PUT':
        b = request.json or {}
        for k, v in b.items():
            if k in db['settings']:
                db['settings'][k] = v
        write_db(db)
    return jsonify(db['settings'])


@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks():
    db = read_db()
    if request.method == 'POST':
        b = request.json or {}
        pri = b.get('priority', 'medium')
        dr = {
            'low': db['settings'].get('default_reminder_low', 60),
            'medium': db['settings'].get('default_reminder_medium', 30),
            'high': db['settings'].get('default_reminder_high', 15)
        }
        ts = now()
        task = {
            'id': nxt(db, 'tasks'),
            'title': (b.get('title') or 'Untitled').strip(),
            'description': b.get('description', ''),
            'category': b.get('category', 'General'),
            'priority': pri,
            'status': b.get('status', 'pending'),
            'due_date': b.get('due_date') or None,
            'due_time': b.get('due_time') or None,
            'reminder_mins': b.get('reminder_mins', dr.get(pri, 30)),
            'assigned_to': b.get('assigned_to', ''),
            'project': b.get('project', ''),
            'tags': json.dumps(b.get('tags', [])),
            'notes': b.get('notes', ''),
            'progress': b.get('progress', 0),
            'is_pinned': 1 if b.get('is_pinned') else 0,
            'created_at': ts,
            'updated_at': ts,
            'completed_at': None,
            'reminder_sent': 0,
            'snooze_until': None
        }
        db['tasks'].insert(0, task)
        run_notifications(db)
        write_db(db)
        return jsonify(task), 201

    tl = list(db['tasks'])
    for f in ['status', 'priority', 'category']:
        v = request.args.get(f, '')
        if v:
            tl = [t for t in tl if t.get(f) == v]
    q = (request.args.get('search', '') or '').lower()
    if q:
        tl = [t for t in tl if q in (t.get('title', '') or '').lower()
              or q in (t.get('description', '') or '').lower()]
    tl.sort(key=lambda t: t.get('is_pinned', 0), reverse=True)
    return jsonify(tl)


@app.route('/api/tasks/<int:tid>', methods=['GET', 'PUT', 'DELETE'])
def task(tid):
    db = read_db()
    t = next((x for x in db['tasks'] if x['id'] == tid), None)
    if not t:
        return jsonify({'error': 'Not found'}), 404

    if request.method == 'GET':
        return jsonify(t)

    if request.method == 'DELETE':
        db['tasks'] = [x for x in db['tasks'] if x['id'] != tid]
        db['notifications'] = [n for n in db['notifications'] if n.get('task_id') != tid]
        write_db(db)
        return jsonify({'ok': True})

    b = request.json or {}
    old_st = t['status']
    for k in ['title', 'description', 'category', 'priority', 'status',
              'due_date', 'due_time', 'reminder_mins', 'assigned_to',
              'project', 'notes', 'progress', 'is_pinned', 'snooze_until']:
        if k in b:
            t[k] = b[k]
    if 'tags' in b:
        t['tags'] = json.dumps(b['tags']) if isinstance(b['tags'], list) else b['tags']
    t['updated_at'] = now()
    new_st = t['status']
    if new_st == 'completed' and old_st != 'completed':
        t['completed_at'] = now()
    elif new_st != 'completed':
        t['completed_at'] = None
    if 'due_date' in b or 'due_time' in b:
        t['reminder_sent'] = 0
    run_notifications(db)
    write_db(db)
    return jsonify(t)


@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT'])
def snooze(tid):
    db = read_db()
    mins = (request.json or {}).get('minutes', 10)
    su = (datetime.now() + timedelta(minutes=mins)).isoformat()
    for t in db['tasks']:
        if t['id'] == tid:
            t['snooze_until'] = su
            t['reminder_sent'] = 0
            break
    db['notifications'] = [n for n in db['notifications']
                           if not (n.get('task_id') == tid and n.get('type') == 'reminder')]
    write_db(db)
    return jsonify({'ok': True})


@app.route('/api/tasks/<int:tid>/pin', methods=['PUT'])
def pin(tid):
    db = read_db()
    for t in db['tasks']:
        if t['id'] == tid:
            t['is_pinned'] = 0 if t.get('is_pinned') else 1
            write_db(db)
            return jsonify({'is_pinned': t['is_pinned']})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/categories', methods=['GET', 'POST'])
def categories():
    db = read_db()
    if request.method == 'POST':
        b = request.json or {}
        name = (b.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        if any(c['name'] == name for c in db['categories']):
            return jsonify({'error': 'Already exists'}), 400
        cat = {'id': nxt(db, 'categories'), 'name': name, 'color': b.get('color', '#6366f1')}
        db['categories'].append(cat)
        write_db(db)
        return jsonify(cat), 201
    return jsonify(db['categories'])


@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def del_cat(cid):
    db = read_db()
    db['categories'] = [c for c in db['categories'] if c['id'] != cid]
    write_db(db)
    return jsonify({'ok': True})


@app.route('/api/notifications')
def notifs():
    db = read_db()
    run_notifications(db)
    write_db(db)
    ns = [n for n in db['notifications'] if not n.get('is_dismissed')]
    po = {'high': 0, 'medium': 1, 'low': 2}
    ns.sort(key=lambda n: po.get(n.get('priority', 'medium'), 1))
    return jsonify(ns)


@app.route('/api/notifications/new')
def notifs_new():
    db = read_db()
    run_notifications(db)
    write_db(db)
    ns = [n for n in db['notifications']
          if not n.get('is_read') and not n.get('is_dismissed')
          and n.get('type') != 'created']
    po = {'high': 0, 'medium': 1, 'low': 2}
    ns.sort(key=lambda n: po.get(n.get('priority', 'medium'), 1))
    return jsonify(ns)


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
def read_notif(nid):
    db = read_db()
    for n in db['notifications']:
        if n['id'] == nid:
            n['is_read'] = 1
            break
    write_db(db)
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['PUT'])
def read_all():
    db = read_db()
    for n in db['notifications']:
        n['is_read'] = 1
    write_db(db)
    return jsonify({'ok': True})


@app.route('/api/notifications/clear-read', methods=['DELETE'])
def clear_read():
    db = read_db()
    db['notifications'] = [n for n in db['notifications'] if not n.get('is_read')]
    write_db(db)
    return jsonify({'ok': True})


@app.route('/api/statistics')
def stats():
    db = read_db()
    tl = db.get('tasks', [])
    today = datetime.now().strftime('%Y-%m-%d')
    total = len(tl)
    comp = sum(1 for t in tl if t.get('status') == 'completed')
    pend = sum(1 for t in tl if t.get('status') == 'pending')
    prog = sum(1 for t in tl if t.get('status') == 'in_progress')
    ov = sum(1 for t in tl if t.get('status') != 'completed'
             and t.get('due_date') and t['due_date'] < today)
    dt = sum(1 for t in tl if t.get('status') != 'completed'
             and t.get('due_date') == today)
    hp = sum(1 for t in tl if t.get('priority') == 'high'
             and t.get('status') != 'completed')
    return jsonify({
        'total': total, 'completed': comp, 'pending': pend,
        'in_progress': prog, 'overdue': ov, 'due_today': dt,
        'high_priority': hp,
        'completion_rate': round(comp / total * 100, 1) if total else 0
    })


@app.route('/api/export')
def export():
    db = read_db()
    return jsonify({'exported_at': now(), 'tasks': db['tasks'], 'categories': db['categories']})


@app.route('/api/import', methods=['POST'])
def import_data():
    db = read_db()
    inc = (request.json or {}).get('tasks', [])
    ts = now()
    count = 0
    for t in inc:
        db['tasks'].insert(0, {
            'id': nxt(db, 'tasks'),
            'title': t.get('title', 'Imported'),
            'description': t.get('description', ''),
            'category': t.get('category', 'General'),
            'priority': t.get('priority', 'medium'),
            'status': t.get('status', 'pending'),
            'due_date': t.get('due_date'),
            'due_time': t.get('due_time'),
            'reminder_mins': t.get('reminder_mins', 30),
            'assigned_to': t.get('assigned_to', ''),
            'project': t.get('project', ''),
            'tags': json.dumps(t.get('tags', [])),
            'notes': t.get('notes', ''),
            'created_at': ts, 'updated_at': ts,
            'completed_at': None, 'reminder_sent': 0,
            'is_pinned': 0, 'progress': 0, 'snooze_until': None
        })
        count += 1
    write_db(db)
    return jsonify({'imported': count})


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': now()})