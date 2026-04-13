from flask import Flask, request, jsonify, Response
import json, os
from datetime import datetime, timedelta

app = Flask(__name__)
DATA_FILE = '/tmp/tp.json'

DEFAULT = {
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
    "projects": [],
    "notifications": [],
    "activity": [],
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
        "check_interval_secs": 30
    },
    "ids": {"tasks":1,"categories":11,"projects":1,"notifications":1,"activity":1}
}

def ld():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,'r') as f:
                data = json.load(f)
                for k in DEFAULT:
                    if k not in data:
                        data[k] = DEFAULT[k]
                return data
    except:
        pass
    return json.loads(json.dumps(DEFAULT))

def sv(data):
    try:
        with open(DATA_FILE,'w') as f:
            json.dump(data, f)
    except:
        pass

def now():
    return datetime.now().isoformat()

def nid(data, col):
    v = data["ids"].get(col, 1)
    data["ids"][col] = v + 1
    return v

def logact(data, action, tid=None, title=''):
    data["activity"].insert(0, {
        "id": nid(data, "activity"),
        "action": action,
        "task_id": tid,
        "task_title": title,
        "timestamp": now()
    })
    data["activity"] = data["activity"][:100]

def gen_notifs(data):
    n = datetime.now()
    td = n.strftime('%Y-%m-%d')
    tm = (n + timedelta(days=1)).strftime('%Y-%m-%d')
    ex = set()
    for x in data["notifications"]:
        ex.add(str(x.get('task_id','')) + '_' + str(x.get('type','')))
    for t in data["tasks"]:
        if t["status"] == "completed" or not t.get("due_date"):
            continue
        tid = t["id"]
        pri = t.get("priority","medium")
        u = '🔴' if pri=='high' else '🟡' if pri=='medium' else '🟢'
        if t["due_date"] < td:
            k = str(tid)+'_overdue'
            if k not in ex:
                days = (n - datetime.strptime(t["due_date"],'%Y-%m-%d')).days
                data["notifications"].insert(0,{
                    "id":nid(data,"notifications"),"task_id":tid,
                    "message":u+" OVERDUE("+str(days)+"d): '"+t['title']+"'",
                    "type":"overdue","priority":pri,"is_read":0,"is_dismissed":0,
                    "created_at":now(),"task_title":t["title"],"task_priority":pri
                })
        elif t["due_date"] == td:
            k = str(tid)+'_due_today'
            if k not in ex:
                ti = " at "+t['due_time'] if t.get("due_time") else ""
                data["notifications"].insert(0,{
                    "id":nid(data,"notifications"),"task_id":tid,
                    "message":u+" Due Today"+ti+": '"+t['title']+"'",
                    "type":"due_today","priority":pri,"is_read":0,"is_dismissed":0,
                    "created_at":now(),"task_title":t["title"],"task_priority":pri
                })
        if t.get("due_time") and not t.get("reminder_sent"):
            try:
                due = datetime.strptime(t['due_date']+" "+t['due_time'],'%Y-%m-%d %H:%M')
                ra = due - timedelta(minutes=t.get("reminder_mins",30))
                if n >= ra and n < due:
                    k = str(tid)+'_reminder'
                    if k not in ex:
                        ml = int((due-n).total_seconds()/60)
                        data["notifications"].insert(0,{
                            "id":nid(data,"notifications"),"task_id":tid,
                            "message":u+" REMINDER: '"+t['title']+"' in "+str(ml)+"min!",
                            "type":"reminder","priority":pri,"is_read":0,"is_dismissed":0,
                            "created_at":now(),"task_title":t["title"],"task_priority":pri
                        })
                        t["reminder_sent"] = 1
            except:
                pass
        if pri=='high' and t["due_date"]==tm:
            k = str(tid)+'_upcoming_high'
            if k not in ex:
                data["notifications"].insert(0,{
                    "id":nid(data,"notifications"),"task_id":tid,
                    "message":"🔴 HIGH PRIORITY tomorrow: '"+t['title']+"'",
                    "type":"upcoming_high","priority":"high","is_read":0,"is_dismissed":0,
                    "created_at":now(),"task_title":t["title"],"task_priority":"high"
                })
    data["notifications"] = data["notifications"][:80]

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return r

@app.route('/', methods=['GET'])
def home():
    return Response(get_html(), content_type='text/html; charset=utf-8')

@app.route('/api/settings', methods=['GET','PUT','OPTIONS'])
def settings_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    if request.method == 'PUT':
        b = request.json or {}
        for k,v in b.items():
            if k in data["settings"]:
                data["settings"][k] = v
        sv(data)
    return jsonify(data["settings"])

@app.route('/api/tasks', methods=['GET','POST','OPTIONS'])
def tasks_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    if request.method == 'POST':
        b = request.json or {}
        pri = b.get('priority','medium')
        s = data["settings"]
        dr = {'low':s.get('default_reminder_low',60),'medium':s.get('default_reminder_medium',30),'high':s.get('default_reminder_high',15)}
        ts = now()
        task = {
            "id":nid(data,"tasks"),"title":b.get('title','Untitled'),
            "description":b.get('description',''),"category":b.get('category','General'),
            "priority":pri,"status":b.get('status','pending'),
            "due_date":b.get('due_date') or None,"due_time":b.get('due_time') or None,
            "reminder_mins":b.get('reminder_mins',dr.get(pri,30)),
            "assigned_to":b.get('assigned_to',''),"project":b.get('project',''),
            "tags":json.dumps(b.get('tags',[])),"notes":b.get('notes',''),
            "estimated_hours":b.get('estimated_hours',0),"progress":b.get('progress',0),
            "is_pinned":1 if b.get('is_pinned') else 0,
            "created_at":ts,"updated_at":ts,"completed_at":None,
            "reminder_sent":0,"snooze_until":None
        }
        data["tasks"].insert(0, task)
        logact(data,'created',task['id'],task['title'])
        gen_notifs(data)
        sv(data)
        return jsonify(task), 201
    tasks = list(data["tasks"])
    st = request.args.get('status','')
    pr = request.args.get('priority','')
    ca = request.args.get('category','')
    pj = request.args.get('project','')
    se = request.args.get('search','').lower()
    if st: tasks = [t for t in tasks if t.get('status')==st]
    if pr: tasks = [t for t in tasks if t.get('priority')==pr]
    if ca: tasks = [t for t in tasks if t.get('category')==ca]
    if pj: tasks = [t for t in tasks if t.get('project')==pj]
    if se: tasks = [t for t in tasks if se in (t.get('title','')or'').lower() or se in (t.get('description','')or'').lower()]
    so = request.args.get('sort','created_at')
    rv = request.args.get('order','desc').lower() == 'desc'
    if so == 'priority':
        po = {'high':0,'medium':1,'low':2}
        tasks.sort(key=lambda t: po.get(t.get('priority','medium'),1))
    else:
        tasks.sort(key=lambda t: t.get(so) or '', reverse=rv)
    tasks.sort(key=lambda t: t.get('is_pinned',0), reverse=True)
    return jsonify(tasks)

@app.route('/api/tasks/<int:tid>', methods=['GET','PUT','DELETE','OPTIONS'])
def task_route(tid):
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    task = next((t for t in data["tasks"] if t["id"]==tid), None)
    if not task: return jsonify({"error":"Not found"}), 404
    if request.method == 'GET': return jsonify(task)
    if request.method == 'DELETE':
        title = task['title']
        data["tasks"] = [t for t in data["tasks"] if t["id"]!=tid]
        data["notifications"] = [n for n in data["notifications"] if n.get("task_id")!=tid]
        logact(data,'deleted',tid,title)
        sv(data)
        return jsonify({"ok":True})
    b = request.json or {}
    old_st = task['status']
    for k in ['title','description','category','priority','status','due_date','due_time','reminder_mins','assigned_to','project','notes','estimated_hours','progress','is_pinned','snooze_until']:
        if k in b: task[k] = b[k]
    if 'tags' in b: task['tags'] = json.dumps(b['tags']) if isinstance(b['tags'],list) else b['tags']
    task['updated_at'] = now()
    ns = task['status']
    if ns=='completed' and old_st!='completed': task['completed_at'] = now()
    elif ns!='completed': task['completed_at'] = None
    if 'due_date' in b or 'due_time' in b: task['reminder_sent'] = 0
    logact(data,'updated',tid,task['title'])
    gen_notifs(data)
    sv(data)
    return jsonify(task)

@app.route('/api/tasks/<int:tid>/snooze', methods=['PUT','OPTIONS'])
def snooze_route(tid):
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    task = next((t for t in data["tasks"] if t["id"]==tid), None)
    if not task: return jsonify({"error":"Not found"}), 404
    mins = (request.json or {}).get('minutes',10)
    task['snooze_until'] = (datetime.now()+timedelta(minutes=mins)).isoformat()
    task['reminder_sent'] = 0
    data["notifications"] = [n for n in data["notifications"] if not(n.get("task_id")==tid and n.get("type")=="reminder")]
    sv(data)
    return jsonify({"ok":True})

@app.route('/api/tasks/<int:tid>/pin', methods=['PUT','OPTIONS'])
def pin_route(tid):
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    task = next((t for t in data["tasks"] if t["id"]==tid), None)
    if not task: return jsonify({"error":"Not found"}), 404
    task['is_pinned'] = 0 if task.get('is_pinned') else 1
    sv(data)
    return jsonify({"is_pinned":task['is_pinned']})

@app.route('/api/categories', methods=['GET','POST','OPTIONS'])
def cats_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    if request.method == 'POST':
        b = request.json or {}
        name = b.get('name','')
        if any(c['name']==name for c in data["categories"]): return jsonify({"error":"Exists"}), 400
        cat = {"id":nid(data,"categories"),"name":name,"color":b.get('color','#6366f1')}
        data["categories"].append(cat)
        sv(data)
        return jsonify(cat), 201
    return jsonify(data["categories"])

@app.route('/api/projects', methods=['GET','POST','OPTIONS'])
def projs_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    if request.method == 'POST':
        b = request.json or {}
        name = b.get('name','')
        if any(p['name']==name for p in data["projects"]): return jsonify({"error":"Exists"}), 400
        proj = {"id":nid(data,"projects"),"name":name,"color":b.get('color','#0ea5e9'),"description":b.get('description',''),"created_at":now()}
        data["projects"].append(proj)
        sv(data)
        return jsonify(proj), 201
    return jsonify(data["projects"])

@app.route('/api/notifications', methods=['GET'])
def notifs_route():
    data = ld()
    gen_notifs(data)
    sv(data)
    ns = [n for n in data["notifications"] if not n.get("is_dismissed")]
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns[:80])

@app.route('/api/notifications/new', methods=['GET'])
def new_notifs_route():
    data = ld()
    gen_notifs(data)
    sv(data)
    ns = [n for n in data["notifications"] if not n.get("is_read") and not n.get("is_dismissed")]
    po = {'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n: po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/<int:nid2>/read', methods=['PUT','OPTIONS'])
def read_notif(nid2):
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    for n in data["notifications"]:
        if n["id"] == nid2: n["is_read"] = 1; break
    sv(data)
    return jsonify({"ok":True})

@app.route('/api/notifications/read-all', methods=['PUT','OPTIONS'])
def read_all_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    for n in data["notifications"]: n["is_read"] = 1
    sv(data)
    return jsonify({"ok":True})

@app.route('/api/notifications/clear-read', methods=['DELETE','OPTIONS'])
def clear_read_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = ld()
    data["notifications"] = [n for n in data["notifications"] if not n.get("is_read")]
    sv(data)
    return jsonify({"ok":True})

@app.route('/api/statistics', methods=['GET'])
def stats_route():
    data = ld()
    ts = data["tasks"]
    td = datetime.now().strftime('%Y-%m-%d')
    total = len(ts)
    comp = sum(1 for t in ts if t['status']=='completed')
    pend = sum(1 for t in ts if t['status']=='pending')
    prog = sum(1 for t in ts if t['status']=='in_progress')
    ov = sum(1 for t in ts if t['status']!='completed' and t.get('due_date') and t['due_date']<td)
    dt = sum(1 for t in ts if t['status']!='completed' and t.get('due_date')==td)
    hp = sum(1 for t in ts if t['priority']=='high' and t['status']!='completed')
    return jsonify({
        "total":total,"completed":comp,"pending":pend,"in_progress":prog,
        "overdue":ov,"due_today":dt,"high_priority":hp,
        "completion_rate":round(comp/total*100,1) if total>0 else 0
    })

@app.route('/api/activity', methods=['GET'])
def activity_route():
    data = ld()
    lim = request.args.get('limit',30,type=int)
    return jsonify(data["activity"][:lim])

@app.route('/api/export', methods=['GET'])
def export_route():
    data = ld()
    return jsonify({"exported_at":now(),"tasks":data["tasks"],"categories":data["categories"],"projects":data["projects"],"settings":data["settings"]})

@app.route('/api/import', methods=['POST','OPTIONS'])
def import_route():
    if request.method == 'OPTIONS': return jsonify({}), 200
    inc = (request.json or {}).get('tasks',[])
    data = ld()
    ts = now()
    count = 0
    for t in inc:
        task = {
            "id":nid(data,"tasks"),"title":t.get('title','Imported'),
            "description":t.get('description',''),"category":t.get('category','General'),
            "priority":t.get('priority','medium'),"status":t.get('status','pending'),
            "due_date":t.get('due_date'),"due_time":t.get('due_time'),
            "reminder_mins":t.get('reminder_mins',30),"assigned_to":t.get('assigned_to',''),
            "project":t.get('project',''),"tags":json.dumps(t.get('tags',[])),"notes":t.get('notes',''),
            "estimated_hours":0,"progress":0,"is_pinned":0,
            "created_at":ts,"updated_at":ts,"completed_at":None,"reminder_sent":0,"snooze_until":None
        }
        data["tasks"].insert(0,task)
        count += 1
    sv(data)
    return jsonify({"imported":count})

def get_html():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TaskPro</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--P:#4f46e5;--PH:#4338ca;--PL:#818cf8;--S:#0ea5e9;--OK:#22c55e;--WA:#f59e0b;--ER:#ef4444;--bg:#f0f2f8;--card:#fff;--inp:#f8fafc;--tx:#1e293b;--txm:#64748b;--bdr:#e2e8f0;--sh:0 8px 30px rgba(0,0,0,.12);--r:12px;--sw:230px;--hh:56px}
body.dark{--bg:#0b1120;--card:#161f33;--inp:#0b1120;--tx:#e8edf5;--txm:#8899bb;--bdr:#1e2d47}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);font-size:14px;overflow:hidden;height:100vh}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:2px}
.app{display:flex;width:100vw;height:100vh}
.sb{width:var(--sw);flex-shrink:0;background:var(--card);border-right:1px solid var(--bdr);display:flex;flex-direction:column;height:100vh;transition:width .25s;overflow:hidden;z-index:50}
.sb.slim{width:56px}
.sbb{height:var(--hh);display:flex;align-items:center;gap:10px;padding:0 14px;border-bottom:1px solid var(--bdr);flex-shrink:0}
.sbl{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.sbn{font-size:15px;font-weight:800;white-space:nowrap;background:linear-gradient(135deg,var(--P),var(--S));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sb.slim .sbn{display:none}
.sbnav{flex:1;overflow-y:auto;padding:8px 5px}
.nss{margin-bottom:14px}
.nsl{font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--txm);padding:0 8px;margin-bottom:4px}
.sb.slim .nsl{opacity:0}
.nbt{width:100%;display:flex;align-items:center;gap:8px;padding:8px 10px;border:none;background:none;border-radius:7px;cursor:pointer;color:var(--txm);transition:all .2s;text-align:left;white-space:nowrap;overflow:hidden;font-size:12px;font-weight:500}
.nbt i{width:15px;text-align:center;font-size:12px;flex-shrink:0}
.nbt .nt{flex:1}
.nbt .nc{background:var(--bg);color:var(--txm);font-size:9px;padding:1px 6px;border-radius:8px;flex-shrink:0}
.nbt:hover{background:var(--bg);color:var(--tx)}
.nbt.on{background:linear-gradient(135deg,var(--P),var(--PH));color:#fff}
.nbt.on .nc{background:rgba(255,255,255,.25);color:#fff}
.sb.slim .nbt .nt,.sb.slim .nbt .nc{display:none}
.sb.slim .nbt{justify-content:center;padding:9px}
.rt{flex:1;display:flex;flex-direction:column;min-width:0;height:100vh;overflow:hidden}
.hd{height:var(--hh);background:var(--card);border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px;padding:0 16px;flex-shrink:0}
.hbt{width:32px;height:32px;border:none;background:var(--bg);border-radius:7px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--txm);position:relative;transition:all .2s;flex-shrink:0;font-size:12px}
.hbt:hover{background:var(--P);color:#fff}
.bdg{position:absolute;top:-3px;right:-3px;background:var(--ER);color:#fff;font-size:8px;min-width:15px;height:15px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700}
.srch{flex:1;max-width:450px;display:flex;align-items:center;gap:6px;background:var(--inp);border:1.5px solid var(--bdr);border-radius:7px;padding:0 11px}
.srch:focus-within{border-color:var(--P)}
.srch i{color:var(--txm);font-size:11px}
.srch input{flex:1;border:none;background:none;outline:none;padding:8px 0;color:var(--tx);font-size:12px}
.srch input::placeholder{color:var(--txm)}
.hdrt{margin-left:auto;display:flex;align-items:center;gap:6px}
.ava{width:30px;height:30px;border-radius:7px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11px;cursor:pointer}
.ctn{flex:1;overflow-y:auto;padding:18px 20px}
.pg{display:none;flex-direction:column;gap:14px;min-height:100%}
.pg.on{display:flex}
.pgh{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:4px}
.pgh h1{font-size:18px;font-weight:800;margin-bottom:2px}
.pgh p{color:var(--txm);font-size:11px}
.pghrt{display:flex;gap:6px}
.btn{display:inline-flex;align-items:center;gap:5px;padding:8px 15px;border:none;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap}
.bp{background:linear-gradient(135deg,var(--P),var(--PH));color:#fff}
.bp:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(79,70,229,.3)}
.bg{background:var(--bg);color:var(--tx)}.bg:hover{background:var(--bdr)}
.bok{background:var(--OK);color:#fff}
.bsm{padding:5px 10px;font-size:11px}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.sc{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);padding:14px;display:flex;align-items:center;gap:10px;transition:all .2s}
.sc:hover{transform:translateY(-2px);box-shadow:var(--sh)}
.sic{width:36px;height:36px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:15px}
.sib{background:rgba(79,70,229,.1);color:var(--P)}.sig{background:rgba(34,197,94,.1);color:var(--OK)}.sio{background:rgba(245,158,11,.1);color:var(--WA)}.sir{background:rgba(239,68,68,.1);color:var(--ER)}.sii{background:rgba(6,182,212,.1);color:#06b6d4}
.scv{font-size:22px;font-weight:800;line-height:1}
.scl{color:var(--txm);font-size:10px;margin-top:2px}
.dgrd{display:grid;grid-template-columns:1fr 255px;gap:12px;flex:1;min-height:0}
@media(max-width:1000px){.dgrd{grid-template-columns:1fr}.dps{display:none!important}}
.crd{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);overflow:hidden;display:flex;flex-direction:column}
.crdh{padding:10px 14px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;gap:6px;flex-shrink:0}
.crdh h2{font-size:13px;font-weight:700}
.crdb{padding:12px;flex:1;overflow-y:auto}
.flt{display:flex;gap:5px;flex-wrap:wrap}
.flt select{padding:5px 8px;border:1px solid var(--bdr);border-radius:5px;background:var(--inp);color:var(--tx);font-size:10px;cursor:pointer;outline:none}
.flt select:focus{border-color:var(--P)}
.tl{overflow-y:auto;flex:1}
.tr{display:flex;align-items:flex-start;gap:10px;padding:11px 14px;border-bottom:1px solid var(--bdr);transition:background .15s;cursor:pointer}
.tr:last-child{border-bottom:none}
.tr:hover{background:var(--bg)}
.tr.dn{opacity:.5}
.tr.ovr{border-left:3px solid var(--ER)}
.tr.pnd{border-left:3px solid var(--WA)}
.ck{width:18px;height:18px;border:2px solid var(--bdr);border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer;margin-top:2px;transition:all .2s}
.ck:hover{border-color:var(--P)}
.ck.dn{background:var(--OK);border-color:var(--OK);color:#fff}
.tif{flex:1;min-width:0}
.tnm{font-weight:600;font-size:12px;margin-bottom:3px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.tr.dn .tnm{text-decoration:line-through;color:var(--txm)}
.tds{font-size:10px;color:var(--txm);margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tmt{display:flex;gap:8px;flex-wrap:wrap;font-size:9px;color:var(--txm)}
.tmt i{margin-right:2px}
.ovtx{color:var(--ER)!important;font-weight:700}
.tg{padding:1px 6px;background:var(--bg);border-radius:20px;font-size:8px;color:var(--txm);margin-top:3px;margin-right:2px;display:inline-flex}
.prb{padding:1px 5px;border-radius:3px;font-size:8px;font-weight:700;text-transform:uppercase}
.prh{background:rgba(239,68,68,.1);color:var(--ER)}.prm{background:rgba(245,158,11,.1);color:var(--WA)}.prl{background:rgba(34,197,94,.1);color:var(--OK)}
.stb{padding:1px 7px;border-radius:20px;font-size:8px;font-weight:600}
.stp{background:rgba(245,158,11,.1);color:var(--WA)}.sti{background:rgba(79,70,229,.1);color:var(--P)}.stc{background:rgba(34,197,94,.1);color:var(--OK)}
.tac{display:flex;gap:3px;flex-shrink:0;opacity:0;transition:opacity .2s}
.tr:hover .tac{opacity:1}
.abt{width:24px;height:24px;border:none;border-radius:4px;background:var(--bg);cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;font-size:10px;transition:all .2s}
.abt:hover{background:var(--P);color:#fff}
.abt.dl:hover{background:var(--ER);color:#fff}
.emp{padding:35px 18px;text-align:center;color:var(--txm)}
.emp i{font-size:38px;margin-bottom:10px;opacity:.3;display:block}
.emp h3{font-size:14px;margin-bottom:5px;color:var(--tx)}
.emp p{font-size:11px;margin-bottom:12px}
.rngw{display:flex;align-items:center;justify-content:center;gap:14px;padding:8px 0}
.rngc{position:relative;width:70px;height:70px}
.rngc svg{transform:rotate(-90deg)}
.rngm{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}
.rngp{font-size:14px;font-weight:800}
.rngl{font-size:8px;color:var(--txm)}
.rngs{display:flex;flex-direction:column;gap:4px}
.rngr{display:flex;align-items:center;gap:5px;font-size:10px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.cpit{display:flex;align-items:center;gap:6px;padding:5px 7px;border-radius:5px;cursor:pointer;transition:background .15s}
.cpit:hover{background:var(--bg)}
.cpdt{width:7px;height:7px;border-radius:50%}
.cpnm{flex:1;font-size:10px}
.cpcnt{font-size:9px;color:var(--txm);background:var(--bg);padding:0 5px;border-radius:7px}
.ndp{position:fixed;top:calc(var(--hh)+3px);right:10px;width:310px;background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);box-shadow:var(--sh);z-index:999;opacity:0;pointer-events:none;transform:translateY(8px);transition:all .25s}
.ndp.on{opacity:1;pointer-events:all;transform:translateY(0)}
.ndph{padding:10px 12px;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.ndph h3{font-size:12px;font-weight:700}
.ndpa{display:flex;gap:5px}
.ndpl{font-size:9px;color:var(--P);cursor:pointer;background:none;border:none}
.ndpl:hover{text-decoration:underline}
.ndpl.er{color:var(--ER)}
.ndps{max-height:330px;overflow-y:auto}
.ndpi{display:flex;gap:9px;padding:10px 12px;border-bottom:1px solid var(--bdr);cursor:pointer;transition:background .15s}
.ndpi:last-child{border-bottom:none}
.ndpi:hover{background:var(--bg)}
.ndpi.ur{background:rgba(79,70,229,.04)}
.ndpi.hp{border-left:3px solid var(--ER)}
.ndpi.mp{border-left:3px solid var(--WA)}
.ndi{width:30px;height:30px;border-radius:6px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px}
.ndi.overdue,.ndi.upcoming_high{background:rgba(239,68,68,.1);color:var(--ER)}
.ndi.due_today{background:rgba(245,158,11,.1);color:var(--WA)}
.ndi.reminder{background:rgba(79,70,229,.1);color:var(--P)}
.ndi.created{background:rgba(34,197,94,.1);color:var(--OK)}
.nditx{flex:1;min-width:0}
.ndim{font-size:11px;margin-bottom:2px;line-height:1.3}
.ndit{font-size:8px;color:var(--txm)}
.ndpe{padding:25px;text-align:center;color:var(--txm);font-size:11px}
.mdov{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:600;opacity:0;pointer-events:none;transition:all .25s}
.mdov.on{opacity:1;pointer-events:all}
.mdl{background:var(--card);border-radius:14px;width:92%;max-width:520px;max-height:90vh;display:flex;flex-direction:column;transform:scale(.94);transition:all .25s}
.mdov.on .mdl{transform:scale(1)}
.mdlh{padding:14px 18px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.mdlh h2{font-size:15px;font-weight:700}
.mdlc{width:28px;height:28px;border:none;background:var(--bg);border-radius:5px;cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;transition:all .2s}
.mdlc:hover{background:var(--ER);color:#fff}
.mdlb{padding:18px;overflow-y:auto;flex:1}
.mdlf{padding:10px 18px;border-top:1px solid var(--bdr);display:flex;justify-content:flex-end;gap:7px;flex-shrink:0}
.fg{margin-bottom:12px}
.fl{display:block;font-size:10px;font-weight:700;margin-bottom:4px}
.fl span{color:var(--ER)}
.fi,.fs,.fta{width:100%;padding:8px 11px;border:1.5px solid var(--bdr);border-radius:6px;background:var(--inp);color:var(--tx);font-size:12px;outline:none;transition:border-color .2s}
.fi:focus,.fs:focus,.fta:focus{border-color:var(--P)}
.fta{min-height:60px;resize:vertical}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:480px){.frow{grid-template-columns:1fr}}
.tstwrap{position:fixed;top:12px;right:12px;display:flex;flex-direction:column;gap:5px;z-index:2000}
.tst{display:flex;align-items:center;gap:9px;background:var(--card);border-radius:8px;padding:11px 14px;box-shadow:var(--sh);min-width:230px;border-left:4px solid var(--P);animation:tsin .25s ease}
.tst.ok{border-left-color:var(--OK)}.tst.er{border-left-color:var(--ER)}.tst.wa{border-left-color:var(--WA)}
.tsti{font-size:14px}.tst.ok .tsti{color:var(--OK)}.tst.er .tsti{color:var(--ER)}.tst.wa .tsti{color:var(--WA)}
.tstm{flex:1;font-size:12px}
.tstc{background:none;border:none;cursor:pointer;color:var(--txm);font-size:13px}
@keyframes tsin{from{opacity:0;transform:translateX(50px)}to{opacity:1;transform:translateX(0)}}
.alp{position:fixed;bottom:20px;right:20px;width:305px;background:var(--card);border-radius:11px;box-shadow:0 10px 35px rgba(0,0,0,.18);border:1px solid var(--bdr);z-index:3000;overflow:hidden;transform:translateY(120%);transition:transform .4s cubic-bezier(.34,1.56,.64,1)}
.alp.on{transform:translateY(0)}
.alps{height:4px;width:100%}
.alps.high{background:linear-gradient(90deg,var(--ER),#ff8a80)}.alps.medium{background:linear-gradient(90deg,var(--WA),#ffe57f)}.alps.low{background:linear-gradient(90deg,var(--OK),#69f0ae)}.alps.created{background:linear-gradient(90deg,var(--P),var(--PL))}
.alpb{padding:12px 14px;display:flex;gap:10px;align-items:flex-start}
.alpi{width:36px;height:36px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:16px}
.alpi.high{background:rgba(239,68,68,.12);color:var(--ER)}.alpi.medium{background:rgba(245,158,11,.12);color:var(--WA)}.alpi.low{background:rgba(34,197,94,.12);color:var(--OK)}.alpi.created{background:rgba(79,70,229,.12);color:var(--P)}
.alpt{flex:1;min-width:0}
.alptt{font-size:11px;font-weight:700;margin-bottom:2px}
.alpmg{font-size:10px;color:var(--txm);line-height:1.4}
.alppr{display:inline-flex;padding:1px 7px;border-radius:20px;font-size:8px;font-weight:700;text-transform:uppercase;margin-top:4px}
.alppr.high{background:rgba(239,68,68,.1);color:var(--ER)}.alppr.medium{background:rgba(245,158,11,.1);color:var(--WA)}.alppr.low{background:rgba(34,197,94,.1);color:var(--OK)}
.alpcl{width:22px;height:22px;border:none;background:var(--bg);border-radius:4px;cursor:pointer;color:var(--txm);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:10px;transition:all .2s}
.alpcl:hover{background:var(--ER);color:#fff}
.alppg{height:2px;background:var(--bdr)}
.alpbar{height:100%;background:var(--P);width:100%}
.alpft{padding:7px 14px;border-top:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.alptm{font-size:8px;color:var(--txm)}
.alpac{display:flex;gap:5px}
.alpbtn{font-size:9px;cursor:pointer;font-weight:600;background:none;border:none;padding:3px 8px;border-radius:4px;transition:all .2s}
.alpbtn.snz{background:var(--bg);color:var(--tx)}.alpbtn.snz:hover{background:var(--bdr)}
.alpbtn.dm{color:var(--P)}.alpbtn.dm:hover{text-decoration:underline}
.setsc{margin-bottom:18px}
.setsc h3{font-size:13px;font-weight:700;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--bdr)}
.setr{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--bdr)}
.setr:last-child{border-bottom:none}
.seti h4{font-size:12px;margin-bottom:1px}
.seti p{font-size:9px;color:var(--txm)}
.tgl{position:relative;width:40px;height:22px;flex-shrink:0}
.tgl input{opacity:0;width:0;height:0}
.tgls{position:absolute;cursor:pointer;inset:0;background:var(--bdr);border-radius:22px;transition:all .25s}
.tgls::before{position:absolute;content:"";width:16px;height:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:all .25s}
.tgl input:checked+.tgls{background:var(--P)}
.tgl input:checked+.tgls::before{transform:translateX(18px)}
@keyframes shrink{from{width:100%}to{width:0%}}
@media(max-width:768px){.sb{position:fixed;left:-100%;transition:left .3s;z-index:200}.sb.mob{left:0}.ctn{padding:10px}}
</style>
</head>
<body>
<div class="app">
<aside class="sb" id="sb">
<div class="sbb"><div class="sbl"><i class="fas fa-layer-group"></i></div><span class="sbn">TaskPro</span></div>
<nav class="sbnav">
<div class="nss"><div class="nsl">MAIN</div>
<button class="nbt on" data-p="db" onclick="go('db',this)"><i class="fas fa-th-large"></i><span class="nt">Dashboard</span></button>
<button class="nbt" data-p="all" onclick="go('all',this)"><i class="fas fa-list-check"></i><span class="nt">All Tasks</span><span class="nc" id="nc-all">0</span></button>
<button class="nbt" data-p="td" onclick="go('td',this)"><i class="fas fa-calendar-day"></i><span class="nt">Due Today</span><span class="nc" id="nc-td">0</span></button>
<button class="nbt" data-p="ov" onclick="go('ov',this)"><i class="fas fa-exclamation-circle"></i><span class="nt">Overdue</span><span class="nc" id="nc-ov" style="background:var(--ER);color:#fff">0</span></button>
<button class="nbt" data-p="cm" onclick="go('cm',this)"><i class="fas fa-check-double"></i><span class="nt">Completed</span></button>
</div>
<div class="nss"><div class="nsl">CATEGORIES</div><div id="sbC"></div>
<button class="nbt" onclick="openCM()"><i class="fas fa-plus"></i><span class="nt">New Category</span></button></div>
</nav>
</aside>
<div class="rt">
<header class="hd">
<button class="hbt" onclick="toggleSB()"><i class="fas fa-bars"></i></button>
<div class="srch"><i class="fas fa-search"></i><input id="si" placeholder="Search..." oninput="onSrch()"></div>
<div class="hdrt">
<button class="hbt" onclick="toggleThm()"><i class="fas fa-moon" id="thmI"></i></button>
<button class="hbt" id="bellBtn" onclick="toggleND()"><i class="fas fa-bell"></i><span class="bdg" id="nBdg" style="display:none">0</span></button>
<button class="hbt" onclick="openSM()"><i class="fas fa-cog"></i></button>
<div class="ava">JD</div>
</div>
</header>
<div class="ndp" id="ndp">
<div class="ndph"><h3>Notifications</h3><div class="ndpa"><button class="ndpl" onclick="markAll()">Read all</button><button class="ndpl er" onclick="clearRd()">Clear</button></div></div>
<div class="ndps" id="ndps"></div>
</div>
<div class="ctn">
<div class="pg on" id="pg-db">
<div class="pgh"><div><h1 id="grt">Hello!</h1><p>Your task overview</p></div>
<div class="pghrt"><button class="btn bg" onclick="loadAll()"><i class="fas fa-sync"></i></button>
<button class="btn bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div></div>
<div class="sg">
<div class="sc"><div class="sic sib"><i class="fas fa-tasks"></i></div><div><div class="scv" id="s-t">0</div><div class="scl">Total</div></div></div>
<div class="sc"><div class="sic sig"><i class="fas fa-check-circle"></i></div><div><div class="scv" id="s-d">0</div><div class="scl">Done</div></div></div>
<div class="sc"><div class="sic sio"><i class="fas fa-spinner"></i></div><div><div class="scv" id="s-p">0</div><div class="scl">Progress</div></div></div>
<div class="sc"><div class="sic sir"><i class="fas fa-exclamation-triangle"></i></div><div><div class="scv" id="s-o">0</div><div class="scl">Overdue</div></div></div>
<div class="sc"><div class="sic sii"><i class="fas fa-calendar-check"></i></div><div><div class="scv" id="s-td">0</div><div class="scl">Due Today</div></div></div>
</div>
<div class="dgrd" style="flex:1;min-height:0">
<div class="crd" style="min-height:0">
<div class="crdh"><h2>Tasks</h2><div class="flt">
<select id="d-st" onchange="rDB()"><option value="">All</option><option value="pending">Pending</option><option value="in_progress">Progress</option><option value="completed">Done</option></select>
<select id="d-pr" onchange="rDB()"><option value="">Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
</div></div><div class="tl" id="dbL"></div></div>
<div class="dps" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto">
<div class="crd"><div class="crdh"><h2>Progress</h2></div><div class="crdb">
<div class="rngw"><div class="rngc"><svg width="70" height="70" viewBox="0 0 70 70"><circle cx="35" cy="35" r="29" fill="none" stroke="var(--bdr)" stroke-width="7"/><circle id="rngC" cx="35" cy="35" r="29" fill="none" stroke="var(--P)" stroke-width="7" stroke-linecap="round" stroke-dasharray="182" stroke-dashoffset="182" style="transition:stroke-dashoffset .6s"/></svg>
<div class="rngm"><div class="rngp" id="rPct">0%</div><div class="rngl">done</div></div></div>
<div class="rngs"><div class="rngr"><span class="dot" style="background:var(--OK)"></span>Done:<b id="rD">0</b></div>
<div class="rngr"><span class="dot" style="background:var(--WA)"></span>Pending:<b id="rPn">0</b></div>
<div class="rngr"><span class="dot" style="background:var(--ER)"></span>Overdue:<b id="rO">0</b></div></div></div></div></div>
<div class="crd"><div class="crdh"><h2>Categories</h2></div><div class="crdb" style="padding:6px 8px"><div id="cpnl"></div></div></div>
</div></div></div>
<div class="pg" id="pg-all"><div class="pgh"><div><h1>All Tasks</h1></div><div class="pghrt"><button class="btn bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div></div>
<div class="crd" style="flex:1"><div class="crdh"><div class="flt">
<select id="a-st" onchange="rAll()"><option value="">All</option><option value="pending">Pending</option><option value="in_progress">Progress</option><option value="completed">Done</option></select>
<select id="a-pr" onchange="rAll()"><option value="">Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
<select id="a-ca" onchange="rAll()"><option value="">Category</option></select>
</div></div><div class="tl" id="allL" style="flex:1"></div></div></div>
<div class="pg" id="pg-td"><div class="pgh"><div><h1>Due Today</h1></div><div class="pghrt"><button class="btn bp" onclick="openTM()"><i class="fas fa-plus"></i></button></div></div><div class="crd" style="flex:1"><div class="tl" id="tdL" style="flex:1"></div></div></div>
<div class="pg" id="pg-ov"><div class="pgh"><div><h1>Overdue</h1></div></div><div class="crd" style="flex:1"><div class="tl" id="ovL" style="flex:1"></div></div></div>
<div class="pg" id="pg-cm"><div class="pgh"><div><h1>Completed</h1></div></div><div class="crd" style="flex:1"><div class="tl" id="cmL" style="flex:1"></div></div></div>
</div></div></div>
<div class="alp" id="alp"><div class="alps" id="alps"></div><div class="alpb"><div class="alpi" id="alpi"><i class="fas fa-bell" id="alpii"></i></div><div class="alpt"><div class="alptt" id="alptt">Alert</div><div class="alpmg" id="alpmg">Update</div><div class="alppr" id="alppr">MED</div></div><button class="alpcl" onclick="closeAP()"><i class="fas fa-times"></i></button></div><div class="alppg"><div class="alpbar" id="alpbar"></div></div><div class="alpft"><span class="alptm" id="alptm">Now</span><div class="alpac"><button class="alpbtn snz" onclick="closeAP()">Snooze</button><button class="alpbtn dm" onclick="closeAP()">Dismiss</button></div></div></div>
<div class="mdov" id="tMd"><div class="mdl"><div class="mdlh"><h2 id="mTi">New Task</h2><button class="mdlc" onclick="closeTM()"><i class="fas fa-times"></i></button></div><div class="mdlb"><input type="hidden" id="fid">
<div class="fg"><label class="fl">Title <span>*</span></label><input class="fi" id="ftit"></div>
<div class="fg"><label class="fl">Description</label><textarea class="fta" id="fdsc"></textarea></div>
<div class="frow"><div class="fg"><label class="fl">Category</label><select class="fs" id="fcat"></select></div><div class="fg"><label class="fl">Priority</label><select class="fs" id="fpri"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></div></div>
<div class="frow"><div class="fg"><label class="fl">Due Date</label><input type="date" class="fi" id="fdt"></div><div class="fg"><label class="fl">Due Time</label><input type="time" class="fi" id="ftm"></div></div>
<div class="frow"><div class="fg"><label class="fl">Status</label><select class="fs" id="fst"><option value="pending">Pending</option><option value="in_progress">In Progress</option><option value="completed">Done</option></select></div><div class="fg"><label class="fl">Reminder</label><select class="fs" id="frm"><option value="5">5m</option><option value="10">10m</option><option value="15">15m</option><option value="30" selected>30m</option><option value="60">1h</option><option value="1440">1d</option></select></div></div>
<div class="fg"><label class="fl">Assigned To</label><input class="fi" id="fasn"></div>
<div class="fg"><label class="fl">Tags</label><input class="fi" id="ftgs" placeholder="comma separated"></div>
<div class="fg"><label class="fl">Notes</label><textarea class="fta" id="fnts"></textarea></div>
</div><div class="mdlf"><button class="btn bg" onclick="closeTM()">Cancel</button><button class="btn bp" onclick="saveT()"><i class="fas fa-save"></i> Save</button></div></div></div>
<div class="mdov" id="cMd"><div class="mdl" style="max-width:310px"><div class="mdlh"><h2>New Category</h2><button class="mdlc" onclick="closeCM()"><i class="fas fa-times"></i></button></div><div class="mdlb"><div class="fg"><label class="fl">Name</label><input class="fi" id="cnm"></div><div class="fg"><label class="fl">Color</label><input type="color" class="fi" id="ccl" value="#4f46e5" style="height:36px;padding:3px"></div></div><div class="mdlf"><button class="btn bg" onclick="closeCM()">Cancel</button><button class="btn bp" onclick="saveC()">Save</button></div></div></div>
<div class="mdov" id="sMd"><div class="mdl" style="max-width:450px"><div class="mdlh"><h2>Settings</h2><button class="mdlc" onclick="closeSM()"><i class="fas fa-times"></i></button></div><div class="mdlb">
<div class="setsc"><h3>Notifications</h3>
<div class="setr"><div class="seti"><h4>Sound Alerts</h4><p>Play chime on notification</p></div><label class="tgl"><input type="checkbox" id="ss" checked onchange="saveSt()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Popup Alerts</h4><p>Show popup window</p></div><label class="tgl"><input type="checkbox" id="sp" checked onchange="saveSt()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Browser Notifications</h4><p>OS-level alerts</p></div><label class="tgl"><input type="checkbox" id="sb2" checked onchange="saveSt()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Poll Interval</h4><p>Check every...</p></div><select class="fs" id="sint" style="width:80px" onchange="saveSt()"><option value="15">15s</option><option value="30">30s</option><option value="60">60s</option></select></div>
</div>
<div class="setsc"><h3>Default Reminders by Priority</h3>
<div class="setr"><div class="seti"><h4>High Priority</h4></div><select class="fs" id="srh" style="width:90px" onchange="saveSt()"><option value="5">5 min</option><option value="10">10 min</option><option value="15">15 min</option><option value="30">30 min</option></select></div>
<div class="setr"><div class="seti"><h4>Medium Priority</h4></div><select class="fs" id="srm" style="width:90px" onchange="saveSt()"><option value="15">15 min</option><option value="30">30 min</option><option value="60">1 hour</option></select></div>
<div class="setr"><div class="seti"><h4>Low Priority</h4></div><select class="fs" id="srl" style="width:90px" onchange="saveSt()"><option value="30">30 min</option><option value="60">1 hour</option><option value="120">2 hours</option></select></div>
</div>
<div class="setsc"><h3>Popup Duration by Priority</h3>
<div class="setr"><div class="seti"><h4>High</h4></div><select class="fs" id="sdh" style="width:80px" onchange="saveSt()"><option value="10">10s</option><option value="12">12s</option><option value="15">15s</option></select></div>
<div class="setr"><div class="seti"><h4>Medium</h4></div><select class="fs" id="sdm" style="width:80px" onchange="saveSt()"><option value="5">5s</option><option value="8">8s</option><option value="10">10s</option></select></div>
<div class="setr"><div class="seti"><h4>Low</h4></div><select class="fs" id="sdl" style="width:80px" onchange="saveSt()"><option value="3">3s</option><option value="5">5s</option><option value="8">8s</option></select></div>
</div>
</div><div class="mdlf"><button class="btn bp" onclick="closeSM()">Done</button></div></div></div>
<div class="tstwrap" id="tw"></div>
<script>
var AP='/api';
var T=[],C=[],ST={},NF=[],SE={};
var pg='db',kN={},aQ=[],aSh=false,aT=null,pT=null,aTid=null;
document.addEventListener('DOMContentLoaded',function(){setGrt();loadThm();loadAll();
if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();});
function loadAll(){Promise.all([fT(),fC(),fS(),fN(),fSE()]).then(function(){render();rSB();});}
function G(i){return document.getElementById(i);}
function SV(i,v){var e=G(i);if(e)e.value=v;}
function TV(i,v){var e=G(i);if(e)e.textContent=v;}
function api(p,m,b){m=m||'GET';var o={method:m,headers:{'Content-Type':'application/json'}};
if(b)o.body=JSON.stringify(b);return fetch(AP+p,o).then(function(r){return r.json();}).catch(function(e){console.error(e);toast('Error','er');return null;});}
function fT(){return api('/tasks?sort=created_at&order=desc').then(function(r){T=r||[];});}
function fC(){return api('/categories').then(function(r){C=r||[];});}
function fS(){return api('/statistics').then(function(r){ST=r||{};});}
function fN(){return api('/notifications').then(function(r){NF=r||[];updBdg();rNL();});}
function fSE(){return api('/settings').then(function(r){SE=r||{};
G('ss').checked=SE.sound_enabled!==0;G('sp').checked=SE.popup_enabled!==0;G('sb2').checked=SE.browser_notif_enabled!==0;
SV('sint',SE.check_interval_secs||30);SV('srh',SE.default_reminder_high||15);SV('srm',SE.default_reminder_medium||30);SV('srl',SE.default_reminder_low||60);
SV('sdh',SE.popup_duration_high||12);SV('sdm',SE.popup_duration_medium||8);SV('sdl',SE.popup_duration_low||5);startPoll();});}
function saveSt(){var d={sound_enabled:G('ss').checked?1:0,popup_enabled:G('sp').checked?1:0,browser_notif_enabled:G('sb2').checked?1:0,
check_interval_secs:parseInt(G('sint').value),default_reminder_high:parseInt(G('srh').value),default_reminder_medium:parseInt(G('srm').value),default_reminder_low:parseInt(G('srl').value),
popup_duration_high:parseInt(G('sdh').value),popup_duration_medium:parseInt(G('sdm').value),popup_duration_low:parseInt(G('sdl').value)};
api('/settings','PUT',d).then(function(r){SE=r||SE;startPoll();toast('Saved','ok');});}
function startPoll(){if(pT)clearInterval(pT);pT=setInterval(pollN,(SE.check_interval_secs||30)*1000);}
function pollN(){api('/notifications/new').then(function(nw){if(!nw)return;
var fr=nw.filter(function(n){return!kN[n.id];});fr.forEach(function(n){kN[n.id]=true;aQ.push(n);});
if(fr.length>0){fN().then(function(){processQ();});}});}
function processQ(){if(aSh||aQ.length===0)return;var n=aQ.shift();var pr=n.priority||'medium';if(SE.popup_enabled!==0)showAP(n,pr);}
function showAP(n,pr){aSh=true;clearTimeout(aT);aTid=n.task_id||null;
var cfs={overdue:{t:'OVERDUE',i:'fa-exclamation-circle'},due_today:{t:'Due Today',i:'fa-calendar-check'},reminder:{t:'Reminder',i:'fa-bell'},upcoming_high:{t:'Tomorrow',i:'fa-fire'},created:{t:'Created',i:'fa-check-circle'}};
var cf=cfs[n.type]||{t:'Alert',i:'fa-bell'};var ic=n.type==='created'?'created':pr;
G('alps').className='alps '+ic;G('alpi').className='alpi '+ic;G('alpii').className='fas '+cf.i;
G('alptt').textContent=cf.t;G('alpmg').textContent=n.message||'Update';
G('alppr').className='alppr '+pr;G('alppr').textContent=pr.toUpperCase();G('alptm').textContent=tAgo(n.created_at);
var du={high:SE.popup_duration_high||12,medium:SE.popup_duration_medium||8,low:SE.popup_duration_low||5};var d=du[pr]||8;
var bar=G('alpbar');bar.style.animation='none';bar.offsetHeight;bar.style.animation=d>0?'shrink '+d+'s linear forwards':'none';
G('alp').classList.add('on');if(SE.sound_enabled!==0)playSnd(pr);
if(SE.browser_notif_enabled!==0&&'Notification'in window&&Notification.permission==='granted')new Notification('TaskPro: '+cf.t,{body:n.message||''});
if(d>0)aT=setTimeout(function(){closeAP();setTimeout(processQ,400);},d*1000);}
function closeAP(){G('alp').classList.remove('on');clearTimeout(aT);aTid=null;setTimeout(function(){aSh=false;processQ();},350);}
var axCtx;
function playSnd(pr){try{if(!axCtx)axCtx=new(window.AudioContext||window.webkitAudioContext)();
var ns={high:[[523,0],[659,.12],[784,.24],[1047,.36]],medium:[[523,0],[659,.15],[784,.3]],low:[[523,0],[659,.2]]};
(ns[pr]||ns.medium).forEach(function(p){var o=axCtx.createOscillator(),g=axCtx.createGain();o.connect(g);g.connect(axCtx.destination);
o.type=pr==='high'?'triangle':'sine';o.frequency.value=p[0];var t=axCtx.currentTime+p[1];
g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.15,t+.04);g.gain.exponentialRampToValueAtTime(.001,t+.4);o.start(t);o.stop(t+.5);});}catch(e){}}
function todStr(){return new Date().toISOString().split('T')[0];}
function isOv(t){return t.due_date&&t.due_date<todStr()&&t.status!=='completed';}
function fmtD(s){if(!s)return'';return new Date(s+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'});}
function tAgo(s){if(!s)return'';var d=Math.floor((Date.now()-new Date(s))/1000);if(d<60)return'Now';if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'h';return Math.floor(d/86400)+'d';}
function pTg(t){try{return JSON.parse(t||'[]');}catch(e){return[];}}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fillSl(id,items,ph){var el=G(id);if(!el)return;var cv=el.value;var h=ph?'<option value="">'+ph+'</option>':'';
items.forEach(function(i){h+='<option value="'+esc(i.v)+'">'+esc(i.l)+'</option>';});el.innerHTML=h;if(cv)el.value=cv;}
function tRow(t){var ov=isOv(t);var tgs=pTg(t.tags).map(function(g){return'<span class="tg">#'+esc(g)+'</span>';}).join('');
var pc={high:'prh',medium:'prm',low:'prl'}[t.priority]||'prm';var sc={pending:'stp',in_progress:'sti',completed:'stc'}[t.status]||'stp';
var rc=(t.status==='completed'?' dn':'')+(ov?' ovr':'');var ck=t.status==='completed'?'dn':'';
var ci=t.status==='completed'?'<i class="fas fa-check" style="font-size:8px"></i>':'';
var h='<div class="tr'+rc+'">';
h+='<div class="ck '+ck+'" onclick="togSt('+t.id+',event)">'+ci+'</div>';
h+='<div class="tif" onclick="edT('+t.id+')">';
h+='<div class="tnm">'+esc(t.title)+' <span class="prb '+pc+'">'+t.priority+'</span> <span class="stb '+sc+'">'+t.status.replace(/_/g,' ')+'</span></div>';
if(t.description)h+='<div class="tds">'+esc(t.description)+'</div>';
h+='<div class="tmt">';
if(t.due_date){h+='<span class="'+(ov?'ovtx':'')+'"><i class="fas fa-calendar"></i>'+fmtD(t.due_date);if(t.due_time)h+=' '+t.due_time;if(ov)h+=' !!';h+='</span>';}
h+='<span><i class="fas fa-folder"></i>'+esc(t.category)+'</span>';
if(t.assigned_to)h+='<span><i class="fas fa-user"></i>'+esc(t.assigned_to)+'</span>';
h+='<span><i class="fas fa-bell"></i>'+(t.reminder_mins||30)+'m</span></div>';
if(tgs)h+='<div style="margin-top:3px">'+tgs+'</div>';
h+='</div><div class="tac"><button class="abt" onclick="edT('+t.id+')"><i class="fas fa-pen"></i></button><button class="abt dl" onclick="dlT('+t.id+',event)"><i class="fas fa-trash"></i></button></div></div>';
return h;}
function empSt(m){return'<div class="emp"><i class="fas fa-clipboard-list"></i><h3>'+(m||'No tasks')+'</h3><button class="btn bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div>';}
function setL(id,l){var e=G(id);if(!e)return;e.innerHTML=l&&l.length?l.map(tRow).join(''):empSt();}
function render(){updSt();updRng();updBdg();updCnts();switch(pg){case'db':rDB();break;case'all':rAll();break;case'td':rTd();break;case'ov':rOv();break;case'cm':rCm();break;}}
function rDB(){var s=G('d-st')?G('d-st').value:'';var p=G('d-pr')?G('d-pr').value:'';var l=T.slice();
if(s)l=l.filter(function(t){return t.status===s;});if(p)l=l.filter(function(t){return t.priority===p;});setL('dbL',l.slice(0,30));}
function rAll(){var s=G('a-st')?G('a-st').value:'';var p=G('a-pr')?G('a-pr').value:'';var c=G('a-ca')?G('a-ca').value:'';var q=G('si')?G('si').value.toLowerCase():'';var l=T.slice();
if(s)l=l.filter(function(t){return t.status===s;});if(p)l=l.filter(function(t){return t.priority===p;});if(c)l=l.filter(function(t){return t.category===c;});
if(q)l=l.filter(function(t){return(t.title+' '+(t.description||'')).toLowerCase().indexOf(q)!==-1;});setL('allL',l);}
function rTd(){var d=todStr();var l=T.filter(function(t){return t.due_date===d&&t.status!=='completed';});var e=G('tdL');if(e)e.innerHTML=l.length?l.map(tRow).join(''):empSt('Nothing today!');}
function rOv(){var l=T.filter(function(t){return isOv(t);});var e=G('ovL');if(e)e.innerHTML=l.length?l.map(tRow).join(''):empSt('All caught up!');}
function rCm(){var l=T.filter(function(t){return t.status==='completed';});l.sort(function(a,b){return(b.completed_at||'').localeCompare(a.completed_at||'');});setL('cmL',l);}
function updSt(){TV('s-t',ST.total||0);TV('s-d',ST.completed||0);TV('s-p',ST.in_progress||0);TV('s-o',ST.overdue||0);TV('s-td',ST.due_today||0);}
function updRng(){var t=ST.total||0;var c=ST.completed||0;var p=t>0?Math.round(c/t*100):0;TV('rPct',p+'%');TV('rD',c);TV('rPn',ST.pending||0);TV('rO',ST.overdue||0);var r=G('rngC');if(r)r.style.strokeDashoffset=182-(p/100)*182;}
function updCnts(){var d=todStr();TV('nc-all',T.filter(function(t){return t.status!=='completed';}).length);TV('nc-td',T.filter(function(t){return t.due_date===d&&t.status!=='completed';}).length);TV('nc-ov',T.filter(function(t){return isOv(t);}).length);}
function updBdg(){var u=NF.filter(function(n){return!n.is_read;}).length;G('nBdg').textContent=u;G('nBdg').style.display=u>0?'flex':'none';}
function rNL(){var e=G('ndps');if(!NF||NF.length===0){e.innerHTML='<div class="ndpe">No notifications</div>';return;}
var h='';NF.slice(0,30).forEach(function(n){var pc=n.priority==='high'?'hp':n.priority==='medium'?'mp':'';var ic=n.type==='overdue'||n.type==='upcoming_high'?'fa-exclamation-circle':n.type==='due_today'?'fa-calendar-check':'fa-bell';
h+='<div class="ndpi '+(n.is_read?'':'ur')+' '+pc+'" onclick="rdN('+n.id+')">';
h+='<div class="ndi '+n.type+'"><i class="fas '+ic+'"></i></div>';
h+='<div class="nditx"><div class="ndim">'+esc(n.message)+'</div><div class="ndit">'+tAgo(n.created_at)+'</div></div></div>';});e.innerHTML=h;}
function rSB(){var ce=G('sbC');if(ce){var h='';C.forEach(function(c){var cnt=T.filter(function(t){return t.category===c.name&&t.status!=='completed';}).length;
h+='<button class="nbt" onclick="fCat(\''+esc(c.name)+'\')"><span style="width:8px;height:8px;border-radius:50%;background:'+c.color+';display:inline-block;flex-shrink:0"></span><span class="nt">'+esc(c.name)+'</span><span class="nc">'+cnt+'</span></button>';});ce.innerHTML=h;}
var cp=G('cpnl');if(cp){var h2='';C.forEach(function(c){var cnt=T.filter(function(t){return t.category===c.name&&t.status!=='completed';}).length;
h2+='<div class="cpit" onclick="fCat(\''+esc(c.name)+'\')"><span class="cpdt" style="background:'+c.color+'"></span><span class="cpnm">'+esc(c.name)+'</span><span class="cpcnt">'+cnt+'</span></div>';});cp.innerHTML=h2;}
fillSl('a-ca',C.map(function(c){return{v:c.name,l:c.name};}),'All Categories');fillSl('fcat',C.map(function(c){return{v:c.name,l:c.name};}));}
function toggleND(){G('ndp').classList.toggle('on');}
function rdN(id){api('/notifications/'+id+'/read','PUT').then(fN);}
function markAll(){api('/notifications/read-all','PUT').then(function(){fN();toast('Done','ok');});}
function clearRd(){api('/notifications/clear-read','DELETE').then(function(){fN();toast('Cleared','ok');});}
function openTM(t){['fid','ftit','fdsc','fdt','ftm','fasn','ftgs','fnts'].forEach(function(id){var e=G(id);if(e)e.value='';});
G('fpri').value='medium';G('fst').value='pending';G('frm').value=SE.default_reminder_medium||30;G('mTi').textContent='New Task';
fillSl('fcat',C.map(function(c){return{v:c.name,l:c.name};}));
if(t){G('mTi').textContent='Edit';G('fid').value=t.id;G('ftit').value=t.title||'';G('fdsc').value=t.description||'';
G('fcat').value=t.category||'General';G('fpri').value=t.priority||'medium';G('fdt').value=t.due_date||'';G('ftm').value=t.due_time||'';
G('fst').value=t.status||'pending';G('frm').value=t.reminder_mins||30;G('fasn').value=t.assigned_to||'';
G('ftgs').value=pTg(t.tags).join(', ');G('fnts').value=t.notes||'';}
G('tMd').classList.add('on');setTimeout(function(){G('ftit').focus();},100);}
function closeTM(){G('tMd').classList.remove('on');}
function edT(id){var t=T.filter(function(x){return x.id===id;})[0];if(t)openTM(t);}
G('fpri').addEventListener('change',function(){var rm={high:SE.default_reminder_high||15,medium:SE.default_reminder_medium||30,low:SE.default_reminder_low||60};G('frm').value=rm[this.value]||30;});
function saveT(){var id=G('fid').value;var tt=G('ftit').value.trim();if(!tt){toast('Title needed!','er');return;}
var tgs=G('ftgs').value?G('ftgs').value.split(',').map(function(s){return s.trim();}).filter(Boolean):[];
var pl={title:tt,description:G('fdsc').value,category:G('fcat').value,priority:G('fpri').value,status:G('fst').value,due_date:G('fdt').value||null,due_time:G('ftm').value||null,reminder_mins:parseInt(G('frm').value),assigned_to:G('fasn').value,tags:tgs,notes:G('fnts').value};
var url=id?'/tasks/'+id:'/tasks';var mth=id?'PUT':'POST';
api(url,mth,pl).then(function(r){if(r&&!r.error){toast(id?'Updated!':'Created!','ok');
showAP({type:'created',priority:pl.priority,message:'"'+tt+'" '+(id?'updated':'created'),created_at:new Date().toISOString()},pl.priority);
closeTM();loadAll();}});}
function togSt(id,e){e.stopPropagation();var t=T.filter(function(x){return x.id===id;})[0];if(!t)return;
var ns=t.status==='completed'?'pending':'completed';api('/tasks/'+id,'PUT',{status:ns}).then(function(r){if(r){toast(ns==='completed'?'Done! ':'Reopened','ok');if(ns==='completed')playSnd('high');loadAll();}});}
function dlT(id,e){e.stopPropagation();var t=T.filter(function(x){return x.id===id;})[0];if(!t||!confirm('Delete "'+t.title+'"?'))return;api('/tasks/'+id,'DELETE').then(function(){toast('Deleted','ok');loadAll();});}
function openCM(){G('cMd').classList.add('on');}
function closeCM(){G('cMd').classList.remove('on');}
function saveC(){var n=G('cnm').value.trim();if(!n){toast('Name needed','er');return;}api('/categories','POST',{name:n,color:G('ccl').value}).then(function(r){if(r&&!r.error){toast('Created','ok');closeCM();G('cnm').value='';loadAll();}else toast('Error','er');});}
function openSM(){G('sMd').classList.add('on');}
function closeSM(){G('sMd').classList.remove('on');}
function go(p,btn){pg=p;document.querySelectorAll('.pg').forEach(function(x){x.classList.remove('on');});document.querySelectorAll('.nbt').forEach(function(x){x.classList.remove('on');});var el=G('pg-'+p);if(el)el.classList.add('on');if(btn)btn.classList.add('on');render();if(window.innerWidth<=768)G('sb').classList.remove('mob');}
function fCat(n){go('all',document.querySelector('[data-p="all"]'));setTimeout(function(){var s=G('a-ca');if(s){s.value=n;rAll();}},50);}
var srT;function onSrch(){clearTimeout(srT);srT=setTimeout(function(){if(pg!=='all')go('all',document.querySelector('[data-p="all"]'));else rAll();},300);}
function toggleSB(){var s=G('sb');if(window.innerWidth<=768)s.classList.toggle('mob');else s.classList.toggle('slim');}
function toggleThm(){document.body.classList.toggle('dark');G('thmI').className=document.body.classList.contains('dark')?'fas fa-sun':'fas fa-moon';localStorage.setItem('tpt',document.body.classList.contains('dark')?'dark':'light');}
function loadThm(){if(localStorage.getItem('tpt')==='dark'){document.body.classList.add('dark');G('thmI').className='fas fa-sun';}}
function setGrt(){var h=new Date().getHours();TV('grt',h<12?'Good Morning!':h<17?'Good Afternoon!':'Good Evening!');}
function toast(m,tp){tp=tp||'ok';var w=G('tw');var e=document.createElement('div');e.className='tst '+tp;var ic={ok:'fa-check-circle',er:'fa-times-circle',wa:'fa-exclamation-triangle'}[tp]||'fa-info-circle';
e.innerHTML='<i class="fas '+ic+' tsti"></i><span class="tstm">'+m+'</span><button class="tstc" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>';
w.appendChild(e);setTimeout(function(){e.style.opacity='0';setTimeout(function(){e.remove();},300);},4000);}
document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();G('si').focus();}if((e.ctrlKey||e.metaKey)&&e.key==='n'){e.preventDefault();openTM();}
if(e.key==='Escape')document.querySelectorAll('.mdov.on,.ndp.on').forEach(function(el){el.classList.remove('on');});});
document.addEventListener('click',function(e){if(!e.target.closest('#bellBtn')&&!e.target.closest('#ndp'))G('ndp').classList.remove('on');});
</script></body></html>'''