"""
TaskPro — Ultimate Professional Task Dashboard
═══════════════════════════════════════════════
Features:
  - Persistent SQLite database (never resets)
  - Custom reminder settings per task
  - Priority-based notification escalation
  - Global settings for defaults
  - Due-time aware reminder engine
  - Activity logging & analytics
  - Import / Export
  - Auto recurring task check
"""

from flask import Flask, render_template, request, jsonify
import sqlite3, json, os, webbrowser, threading
from datetime import datetime, timedelta

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'taskpro_data.db')


# ═══════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        title           TEXT    NOT NULL,
        description     TEXT    DEFAULT '',
        category        TEXT    DEFAULT 'General',
        priority        TEXT    DEFAULT 'medium',
        status          TEXT    DEFAULT 'pending',
        due_date        TEXT,
        due_time        TEXT,
        reminder_mins   INTEGER DEFAULT 30,
        assigned_to     TEXT    DEFAULT '',
        project         TEXT    DEFAULT '',
        tags            TEXT    DEFAULT '[]',
        notes           TEXT    DEFAULT '',
        estimated_hours REAL    DEFAULT 0,
        actual_hours    REAL    DEFAULT 0,
        progress        INTEGER DEFAULT 0,
        is_pinned       INTEGER DEFAULT 0,
        color           TEXT    DEFAULT '',
        created_at      TEXT    NOT NULL,
        updated_at      TEXT    NOT NULL,
        completed_at    TEXT,
        reminder_sent   INTEGER DEFAULT 0,
        snooze_until    TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name  TEXT UNIQUE NOT NULL,
        color TEXT DEFAULT '#6366f1',
        icon  TEXT DEFAULT 'folder'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE NOT NULL,
        color       TEXT DEFAULT '#0ea5e9',
        description TEXT DEFAULT '',
        deadline    TEXT,
        created_at  TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER,
        message         TEXT,
        type            TEXT DEFAULT 'reminder',
        priority        TEXT DEFAULT 'medium',
        is_read         INTEGER DEFAULT 0,
        is_dismissed    INTEGER DEFAULT 0,
        created_at      TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        action     TEXT,
        task_id    INTEGER,
        task_title TEXT,
        details    TEXT,
        timestamp  TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id                      INTEGER PRIMARY KEY DEFAULT 1,
        default_reminder_low    INTEGER DEFAULT 60,
        default_reminder_medium INTEGER DEFAULT 30,
        default_reminder_high   INTEGER DEFAULT 15,
        sound_enabled           INTEGER DEFAULT 1,
        popup_enabled           INTEGER DEFAULT 1,
        browser_notif_enabled   INTEGER DEFAULT 1,
        popup_duration_low      INTEGER DEFAULT 5,
        popup_duration_medium   INTEGER DEFAULT 8,
        popup_duration_high     INTEGER DEFAULT 12,
        auto_snooze_mins        INTEGER DEFAULT 10,
        working_hours_start     TEXT    DEFAULT '09:00',
        working_hours_end       TEXT    DEFAULT '18:00',
        theme                   TEXT    DEFAULT 'light',
        check_interval_secs     INTEGER DEFAULT 30
    )''')

    # Seed settings
    c.execute('INSERT OR IGNORE INTO settings (id) VALUES (1)')

    # Seed default categories
    defaults = [
        ('General','#6366f1','folder'),('Work','#0ea5e9','briefcase'),
        ('Personal','#f59e0b','user'),('Meetings','#8b5cf6','calendar'),
        ('Development','#10b981','code'),('Design','#ec4899','palette'),
        ('Marketing','#f97316','bullhorn'),('Finance','#14b8a6','dollar-sign'),
        ('HR','#6b7280','users'),('Urgent','#ef4444','exclamation'),
    ]
    for name, color, icon in defaults:
        c.execute('INSERT OR IGNORE INTO categories (name,color,icon) VALUES (?,?,?)',
                  (name, color, icon))

    conn.commit()
    conn.close()
    print("✅ Database ready:", DATABASE)


# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════
def now_iso():
    return datetime.now().isoformat()


def log_activity(action, task_id=None, task_title='', details=''):
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO activity_log (action,task_id,task_title,details,timestamp) VALUES (?,?,?,?,?)',
            (action, task_id, task_title, details, now_iso()))
        conn.commit()
        conn.close()
    except:
        pass


def get_settings():
    conn = get_db()
    row = conn.execute('SELECT * FROM settings WHERE id=1').fetchone()
    conn.close()
    return dict(row) if row else {}


def create_notification(conn, task_id, message, ntype, priority):
    """Create notification only if same one doesn't exist (dedup)"""
    existing = conn.execute(
        "SELECT 1 FROM notifications WHERE task_id=? AND type=? AND is_dismissed=0",
        (task_id, ntype)
    ).fetchone()
    if not existing:
        conn.execute(
            'INSERT INTO notifications (task_id,message,type,priority,created_at) VALUES (?,?,?,?,?)',
            (task_id, message, ntype, priority, now_iso()))


def auto_notifications():
    """
    Smart notification engine:
    - Checks overdue tasks
    - Checks tasks due today
    - Checks tasks due within their reminder window
    - Priority affects urgency level
    """
    conn = get_db()
    c = conn.cursor()
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    now_time = now.strftime('%H:%M')
    settings = dict(c.execute('SELECT * FROM settings WHERE id=1').fetchone())

    # 1. OVERDUE tasks
    c.execute("""
        SELECT id, title, priority, due_date, due_time FROM tasks
        WHERE status != 'completed' AND due_date IS NOT NULL AND due_date < ?
    """, (today_str,))
    for t in c.fetchall():
        days_over = (now - datetime.strptime(t['due_date'], '%Y-%m-%d')).days
        urgency = '🔴' if t['priority'] == 'high' else '🟡' if t['priority'] == 'medium' else '🟢'
        msg = f"{urgency} OVERDUE ({days_over}d): '{t['title']}'"
        create_notification(conn, t['id'], msg, 'overdue', t['priority'])

    # 2. DUE TODAY tasks
    c.execute("""
        SELECT id, title, priority, due_time FROM tasks
        WHERE status != 'completed' AND due_date = ?
    """, (today_str,))
    for t in c.fetchall():
        time_info = f" at {t['due_time']}" if t['due_time'] else ''
        urgency = '🔴' if t['priority'] == 'high' else '🟡' if t['priority'] == 'medium' else '🟢'
        msg = f"{urgency} Due Today{time_info}: '{t['title']}'"
        create_notification(conn, t['id'], msg, 'due_today', t['priority'])

    # 3. REMINDER window check (time-based)
    c.execute("""
        SELECT id, title, priority, due_date, due_time, reminder_mins, reminder_sent, snooze_until
        FROM tasks
        WHERE status != 'completed'
          AND due_date IS NOT NULL
          AND due_time IS NOT NULL
          AND reminder_sent = 0
    """)
    for t in c.fetchall():
        # Check snooze
        if t['snooze_until']:
            try:
                if now < datetime.fromisoformat(t['snooze_until']):
                    continue
            except:
                pass

        try:
            due_dt = datetime.strptime(f"{t['due_date']} {t['due_time']}", '%Y-%m-%d %H:%M')
            remind_at = due_dt - timedelta(minutes=t['reminder_mins'] or 30)

            if now >= remind_at and now < due_dt:
                mins_left = int((due_dt - now).total_seconds() / 60)
                urgency = '🔴' if t['priority'] == 'high' else '🟡' if t['priority'] == 'medium' else '🟢'
                msg = f"{urgency} REMINDER: '{t['title']}' due in {mins_left} min!"
                create_notification(conn, t['id'], msg, 'reminder', t['priority'])
                c.execute('UPDATE tasks SET reminder_sent=1 WHERE id=?', (t['id'],))
        except ValueError:
            pass

    # 4. Upcoming HIGH priority tasks (within 24h)
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    c.execute("""
        SELECT id, title, due_date, due_time FROM tasks
        WHERE status != 'completed' AND priority = 'high'
          AND due_date = ?
    """, (tomorrow,))
    for t in c.fetchall():
        msg = f"🔴 HIGH PRIORITY tomorrow: '{t['title']}'"
        create_notification(conn, t['id'], msg, 'upcoming_high', 'high')

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════
# ROUTES — Page
# ═══════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')


# ═══════════════════════════════════════════════
# ROUTES — Settings
# ═══════════════════════════════════════════════
@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    return jsonify(get_settings())


@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    d = request.json or {}
    conn = get_db()
    allowed = [
        'default_reminder_low', 'default_reminder_medium', 'default_reminder_high',
        'sound_enabled', 'popup_enabled', 'browser_notif_enabled',
        'popup_duration_low', 'popup_duration_medium', 'popup_duration_high',
        'auto_snooze_mins', 'working_hours_start', 'working_hours_end',
        'theme', 'check_interval_secs'
    ]
    sets = []
    vals = []
    for k in allowed:
        if k in d:
            sets.append(f'{k}=?')
            vals.append(d[k])
    if sets:
        vals.append(1)
        conn.execute(f"UPDATE settings SET {','.join(sets)} WHERE id=?", vals)
        conn.commit()
    row = dict(conn.execute('SELECT * FROM settings WHERE id=1').fetchone())
    conn.close()
    log_activity('settings_updated', details=json.dumps(d))
    return jsonify(row)


# ═══════════════════════════════════════════════
# ROUTES — Tasks
# ═══════════════════════════════════════════════
@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    conn = get_db()
    c = conn.cursor()
    q = 'SELECT * FROM tasks WHERE 1=1'
    p = []

    for key, col in [('status', 'status'), ('priority', 'priority'),
                     ('category', 'category'), ('project', 'project')]:
        v = request.args.get(key, '')
        if v:
            q += f' AND {col}=?'
            p.append(v)

    search = request.args.get('search', '')
    if search:
        q += ' AND (title LIKE ? OR description LIKE ? OR notes LIKE ? OR tags LIKE ?)'
        s = f'%{search}%'
        p += [s, s, s, s]

    pinned = request.args.get('pinned', '')
    if pinned == '1':
        q += ' AND is_pinned=1'

    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc').upper()
    allowed_sorts = {'created_at', 'updated_at', 'due_date', 'priority', 'title', 'status'}
    if sort not in allowed_sorts:
        sort = 'created_at'
    if order not in ('ASC', 'DESC'):
        order = 'DESC'

    q += ' ORDER BY is_pinned DESC, '

    if sort == 'priority':
        q += "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 END"
    else:
        q += f'{sort} {order}'

    c.execute(q, p)
    tasks = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(tasks)


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    d = request.json or {}
    conn = get_db()
    c = conn.cursor()
    ts = now_iso()

    # Get default reminder based on priority from settings
    settings = get_settings()
    priority = d.get('priority', 'medium')
    default_reminder = {
        'low': settings.get('default_reminder_low', 60),
        'medium': settings.get('default_reminder_medium', 30),
        'high': settings.get('default_reminder_high', 15),
    }.get(priority, 30)

    reminder_mins = d.get('reminder_mins', default_reminder)

    c.execute('''INSERT INTO tasks
        (title,description,category,priority,status,due_date,due_time,
         reminder_mins,assigned_to,project,tags,notes,estimated_hours,
         progress,is_pinned,color,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        d.get('title', 'Untitled'),
        d.get('description', ''),
        d.get('category', 'General'),
        priority,
        d.get('status', 'pending'),
        d.get('due_date') or None,
        d.get('due_time') or None,
        reminder_mins,
        d.get('assigned_to', ''),
        d.get('project', ''),
        json.dumps(d.get('tags', [])),
        d.get('notes', ''),
        d.get('estimated_hours', 0),
        d.get('progress', 0),
        1 if d.get('is_pinned') else 0,
        d.get('color', ''),
        ts, ts
    ))
    tid = c.lastrowid
    conn.commit()

    c.execute('SELECT * FROM tasks WHERE id=?', (tid,))
    task = dict(c.fetchone())
    conn.close()

    log_activity('created', tid, task['title'])
    auto_notifications()
    return jsonify(task), 201


@app.route('/api/tasks/<int:tid>', methods=['GET'])
def api_get_task(tid):
    conn = get_db()
    row = conn.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    conn.close()
    return jsonify(dict(row)) if row else (jsonify({'error': 'Not found'}), 404)


@app.route('/api/tasks/<int:tid>', methods=['PUT'])
def api_update_task(tid):
    d = request.json or {}
    conn = get_db()
    c = conn.cursor()
    cur = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    if not cur:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    cur = dict(cur)

    ns = d.get('status', cur['status'])
    completed_at = now_iso() if ns == 'completed' and cur['status'] != 'completed' else cur.get('completed_at')

    # Reset reminder_sent if due_date/time changes
    new_date = d.get('due_date', cur['due_date'])
    new_time = d.get('due_time', cur['due_time'])
    reminder_sent = cur['reminder_sent']
    if new_date != cur['due_date'] or new_time != cur['due_time']:
        reminder_sent = 0

    c.execute('''UPDATE tasks SET
        title=?,description=?,category=?,priority=?,status=?,
        due_date=?,due_time=?,reminder_mins=?,assigned_to=?,project=?,
        tags=?,notes=?,estimated_hours=?,actual_hours=?,progress=?,
        is_pinned=?,color=?,updated_at=?,completed_at=?,
        reminder_sent=?,snooze_until=?
        WHERE id=?''', (
        d.get('title', cur['title']),
        d.get('description', cur['description']),
        d.get('category', cur['category']),
        d.get('priority', cur['priority']),
        ns,
        new_date,
        new_time,
        d.get('reminder_mins', cur['reminder_mins']),
        d.get('assigned_to', cur['assigned_to']),
        d.get('project', cur['project']),
        json.dumps(d.get('tags', json.loads(cur['tags'] or '[]'))),
        d.get('notes', cur['notes']),
        d.get('estimated_hours', cur['estimated_hours']),
        d.get('actual_hours', cur['actual_hours']),
        d.get('progress', cur['progress']),
        1 if d.get('is_pinned', cur['is_pinned']) else 0,
        d.get('color', cur['color']),
        now_iso(),
        completed_at,
        reminder_sent,
        d.get('snooze_until', cur.get('snooze_until')),
        tid
    ))
    conn.commit()

    task = dict(c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone())
    conn.close()

    log_activity('updated', tid, task['title'])
    auto_notifications()
    return jsonify(task)


@app.route('/api/tasks/<int:tid>', methods=['DELETE'])
def api_delete_task(tid):
    conn = get_db()
    c = conn.cursor()
    row = c.execute('SELECT title FROM tasks WHERE id=?', (tid,)).fetchone()
    if row:
        c.execute('DELETE FROM tasks WHERE id=?', (tid,))
        c.execute('DELETE FROM notifications WHERE task_id=?', (tid,))
        conn.commit()
        conn.close()
        log_activity('deleted', tid, row['title'])
        return jsonify({'message': 'Deleted'})
    conn.close()
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT'])
def api_snooze_task(tid):
    """Snooze a task's reminder by X minutes"""
    d = request.json or {}
    mins = d.get('minutes', 10)
    snooze_until = (datetime.now() + timedelta(minutes=mins)).isoformat()
    conn = get_db()
    conn.execute('UPDATE tasks SET snooze_until=?, reminder_sent=0 WHERE id=?',
                 (snooze_until, tid))
    # Dismiss associated notifications
    conn.execute("UPDATE notifications SET is_dismissed=1 WHERE task_id=? AND type='reminder'",
                 (tid,))
    conn.commit()
    conn.close()
    return jsonify({'snoozed_until': snooze_until})


@app.route('/api/tasks/<int:tid>/pin', methods=['PUT'])
def api_pin_task(tid):
    conn = get_db()
    cur = conn.execute('SELECT is_pinned FROM tasks WHERE id=?', (tid,)).fetchone()
    if not cur:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    new_val = 0 if cur['is_pinned'] else 1
    conn.execute('UPDATE tasks SET is_pinned=? WHERE id=?', (new_val, tid))
    conn.commit()
    conn.close()
    return jsonify({'is_pinned': new_val})


# ═══════════════════════════════════════════════
# ROUTES — Categories
# ═══════════════════════════════════════════════
@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    conn = get_db()
    cats = [dict(r) for r in conn.execute('SELECT * FROM categories ORDER BY name').fetchall()]
    conn.close()
    return jsonify(cats)


@app.route('/api/categories', methods=['POST'])
def api_create_category():
    d = request.json or {}
    conn = get_db()
    try:
        conn.execute('INSERT INTO categories (name,color,icon) VALUES (?,?,?)',
                     (d.get('name'), d.get('color', '#6366f1'), d.get('icon', 'folder')))
        conn.commit()
        cat = dict(conn.execute('SELECT * FROM categories WHERE name=?', (d.get('name'),)).fetchone())
        conn.close()
        return jsonify(cat), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def api_delete_category(cid):
    conn = get_db()
    conn.execute('DELETE FROM categories WHERE id=?', (cid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════
# ROUTES — Projects
# ═══════════════════════════════════════════════
@app.route('/api/projects', methods=['GET'])
def api_get_projects():
    conn = get_db()
    rows = [dict(r) for r in conn.execute('SELECT * FROM projects ORDER BY name').fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/api/projects', methods=['POST'])
def api_create_project():
    d = request.json or {}
    conn = get_db()
    try:
        conn.execute('INSERT INTO projects (name,color,description,deadline,created_at) VALUES (?,?,?,?,?)',
                     (d.get('name'), d.get('color', '#0ea5e9'), d.get('description', ''),
                      d.get('deadline'), now_iso()))
        conn.commit()
        proj = dict(conn.execute('SELECT * FROM projects WHERE name=?', (d.get('name'),)).fetchone())
        conn.close()
        return jsonify(proj), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


# ═══════════════════════════════════════════════
# ROUTES — Notifications
# ═══════════════════════════════════════════════
@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    auto_notifications()
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT n.*, t.title as task_title, t.due_date, t.due_time, t.priority as task_priority
        FROM notifications n
        LEFT JOIN tasks t ON n.task_id = t.id
        WHERE n.is_dismissed = 0
        ORDER BY
            CASE n.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 END,
            n.created_at DESC
        LIMIT 80
    ''')
    notifs = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(notifs)


@app.route('/api/notifications/new', methods=['GET'])
def api_new_notifications():
    auto_notifications()
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT n.*, t.title as task_title, t.priority as task_priority
        FROM notifications n
        LEFT JOIN tasks t ON n.task_id = t.id
        WHERE n.is_read = 0 AND n.is_dismissed = 0
        ORDER BY
            CASE n.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 END,
            n.created_at DESC
    ''')
    notifs = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(notifs)


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
def api_mark_read(nid):
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read=1 WHERE id=?', (nid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/notifications/<int:nid>/dismiss', methods=['PUT'])
def api_dismiss(nid):
    conn = get_db()
    conn.execute('UPDATE notifications SET is_dismissed=1 WHERE id=?', (nid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['PUT'])
def api_mark_all_read():
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read=1')
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/notifications/clear-read', methods=['DELETE'])
def api_clear_read():
    conn = get_db()
    conn.execute('DELETE FROM notifications WHERE is_read=1')
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════
# ROUTES — Statistics
# ═══════════════════════════════════════════════
@app.route('/api/statistics', methods=['GET'])
def api_statistics():
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    def cnt(sql, params=()):
        return c.execute(sql, params).fetchone()[0]

    stats = {
        'total':              cnt('SELECT COUNT(*) FROM tasks'),
        'completed':          cnt("SELECT COUNT(*) FROM tasks WHERE status='completed'"),
        'pending':            cnt("SELECT COUNT(*) FROM tasks WHERE status='pending'"),
        'in_progress':        cnt("SELECT COUNT(*) FROM tasks WHERE status='in_progress'"),
        'overdue':            cnt("SELECT COUNT(*) FROM tasks WHERE status!='completed' AND due_date<?", (today,)),
        'due_today':          cnt("SELECT COUNT(*) FROM tasks WHERE status!='completed' AND due_date=?", (today,)),
        'pinned':             cnt("SELECT COUNT(*) FROM tasks WHERE is_pinned=1 AND status!='completed'"),
        'high_priority':      cnt("SELECT COUNT(*) FROM tasks WHERE priority='high' AND status!='completed'"),
        'unread_notifications': cnt('SELECT COUNT(*) FROM notifications WHERE is_read=0 AND is_dismissed=0'),
    }

    # By category
    c.execute("SELECT category, COUNT(*) as cnt FROM tasks WHERE status!='completed' GROUP BY category")
    stats['by_category'] = {r['category']: r['cnt'] for r in c.fetchall()}

    # By project
    c.execute("SELECT project, COUNT(*) as cnt FROM tasks WHERE status!='completed' AND project!='' GROUP BY project")
    stats['by_project'] = {r['project']: r['cnt'] for r in c.fetchall()}

    # Completion rate
    stats['completion_rate'] = round(
        stats['completed'] / stats['total'] * 100, 1
    ) if stats['total'] > 0 else 0

    conn.close()
    return jsonify(stats)


# ═══════════════════════════════════════════════
# ROUTES — Activity
# ═══════════════════════════════════════════════
@app.route('/api/activity', methods=['GET'])
def api_activity():
    limit = request.args.get('limit', 30, type=int)
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        'SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?', (limit,)
    ).fetchall()]
    conn.close()
    return jsonify(rows)


# ═══════════════════════════════════════════════
# ROUTES — Export / Import
# ═══════════════════════════════════════════════
@app.route('/api/export', methods=['GET'])
def api_export():
    conn = get_db()
    data = {
        'exported_at': now_iso(),
        'version': '2.0',
        'tasks':      [dict(r) for r in conn.execute('SELECT * FROM tasks').fetchall()],
        'categories': [dict(r) for r in conn.execute('SELECT * FROM categories').fetchall()],
        'projects':   [dict(r) for r in conn.execute('SELECT * FROM projects').fetchall()],
        'settings':   dict(conn.execute('SELECT * FROM settings WHERE id=1').fetchone()),
    }
    conn.close()
    return jsonify(data)


@app.route('/api/import', methods=['POST'])
def api_import():
    data = request.json or {}
    tasks = data.get('tasks', [])
    conn = get_db()
    c = conn.cursor()
    count = 0
    ts = now_iso()
    for t in tasks:
        try:
            c.execute('''INSERT INTO tasks
                (title,description,category,priority,status,due_date,due_time,
                 reminder_mins,assigned_to,project,tags,notes,estimated_hours,
                 progress,is_pinned,color,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                t.get('title', 'Imported'),
                t.get('description', ''),
                t.get('category', 'General'),
                t.get('priority', 'medium'),
                t.get('status', 'pending'),
                t.get('due_date'),
                t.get('due_time'),
                t.get('reminder_mins', 30),
                t.get('assigned_to', ''),
                t.get('project', ''),
                json.dumps(t.get('tags', [])),
                t.get('notes', ''),
                t.get('estimated_hours', 0),
                t.get('progress', 0),
                t.get('is_pinned', 0),
                t.get('color', ''),
                ts, ts))
            count += 1
        except:
            pass
    conn.commit()
    conn.close()
    return jsonify({'imported': count})


# ═══════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════
def open_browser():
    webbrowser.open('http://127.0.0.1:5000')


if __name__ == '__main__':
    print("=" * 60)
    print("  🚀  TaskPro — Ultimate Professional Dashboard v2.0")
    print("=" * 60)
    init_db()
    auto_notifications()
    threading.Timer(1.5, open_browser).start()
    print(f"\n  ✅  Running at http://127.0.0.1:5000")
    print(f"  📁  Database: {DATABASE}")
    print(f"  🛑  Press Ctrl+C to stop\n")
    app.run(debug=False, port=5000, threaded=True)