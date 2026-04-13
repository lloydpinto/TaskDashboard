from flask import Flask, request, jsonify, Response
import json, os, hashlib, uuid, time
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE = '/tmp/taskpro_multiuser.json'
SECRET = os.environ.get('APP_SECRET', 'taskpro-default-secret-2024')

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
    "default_reminder_low": 60,
    "default_reminder_medium": 30,
    "default_reminder_high": 15,
    "sound_enabled": 1,
    "popup_enabled": 1,
    "browser_notif_enabled": 1,
    "popup_duration_low": 5,
    "popup_duration_medium": 8,
    "popup_duration_high": 12,
    "auto_snooze_mins": 10,
    "check_interval_secs": 30
}


def load_db():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Load error: {e}")
    return {"users": {}}


def save_db(db):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(db, f)
    except Exception as e:
        print(f"Save error: {e}")


def hash_password(pw):
    return hashlib.sha256((pw + SECRET).encode()).hexdigest()


def generate_token(user_id):
    raw = f"{user_id}:{SECRET}:{int(time.time())}"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()[:48]
    return f"{token_hash}.{user_id}"


def extract_user():
    auth_header = request.headers.get('Authorization', '')
    token = ''
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        token = request.args.get('token', '')

    if not token or '.' not in token:
        return None, None

    parts = token.rsplit('.', 1)
    if len(parts) != 2:
        return None, None

    user_id = parts[1]
    db = load_db()
    if user_id in db.get('users', {}):
        return user_id, db['users'][user_id]
    return None, None


def save_user(user_id, user_data):
    db = load_db()
    db['users'][user_id] = user_data
    save_db(db)


def next_id(user_data, collection):
    val = user_data["ids"].get(collection, 1)
    user_data["ids"][collection] = val + 1
    return val


def now_iso():
    return datetime.now().isoformat()


def new_user_data(name, email, password_hash, role):
    return {
        "name": name,
        "email": email,
        "password": password_hash,
        "role": role,
        "created_at": now_iso(),
        "tasks": [],
        "categories": json.loads(json.dumps(DEFAULT_CATS)),
        "notifications": [],
        "settings": json.loads(json.dumps(DEFAULT_SETTINGS)),
        "ids": {"tasks": 1, "categories": 11, "notifications": 1}
    }


def generate_notifications(user_data):
    current = datetime.now()
    today_str = current.strftime('%Y-%m-%d')
    tomorrow_str = (current + timedelta(days=1)).strftime('%Y-%m-%d')

    existing_notifs = [
        x for x in user_data.get('notifications', [])
        if not x.get('is_dismissed')
    ]
    existing_keys = set(
        f"{x.get('task_id')}_{x.get('type')}" for x in existing_notifs
    )

    active_tasks = [
        t for t in user_data.get('tasks', [])
        if t.get('status') != 'completed' and t.get('due_date')
    ]

    for task in active_tasks:
        task_id = task['id']
        priority = task.get('priority', 'medium')
        emoji = '🔴' if priority == 'high' else '🟡' if priority == 'medium' else '🟢'
        due_date = task.get('due_date', '')

        # Check overdue
        if due_date and due_date < today_str:
            key = f"{task_id}_overdue"
            if key not in existing_keys:
                try:
                    days_overdue = max(1, (current - datetime.strptime(due_date, '%Y-%m-%d')).days)
                except:
                    days_overdue = 1
                user_data['notifications'].insert(0, {
                    'id': next_id(user_data, 'notifications'),
                    'task_id': task_id,
                    'message': f"{emoji} OVERDUE ({days_overdue}d): '{task['title']}'",
                    'type': 'overdue',
                    'priority': priority,
                    'is_read': 0,
                    'is_dismissed': 0,
                    'created_at': now_iso(),
                    'task_title': task['title'],
                    'task_priority': priority
                })

        # Check due today
        elif due_date == today_str:
            key = f"{task_id}_due_today"
            if key not in existing_keys:
                time_info = f" at {task['due_time']}" if task.get('due_time') else ''
                user_data['notifications'].insert(0, {
                    'id': next_id(user_data, 'notifications'),
                    'task_id': task_id,
                    'message': f"{emoji} Due Today{time_info}: '{task['title']}'",
                    'type': 'due_today',
                    'priority': priority,
                    'is_read': 0,
                    'is_dismissed': 0,
                    'created_at': now_iso(),
                    'task_title': task['title'],
                    'task_priority': priority
                })

        # Check time-based reminder
        if task.get('due_time') and not task.get('reminder_sent'):
            try:
                due_datetime = datetime.strptime(
                    f"{due_date} {task['due_time']}", '%Y-%m-%d %H:%M'
                )
                remind_mins = task.get('reminder_mins', 30) or 30
                remind_at = due_datetime - timedelta(minutes=remind_mins)

                if current >= remind_at and current < due_datetime:
                    key = f"{task_id}_reminder"
                    if key not in existing_keys:
                        mins_left = max(0, int(
                            (due_datetime - current).total_seconds() / 60
                        ))
                        user_data['notifications'].insert(0, {
                            'id': next_id(user_data, 'notifications'),
                            'task_id': task_id,
                            'message': f"{emoji} REMINDER: '{task['title']}' in {mins_left} min!",
                            'type': 'reminder',
                            'priority': priority,
                            'is_read': 0,
                            'is_dismissed': 0,
                            'created_at': now_iso(),
                            'task_title': task['title'],
                            'task_priority': priority
                        })
                        task['reminder_sent'] = 1
            except Exception:
                pass

        # High priority tomorrow alert
        if priority == 'high' and due_date == tomorrow_str:
            key = f"{task_id}_upcoming_high"
            if key not in existing_keys:
                user_data['notifications'].insert(0, {
                    'id': next_id(user_data, 'notifications'),
                    'task_id': task_id,
                    'message': f"🔴 HIGH PRIORITY tomorrow: '{task['title']}'",
                    'type': 'upcoming_high',
                    'priority': 'high',
                    'is_read': 0,
                    'is_dismissed': 0,
                    'created_at': now_iso(),
                    'task_title': task['title'],
                    'task_priority': 'high'
                })

    # Keep only last 80 notifications
    user_data['notifications'] = user_data['notifications'][:80]


def require_auth():
    user_id, user_data = extract_user()
    if not user_id:
        return None, None, (jsonify({'error': 'Authentication required'}), 401)
    return user_id, user_data, None


# ── CORS ────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response


@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        resp = jsonify({})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return resp, 200


# ── SERVE HTML ──────────────────────────────
@app.route('/', methods=['GET'])
def serve_app():
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static', 'app.html'
    )
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return Response(f.read(), content_type='text/html; charset=utf-8')
    except Exception as e:
        return Response(
            f'<h1>Error loading app: {e}</h1>',
            content_type='text/html'
        )


# ── AUTH ROUTES ─────────────────────────────
@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    body = request.json or {}
    name = body.get('name', '').strip()
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')
    role = body.get('role', 'Member').strip() or 'Member'

    if not name or not email or not password:
        return jsonify({'error': 'Name, email and password are required'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    db = load_db()
    for uid, udata in db.get('users', {}).items():
        if udata.get('email', '').lower() == email:
            return jsonify({'error': 'Email already registered'}), 400

    user_id = str(uuid.uuid4())[:12]
    user_data = new_user_data(name, email, hash_password(password), role)
    db['users'][user_id] = user_data
    save_db(db)

    token = generate_token(user_id)
    return jsonify({
        'token': token,
        'user': {
            'id': user_id, 'name': name,
            'email': email, 'role': role
        }
    })


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    body = request.json or {}
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    pw_hash = hash_password(password)
    db = load_db()
    for uid, udata in db.get('users', {}).items():
        if (udata.get('email', '').lower() == email and
                udata.get('password') == pw_hash):
            token = generate_token(uid)
            return jsonify({
                'token': token,
                'user': {
                    'id': uid, 'name': udata['name'],
                    'email': udata['email'],
                    'role': udata.get('role', 'Member')
                }
            })

    return jsonify({'error': 'Invalid email or password'}), 401


@app.route('/api/auth/guest', methods=['POST'])
def auth_guest():
    db = load_db()
    guest_id = 'guest_' + str(uuid.uuid4())[:8]
    guest_email = f"{guest_id}@guest.taskpro"
    user_data = new_user_data('Guest User', guest_email, '', 'Guest')
    db['users'][guest_id] = user_data
    save_db(db)
    token = generate_token(guest_id)
    return jsonify({
        'token': token,
        'user': {
            'id': guest_id, 'name': 'Guest User',
            'email': guest_email, 'role': 'Guest'
        }
    })


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    uid, udata = extract_user()
    if not uid:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({
        'user': {
            'id': uid, 'name': udata['name'],
            'email': udata['email'],
            'role': udata.get('role', 'Member')
        }
    })


@app.route('/api/auth/profile', methods=['PUT'])
def auth_update_profile():
    uid, udata = extract_user()
    if not uid:
        return jsonify({'error': 'Not authenticated'}), 401
    body = request.json or {}
    if 'name' in body and body['name'].strip():
        udata['name'] = body['name'].strip()
    if 'role' in body:
        udata['role'] = body['role'].strip()
    if 'email' in body and body['email'].strip():
        udata['email'] = body['email'].strip().lower()
    save_user(uid, udata)
    return jsonify({
        'user': {
            'id': uid, 'name': udata['name'],
            'email': udata['email'],
            'role': udata.get('role', 'Member')
        }
    })


# ── SETTINGS ────────────────────────────────
@app.route('/api/settings', methods=['GET', 'PUT'])
def api_settings():
    uid, udata, err = require_auth()
    if err:
        return err
    if request.method == 'PUT':
        body = request.json or {}
        for key, val in body.items():
            if key in udata['settings']:
                udata['settings'][key] = val
        save_user(uid, udata)
    return jsonify(udata['settings'])


# ── TASKS ───────────────────────────────────
@app.route('/api/tasks', methods=['GET', 'POST'])
def api_tasks():
    uid, udata, err = require_auth()
    if err:
        return err

    if request.method == 'POST':
        body = request.json or {}
        priority = body.get('priority', 'medium')
        default_reminders = {
            'low': udata['settings'].get('default_reminder_low', 60),
            'medium': udata['settings'].get('default_reminder_medium', 30),
            'high': udata['settings'].get('default_reminder_high', 15)
        }
        timestamp = now_iso()
        task = {
            'id': next_id(udata, 'tasks'),
            'title': body.get('title', 'Untitled'),
            'description': body.get('description', ''),
            'category': body.get('category', 'General'),
            'priority': priority,
            'status': body.get('status', 'pending'),
            'due_date': body.get('due_date') or None,
            'due_time': body.get('due_time') or None,
            'reminder_mins': body.get('reminder_mins', default_reminders.get(priority, 30)),
            'assigned_to': body.get('assigned_to', ''),
            'project': body.get('project', ''),
            'tags': json.dumps(body.get('tags', [])),
            'notes': body.get('notes', ''),
            'progress': body.get('progress', 0),
            'is_pinned': 1 if body.get('is_pinned') else 0,
            'created_at': timestamp,
            'updated_at': timestamp,
            'completed_at': None,
            'reminder_sent': 0,
            'snooze_until': None
        }
        udata['tasks'].insert(0, task)
        generate_notifications(udata)
        save_user(uid, udata)
        return jsonify(task), 201

    # GET with filters
    task_list = list(udata['tasks'])
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    category_filter = request.args.get('category', '')
    search_query = request.args.get('search', '').lower()

    if status_filter:
        task_list = [t for t in task_list if t.get('status') == status_filter]
    if priority_filter:
        task_list = [t for t in task_list if t.get('priority') == priority_filter]
    if category_filter:
        task_list = [t for t in task_list if t.get('category') == category_filter]
    if search_query:
        task_list = [
            t for t in task_list
            if search_query in (t.get('title', '') or '').lower()
            or search_query in (t.get('description', '') or '').lower()
        ]

    task_list.sort(key=lambda t: t.get('is_pinned', 0), reverse=True)
    return jsonify(task_list)


@app.route('/api/tasks/<int:task_id>', methods=['GET', 'PUT', 'DELETE'])
def api_single_task(task_id):
    uid, udata, err = require_auth()
    if err:
        return err

    task = next((t for t in udata['tasks'] if t['id'] == task_id), None)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    if request.method == 'GET':
        return jsonify(task)

    if request.method == 'DELETE':
        udata['tasks'] = [t for t in udata['tasks'] if t['id'] != task_id]
        udata['notifications'] = [
            n for n in udata.get('notifications', [])
            if n.get('task_id') != task_id
        ]
        save_user(uid, udata)
        return jsonify({'ok': True})

    # PUT - update task
    body = request.json or {}
    old_status = task['status']

    updatable_fields = [
        'title', 'description', 'category', 'priority', 'status',
        'due_date', 'due_time', 'reminder_mins', 'assigned_to',
        'project', 'notes', 'progress', 'is_pinned', 'snooze_until'
    ]
    for field in updatable_fields:
        if field in body:
            task[field] = body[field]

    if 'tags' in body:
        if isinstance(body['tags'], list):
            task['tags'] = json.dumps(body['tags'])
        else:
            task['tags'] = body['tags']

    task['updated_at'] = now_iso()
    new_status = task['status']

    if new_status == 'completed' and old_status != 'completed':
        task['completed_at'] = now_iso()
    elif new_status != 'completed':
        task['completed_at'] = None

    if 'due_date' in body or 'due_time' in body:
        task['reminder_sent'] = 0

    generate_notifications(udata)
    save_user(uid, udata)
    return jsonify(task)


@app.route('/api/tasks/<int:task_id>/snooze', methods=['PUT'])
def api_snooze_task(task_id):
    uid, udata, err = require_auth()
    if err:
        return err

    minutes = (request.json or {}).get('minutes', 10)
    snooze_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()

    for task in udata['tasks']:
        if task['id'] == task_id:
            task['snooze_until'] = snooze_until
            task['reminder_sent'] = 0
            break

    udata['notifications'] = [
        n for n in udata.get('notifications', [])
        if not (n.get('task_id') == task_id and n.get('type') == 'reminder')
    ]
    save_user(uid, udata)
    return jsonify({'ok': True, 'snoozed_until': snooze_until})


@app.route('/api/tasks/<int:task_id>/pin', methods=['PUT'])
def api_pin_task(task_id):
    uid, udata, err = require_auth()
    if err:
        return err

    for task in udata['tasks']:
        if task['id'] == task_id:
            task['is_pinned'] = 0 if task.get('is_pinned') else 1
            save_user(uid, udata)
            return jsonify({'is_pinned': task['is_pinned']})

    return jsonify({'error': 'Task not found'}), 404


# ── CATEGORIES ──────────────────────────────
@app.route('/api/categories', methods=['GET', 'POST'])
def api_categories():
    uid, udata, err = require_auth()
    if err:
        return err

    if request.method == 'POST':
        body = request.json or {}
        name = body.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        if any(c['name'] == name for c in udata['categories']):
            return jsonify({'error': 'Category already exists'}), 400
        cat = {
            'id': next_id(udata, 'categories'),
            'name': name,
            'color': body.get('color', '#6366f1')
        }
        udata['categories'].append(cat)
        save_user(uid, udata)
        return jsonify(cat), 201

    return jsonify(udata['categories'])


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
def api_delete_category(cat_id):
    uid, udata, err = require_auth()
    if err:
        return err
    udata['categories'] = [c for c in udata['categories'] if c['id'] != cat_id]
    save_user(uid, udata)
    return jsonify({'ok': True})


# ── NOTIFICATIONS ───────────────────────────
@app.route('/api/notifications', methods=['GET'])
def api_notifications():
    uid, udata, err = require_auth()
    if err:
        return err

    generate_notifications(udata)
    save_user(uid, udata)

    notif_list = [
        n for n in udata.get('notifications', [])
        if not n.get('is_dismissed')
    ]
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    notif_list.sort(
        key=lambda n: priority_order.get(n.get('priority', 'medium'), 1)
    )
    return jsonify(notif_list)


@app.route('/api/notifications/new', methods=['GET'])
def api_new_notifications():
    uid, udata, err = require_auth()
    if err:
        return err

    generate_notifications(udata)
    save_user(uid, udata)

    notif_list = [
        n for n in udata.get('notifications', [])
        if not n.get('is_read')
        and not n.get('is_dismissed')
        and n.get('type') != 'created'
    ]
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    notif_list.sort(
        key=lambda n: priority_order.get(n.get('priority', 'medium'), 1)
    )
    return jsonify(notif_list)


@app.route('/api/notifications/<int:notif_id>/read', methods=['PUT'])
def api_read_notification(notif_id):
    uid, udata, err = require_auth()
    if err:
        return err

    for notif in udata.get('notifications', []):
        if notif['id'] == notif_id:
            notif['is_read'] = 1
            break
    save_user(uid, udata)
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['PUT'])
def api_read_all_notifications():
    uid, udata, err = require_auth()
    if err:
        return err

    for notif in udata.get('notifications', []):
        notif['is_read'] = 1
    save_user(uid, udata)
    return jsonify({'ok': True})


@app.route('/api/notifications/clear-read', methods=['DELETE'])
def api_clear_read_notifications():
    uid, udata, err = require_auth()
    if err:
        return err

    udata['notifications'] = [
        n for n in udata.get('notifications', [])
        if not n.get('is_read')
    ]
    save_user(uid, udata)
    return jsonify({'ok': True})


# ── STATISTICS ──────────────────────────────
@app.route('/api/statistics', methods=['GET'])
def api_statistics():
    uid, udata, err = require_auth()
    if err:
        return err

    task_list = udata.get('tasks', [])
    today = datetime.now().strftime('%Y-%m-%d')
    total = len(task_list)
    completed = sum(1 for t in task_list if t.get('status') == 'completed')
    pending = sum(1 for t in task_list if t.get('status') == 'pending')
    in_progress = sum(1 for t in task_list if t.get('status') == 'in_progress')
    overdue = sum(
        1 for t in task_list
        if t.get('status') != 'completed'
        and t.get('due_date')
        and t.get('due_date', '') < today
    )
    due_today = sum(
        1 for t in task_list
        if t.get('status') != 'completed'
        and t.get('due_date') == today
    )
    high_priority = sum(
        1 for t in task_list
        if t.get('priority') == 'high'
        and t.get('status') != 'completed'
    )

    return jsonify({
        'total': total,
        'completed': completed,
        'pending': pending,
        'in_progress': in_progress,
        'overdue': overdue,
        'due_today': due_today,
        'high_priority': high_priority,
        'completion_rate': round(
            completed / total * 100, 1
        ) if total > 0 else 0
    })


# ── EXPORT / IMPORT ─────────────────────────
@app.route('/api/export', methods=['GET'])
def api_export():
    uid, udata, err = require_auth()
    if err:
        return err
    return jsonify({
        'exported_at': now_iso(),
        'tasks': udata.get('tasks', []),
        'categories': udata.get('categories', [])
    })


@app.route('/api/import', methods=['POST'])
def api_import():
    uid, udata, err = require_auth()
    if err:
        return err

    incoming = (request.json or {}).get('tasks', [])
    timestamp = now_iso()
    count = 0

    for t in incoming:
        task = {
            'id': next_id(udata, 'tasks'),
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
            'created_at': timestamp,
            'updated_at': timestamp,
            'completed_at': None,
            'reminder_sent': 0,
            'is_pinned': 0,
            'progress': 0,
            'snooze_until': None
        }
        udata['tasks'].insert(0, task)
        count += 1

    save_user(uid, udata)
    return jsonify({'imported': count})


# ── HEALTH ──────────────────────────────────
@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'ok',
        'time': now_iso(),
        'version': '3.0'
    })