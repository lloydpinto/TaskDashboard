"""
TaskPro — Vercel Serverless API
Uses JSON file on /tmp for Vercel (ephemeral storage)
For permanent storage, use a cloud database (Supabase, PlanetScale, etc.)

NOTE: Vercel /tmp is ephemeral. For production, connect a real database.
This version uses in-memory + /tmp fallback so it WORKS on Vercel.
"""

from flask import Flask, request, jsonify, send_from_directory
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)

# ══════════════════════════════════════════════
# DATA STORAGE — JSON file in /tmp for Vercel
# ══════════════════════════════════════════════
DATA_FILE = '/tmp/taskpro_data.json'

DEFAULT_DATA = {
    "tasks": [],
    "categories": [
        {"id": 1, "name": "General", "color": "#6366f1", "icon": "folder"},
        {"id": 2, "name": "Work", "color": "#0ea5e9", "icon": "briefcase"},
        {"id": 3, "name": "Personal", "color": "#f59e0b", "icon": "user"},
        {"id": 4, "name": "Meetings", "color": "#8b5cf6", "icon": "calendar"},
        {"id": 5, "name": "Development", "color": "#10b981", "icon": "code"},
        {"id": 6, "name": "Design", "color": "#ec4899", "icon": "palette"},
        {"id": 7, "name": "Marketing", "color": "#f97316", "icon": "bullhorn"},
        {"id": 8, "name": "Finance", "color": "#14b8a6", "icon": "dollar-sign"},
        {"id": 9, "name": "HR", "color": "#6b7280", "icon": "users"},
        {"id": 10, "name": "Urgent", "color": "#ef4444", "icon": "exclamation"}
    ],
    "projects": [],
    "notifications": [],
    "activity_log": [],
    "settings": {
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
        "check_interval_secs": 30,
        "theme": "light"
    },
    "next_ids": {
        "tasks": 1,
        "categories": 11,
        "projects": 1,
        "notifications": 1,
        "activity": 1
    }
}


def load_data():
    """Load data from JSON file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                # Ensure all keys exist
                for key in DEFAULT_DATA:
                    if key not in data:
                        data[key] = DEFAULT_DATA[key]
                return data
    except Exception as e:
        print(f"Error loading data: {e}")
    return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data):
    """Save data to JSON file"""
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")


def now_iso():
    return datetime.now().isoformat()


def get_next_id(data, collection):
    """Get and increment next ID"""
    current = data["next_ids"].get(collection, 1)
    data["next_ids"][collection] = current + 1
    return current


def log_activity(data, action, task_id=None, task_title='', details=''):
    """Add activity log entry"""
    entry = {
        "id": get_next_id(data, "activity"),
        "action": action,
        "task_id": task_id,
        "task_title": task_title,
        "details": details,
        "timestamp": now_iso()
    }
    data["activity_log"].insert(0, entry)
    # Keep only last 100 entries
    data["activity_log"] = data["activity_log"][:100]


def auto_notifications(data):
    """Generate notifications for overdue/due tasks"""
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')

    existing_keys = set()
    for n in data["notifications"]:
        existing_keys.add(f"{n.get('task_id')}_{n.get('type')}")

    for task in data["tasks"]:
        if task["status"] == "completed" or not task.get("due_date"):
            continue

        tid = task["id"]
        pri = task.get("priority", "medium")
        urgency = '🔴' if pri == 'high' else '🟡' if pri == 'medium' else '🟢'

        # Overdue
        if task["due_date"] < today_str:
            key = f"{tid}_overdue"
            if key not in existing_keys:
                days = (now - datetime.strptime(task["due_date"], '%Y-%m-%d')).days
                data["notifications"].insert(0, {
                    "id": get_next_id(data, "notifications"),
                    "task_id": tid,
                    "message": f"{urgency} OVERDUE ({days}d): '{task['title']}'",
                    "type": "overdue",
                    "priority": pri,
                    "is_read": 0,
                    "is_dismissed": 0,
                    "created_at": now_iso(),
                    "task_title": task["title"],
                    "task_priority": pri
                })

        # Due today
        elif task["due_date"] == today_str:
            key = f"{tid}_due_today"
            if key not in existing_keys:
                time_info = f" at {task['due_time']}" if task.get("due_time") else ""
                data["notifications"].insert(0, {
                    "id": get_next_id(data, "notifications"),
                    "task_id": tid,
                    "message": f"{urgency} Due Today{time_info}: '{task['title']}'",
                    "type": "due_today",
                    "priority": pri,
                    "is_read": 0,
                    "is_dismissed": 0,
                    "created_at": now_iso(),
                    "task_title": task["title"],
                    "task_priority": pri
                })

        # Reminder window
        if task.get("due_time") and not task.get("reminder_sent"):
            try:
                due_dt = datetime.strptime(
                    f"{task['due_date']} {task['due_time']}", '%Y-%m-%d %H:%M'
                )
                remind_mins = task.get("reminder_mins", 30)
                remind_at = due_dt - timedelta(minutes=remind_mins)

                if now >= remind_at and now < due_dt:
                    key = f"{tid}_reminder"
                    if key not in existing_keys:
                        mins_left = int((due_dt - now).total_seconds() / 60)
                        data["notifications"].insert(0, {
                            "id": get_next_id(data, "notifications"),
                            "task_id": tid,
                            "message": f"{urgency} REMINDER: '{task['title']}' due in {mins_left} min!",
                            "type": "reminder",
                            "priority": pri,
                            "is_read": 0,
                            "is_dismissed": 0,
                            "created_at": now_iso(),
                            "task_title": task["title"],
                            "task_priority": pri
                        })
                        task["reminder_sent"] = 1
            except ValueError:
                pass

        # High priority tomorrow
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        if pri == 'high' and task["due_date"] == tomorrow:
            key = f"{tid}_upcoming_high"
            if key not in existing_keys:
                data["notifications"].insert(0, {
                    "id": get_next_id(data, "notifications"),
                    "task_id": tid,
                    "message": f"🔴 HIGH PRIORITY tomorrow: '{task['title']}'",
                    "type": "upcoming_high",
                    "priority": "high",
                    "is_read": 0,
                    "is_dismissed": 0,
                    "created_at": now_iso(),
                    "task_title": task["title"],
                    "task_priority": "high"
                })

    # Keep only last 80 notifications
    data["notifications"] = data["notifications"][:80]


# ══════════════════════════════════════════════
# CORS Middleware
# ══════════════════════════════════════════════
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response


# ══════════════════════════════════════════════
# ROUTES — Settings
# ══════════════════════════════════════════════
@app.route('/api/settings', methods=['GET'])
def get_settings():
    data = load_data()
    return jsonify(data["settings"])


@app.route('/api/settings', methods=['PUT', 'OPTIONS'])
def update_settings():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    data = load_data()
    for k, v in d.items():
        if k in data["settings"]:
            data["settings"][k] = v
    save_data(data)
    return jsonify(data["settings"])


# ══════════════════════════════════════════════
# ROUTES — Tasks
# ══════════════════════════════════════════════
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    data = load_data()
    tasks = data["tasks"]

    # Filtering
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    category = request.args.get('category', '')
    project = request.args.get('project', '')
    search = request.args.get('search', '').lower()

    if status:
        tasks = [t for t in tasks if t.get('status') == status]
    if priority:
        tasks = [t for t in tasks if t.get('priority') == priority]
    if category:
        tasks = [t for t in tasks if t.get('category') == category]
    if project:
        tasks = [t for t in tasks if t.get('project') == project]
    if search:
        tasks = [t for t in tasks if
                 search in (t.get('title', '') or '').lower() or
                 search in (t.get('description', '') or '').lower() or
                 search in (t.get('notes', '') or '').lower()]

    # Sorting
    sort_by = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    reverse = order.lower() == 'desc'

    if sort_by == 'priority':
        pri_order = {'high': 0, 'medium': 1, 'low': 2}
        tasks.sort(key=lambda t: pri_order.get(t.get('priority', 'medium'), 1), reverse=False)
    else:
        tasks.sort(key=lambda t: t.get(sort_by) or '', reverse=reverse)

    # Pinned first
    tasks.sort(key=lambda t: t.get('is_pinned', 0), reverse=True)

    return jsonify(tasks)


@app.route('/api/tasks', methods=['POST', 'OPTIONS'])
def create_task():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    data = load_data()
    settings = data["settings"]

    priority = d.get('priority', 'medium')
    default_reminders = {
        'low': settings.get('default_reminder_low', 60),
        'medium': settings.get('default_reminder_medium', 30),
        'high': settings.get('default_reminder_high', 15)
    }

    ts = now_iso()
    task = {
        "id": get_next_id(data, "tasks"),
        "title": d.get('title', 'Untitled'),
        "description": d.get('description', ''),
        "category": d.get('category', 'General'),
        "priority": priority,
        "status": d.get('status', 'pending'),
        "due_date": d.get('due_date') or None,
        "due_time": d.get('due_time') or None,
        "reminder_mins": d.get('reminder_mins', default_reminders.get(priority, 30)),
        "assigned_to": d.get('assigned_to', ''),
        "project": d.get('project', ''),
        "tags": json.dumps(d.get('tags', [])),
        "notes": d.get('notes', ''),
        "estimated_hours": d.get('estimated_hours', 0),
        "actual_hours": d.get('actual_hours', 0),
        "progress": d.get('progress', 0),
        "is_pinned": 1 if d.get('is_pinned') else 0,
        "color": d.get('color', ''),
        "created_at": ts,
        "updated_at": ts,
        "completed_at": None,
        "reminder_sent": 0,
        "snooze_until": None
    }

    data["tasks"].insert(0, task)
    log_activity(data, 'created', task['id'], task['title'])
    auto_notifications(data)
    save_data(data)

    return jsonify(task), 201


@app.route('/api/tasks/<int:tid>', methods=['GET'])
def get_task(tid):
    data = load_data()
    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if task:
        return jsonify(task)
    return jsonify({"error": "Not found"}), 404


@app.route('/api/tasks/<int:tid>', methods=['PUT', 'OPTIONS'])
def update_task(tid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    data = load_data()

    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if not task:
        return jsonify({"error": "Not found"}), 404

    old_status = task['status']
    new_status = d.get('status', task['status'])

    # Update fields
    for key in ['title', 'description', 'category', 'priority', 'status',
                'due_date', 'due_time', 'reminder_mins', 'assigned_to',
                'project', 'notes', 'estimated_hours', 'actual_hours',
                'progress', 'is_pinned', 'color', 'snooze_until']:
        if key in d:
            task[key] = d[key]

    if 'tags' in d:
        task['tags'] = json.dumps(d['tags']) if isinstance(d['tags'], list) else d['tags']

    task['updated_at'] = now_iso()

    # Handle completion
    if new_status == 'completed' and old_status != 'completed':
        task['completed_at'] = now_iso()
    elif new_status != 'completed':
        task['completed_at'] = None

    # Reset reminder if date/time changed
    if 'due_date' in d or 'due_time' in d:
        task['reminder_sent'] = 0

    log_activity(data, 'updated', tid, task['title'])
    auto_notifications(data)
    save_data(data)

    return jsonify(task)


@app.route('/api/tasks/<int:tid>', methods=['DELETE', 'OPTIONS'])
def delete_task(tid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()

    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if not task:
        return jsonify({"error": "Not found"}), 404

    title = task['title']
    data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
    data["notifications"] = [n for n in data["notifications"] if n.get("task_id") != tid]

    log_activity(data, 'deleted', tid, title)
    save_data(data)

    return jsonify({"message": "Deleted"})


@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT', 'OPTIONS'])
def snooze_task(tid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    mins = d.get('minutes', 10)
    data = load_data()

    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if task:
        task['snooze_until'] = (datetime.now() + timedelta(minutes=mins)).isoformat()
        task['reminder_sent'] = 0
        data["notifications"] = [
            n for n in data["notifications"]
            if not (n.get("task_id") == tid and n.get("type") == "reminder")
        ]
        save_data(data)
        return jsonify({"snoozed_until": task['snooze_until']})

    return jsonify({"error": "Not found"}), 404


@app.route('/api/tasks/<int:tid>/pin', methods=['PUT', 'OPTIONS'])
def pin_task(tid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()
    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if task:
        task['is_pinned'] = 0 if task.get('is_pinned') else 1
        save_data(data)
        return jsonify({"is_pinned": task['is_pinned']})
    return jsonify({"error": "Not found"}), 404


# ══════════════════════════════════════════════
# ROUTES — Categories
# ══════════════════════════════════════════════
@app.route('/api/categories', methods=['GET'])
def get_categories():
    data = load_data()
    return jsonify(data["categories"])


@app.route('/api/categories', methods=['POST', 'OPTIONS'])
def create_category():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    data = load_data()

    name = d.get('name', '')
    if any(c['name'] == name for c in data["categories"]):
        return jsonify({"error": "Category exists"}), 400

    cat = {
        "id": get_next_id(data, "categories"),
        "name": name,
        "color": d.get('color', '#6366f1'),
        "icon": d.get('icon', 'folder')
    }
    data["categories"].append(cat)
    save_data(data)
    return jsonify(cat), 201


# ══════════════════════════════════════════════
# ROUTES — Projects
# ══════════════════════════════════════════════
@app.route('/api/projects', methods=['GET'])
def get_projects():
    data = load_data()
    return jsonify(data["projects"])


@app.route('/api/projects', methods=['POST', 'OPTIONS'])
def create_project():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    data = load_data()

    name = d.get('name', '')
    if any(p['name'] == name for p in data["projects"]):
        return jsonify({"error": "Project exists"}), 400

    proj = {
        "id": get_next_id(data, "projects"),
        "name": name,
        "color": d.get('color', '#0ea5e9'),
        "description": d.get('description', ''),
        "created_at": now_iso()
    }
    data["projects"].append(proj)
    save_data(data)
    return jsonify(proj), 201


# ══════════════════════════════════════════════
# ROUTES — Notifications
# ══════════════════════════════════════════════
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    data = load_data()
    auto_notifications(data)
    save_data(data)

    notifs = [n for n in data["notifications"] if not n.get("is_dismissed")]
    # Sort: high priority first
    pri_order = {'high': 0, 'medium': 1, 'low': 2}
    notifs.sort(key=lambda n: pri_order.get(n.get('priority', 'medium'), 1))

    return jsonify(notifs[:80])


@app.route('/api/notifications/new', methods=['GET'])
def get_new_notifications():
    data = load_data()
    auto_notifications(data)
    save_data(data)

    notifs = [n for n in data["notifications"]
              if not n.get("is_read") and not n.get("is_dismissed")]
    pri_order = {'high': 0, 'medium': 1, 'low': 2}
    notifs.sort(key=lambda n: pri_order.get(n.get('priority', 'medium'), 1))

    return jsonify(notifs)


@app.route('/api/notifications/<int:nid>/read', methods=['PUT', 'OPTIONS'])
def mark_notif_read(nid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()
    for n in data["notifications"]:
        if n["id"] == nid:
            n["is_read"] = 1
            break
    save_data(data)
    return jsonify({"ok": True})


@app.route('/api/notifications/<int:nid>/dismiss', methods=['PUT', 'OPTIONS'])
def dismiss_notif(nid):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()
    for n in data["notifications"]:
        if n["id"] == nid:
            n["is_dismissed"] = 1
            break
    save_data(data)
    return jsonify({"ok": True})


@app.route('/api/notifications/read-all', methods=['PUT', 'OPTIONS'])
def mark_all_read():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()
    for n in data["notifications"]:
        n["is_read"] = 1
    save_data(data)
    return jsonify({"ok": True})


@app.route('/api/notifications/clear-read', methods=['DELETE', 'OPTIONS'])
def clear_read():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = load_data()
    data["notifications"] = [n for n in data["notifications"] if not n.get("is_read")]
    save_data(data)
    return jsonify({"ok": True})


# ══════════════════════════════════════════════
# ROUTES — Statistics
# ══════════════════════════════════════════════
@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    data = load_data()
    tasks = data["tasks"]
    today = datetime.now().strftime('%Y-%m-%d')

    total = len(tasks)
    completed = sum(1 for t in tasks if t['status'] == 'completed')
    pending = sum(1 for t in tasks if t['status'] == 'pending')
    in_progress = sum(1 for t in tasks if t['status'] == 'in_progress')
    overdue = sum(1 for t in tasks if t['status'] != 'completed'
                  and t.get('due_date') and t['due_date'] < today)
    due_today = sum(1 for t in tasks if t['status'] != 'completed'
                    and t.get('due_date') == today)
    high_pri = sum(1 for t in tasks if t['priority'] == 'high'
                   and t['status'] != 'completed')
    pinned = sum(1 for t in tasks if t.get('is_pinned')
                 and t['status'] != 'completed')
    unread = sum(1 for n in data["notifications"]
                 if not n.get("is_read") and not n.get("is_dismissed"))

    by_category = {}
    for t in tasks:
        if t['status'] != 'completed':
            cat = t.get('category', 'General')
            by_category[cat] = by_category.get(cat, 0) + 1

    return jsonify({
        "total": total,
        "completed": completed,
        "pending": pending,
        "in_progress": in_progress,
        "overdue": overdue,
        "due_today": due_today,
        "high_priority": high_pri,
        "pinned": pinned,
        "unread_notifications": unread,
        "by_category": by_category,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0
    })


# ══════════════════════════════════════════════
# ROUTES — Activity
# ══════════════════════════════════════════════
@app.route('/api/activity', methods=['GET'])
def get_activity():
    data = load_data()
    limit = request.args.get('limit', 30, type=int)
    return jsonify(data["activity_log"][:limit])


# ══════════════════════════════════════════════
# ROUTES — Export / Import
# ══════════════════════════════════════════════
@app.route('/api/export', methods=['GET'])
def export_data():
    data = load_data()
    return jsonify({
        "exported_at": now_iso(),
        "version": "2.0",
        "tasks": data["tasks"],
        "categories": data["categories"],
        "projects": data["projects"],
        "settings": data["settings"]
    })


@app.route('/api/import', methods=['POST', 'OPTIONS'])
def import_data():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    d = request.json or {}
    incoming_tasks = d.get('tasks', [])
    data = load_data()
    count = 0
    ts = now_iso()

    for t in incoming_tasks:
        task = {
            "id": get_next_id(data, "tasks"),
            "title": t.get('title', 'Imported'),
            "description": t.get('description', ''),
            "category": t.get('category', 'General'),
            "priority": t.get('priority', 'medium'),
            "status": t.get('status', 'pending'),
            "due_date": t.get('due_date'),
            "due_time": t.get('due_time'),
            "reminder_mins": t.get('reminder_mins', 30),
            "assigned_to": t.get('assigned_to', ''),
            "project": t.get('project', ''),
            "tags": json.dumps(t.get('tags', [])),
            "notes": t.get('notes', ''),
            "estimated_hours": t.get('estimated_hours', 0),
            "actual_hours": t.get('actual_hours', 0),
            "progress": t.get('progress', 0),
            "is_pinned": t.get('is_pinned', 0),
            "color": t.get('color', ''),
            "created_at": ts,
            "updated_at": ts,
            "completed_at": None,
            "reminder_sent": 0,
            "snooze_until": None
        }
        data["tasks"].insert(0, task)
        count += 1

    save_data(data)
    return jsonify({"imported": count})


# ══════════════════════════════════════════════
# CATCH-ALL for Vercel
# ══════════════════════════════════════════════
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return jsonify({"status": "TaskPro API is running", "version": "2.0"})


# Vercel handler
app = app