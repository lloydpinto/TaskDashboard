from flask import Flask, request, jsonify, Response
import json, os
from datetime import datetime, timedelta

app = Flask(__name__)
DATA_FILE = '/tmp/taskpro.json'

DEFAULT = {
    "tasks":[],"categories":[
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
    ],"projects":[],"notifications":[],"activity":[],"settings":{
        "default_reminder_low":60,"default_reminder_medium":30,
        "default_reminder_high":15,"sound_enabled":1,"popup_enabled":1,
        "browser_notif_enabled":1,"popup_duration_low":5,
        "popup_duration_medium":8,"popup_duration_high":12,
        "auto_snooze_mins":10,"check_interval_secs":30
    },"nid":{"tasks":1,"categories":11,"projects":1,"notifications":1,"activity":1}
}

def ld():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,'r') as f:
                d=json.load(f)
                for k in DEFAULT:
                    if k not in d: d[k]=DEFAULT[k]
                return d
    except: pass
    return json.loads(json.dumps(DEFAULT))

def sv(d):
    try:
        with open(DATA_FILE,'w') as f: json.dump(d,f)
    except: pass

def ni():
    return datetime.now().isoformat()

def nid(d,c):
    cur=d["nid"].get(c,1); d["nid"][c]=cur+1; return cur

def logact(d,action,tid=None,title=''):
    d["activity"].insert(0,{"id":nid(d,"activity"),"action":action,"task_id":tid,"task_title":title,"timestamp":ni()})
    d["activity"]=d["activity"][:100]

def autonotif(d):
    now=datetime.now(); td=now.strftime('%Y-%m-%d'); tm=(now+timedelta(days=1)).strftime('%Y-%m-%d')
    ex=set()
    for n in d["notifications"]:
        ex.add(str(n.get('task_id',''))+'_'+str(n.get('type','')))
    for t in d["tasks"]:
        if t["status"]=="completed" or not t.get("due_date"): continue
        tid=t["id"]; pri=t.get("priority","medium")
        u='\U0001f534' if pri=='high' else '\U0001f7e1' if pri=='medium' else '\U0001f7e2'
        if t["due_date"]<td:
            k=str(tid)+'_overdue'
            if k not in ex:
                days=(now-datetime.strptime(t["due_date"],'%Y-%m-%d')).days
                d["notifications"].insert(0,{"id":nid(d,"notifications"),"task_id":tid,
                    "message":u+" OVERDUE ("+str(days)+"d): '"+t['title']+"'",
                    "type":"overdue","priority":pri,"is_read":0,"is_dismissed":0,
                    "created_at":ni(),"task_title":t["title"],"task_priority":pri})
        elif t["due_date"]==td:
            k=str(tid)+'_due_today'
            if k not in ex:
                ti=" at "+t['due_time'] if t.get("due_time") else ""
                d["notifications"].insert(0,{"id":nid(d,"notifications"),"task_id":tid,
                    "message":u+" Due Today"+ti+": '"+t['title']+"'",
                    "type":"due_today","priority":pri,"is_read":0,"is_dismissed":0,
                    "created_at":ni(),"task_title":t["title"],"task_priority":pri})
        if t.get("due_time") and not t.get("reminder_sent"):
            try:
                due=datetime.strptime(t['due_date']+" "+t['due_time'],'%Y-%m-%d %H:%M')
                ra=due-timedelta(minutes=t.get("reminder_mins",30))
                if now>=ra and now<due:
                    k=str(tid)+'_reminder'
                    if k not in ex:
                        ml=int((due-now).total_seconds()/60)
                        d["notifications"].insert(0,{"id":nid(d,"notifications"),"task_id":tid,
                            "message":u+" REMINDER: '"+t['title']+"' due in "+str(ml)+" min!",
                            "type":"reminder","priority":pri,"is_read":0,"is_dismissed":0,
                            "created_at":ni(),"task_title":t["title"],"task_priority":pri})
                        t["reminder_sent"]=1
            except: pass
        if pri=='high' and t["due_date"]==tm:
            k=str(tid)+'_upcoming_high'
            if k not in ex:
                d["notifications"].insert(0,{"id":nid(d,"notifications"),"task_id":tid,
                    "message":"\U0001f534 HIGH PRIORITY tomorrow: '"+t['title']+"'",
                    "type":"upcoming_high","priority":"high","is_read":0,"is_dismissed":0,
                    "created_at":ni(),"task_title":t["title"],"task_priority":"high"})
    d["notifications"]=d["notifications"][:80]

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']='*'
    r.headers['Access-Control-Allow-Headers']='Content-Type'
    r.headers['Access-Control-Allow-Methods']='GET,POST,PUT,DELETE,OPTIONS'
    return r

# ── SERVE HTML ──
@app.route('/')
def index():
    return Response(HTML_PAGE, content_type='text/html')

# ── SETTINGS ──
@app.route('/api/settings',methods=['GET','PUT','OPTIONS'])
def handle_settings():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    if request.method=='PUT':
        b=request.json or {}
        for k,v in b.items():
            if k in d["settings"]: d["settings"][k]=v
        sv(d)
    return jsonify(d["settings"])

# ── TASKS ──
@app.route('/api/tasks',methods=['GET','POST','OPTIONS'])
def handle_tasks():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    if request.method=='POST':
        b=request.json or {}
        pri=b.get('priority','medium')
        s=d["settings"]
        dr={'low':s.get('default_reminder_low',60),'medium':s.get('default_reminder_medium',30),'high':s.get('default_reminder_high',15)}
        ts=ni()
        t={"id":nid(d,"tasks"),"title":b.get('title','Untitled'),"description":b.get('description',''),
           "category":b.get('category','General'),"priority":pri,"status":b.get('status','pending'),
           "due_date":b.get('due_date')or None,"due_time":b.get('due_time')or None,
           "reminder_mins":b.get('reminder_mins',dr.get(pri,30)),"assigned_to":b.get('assigned_to',''),
           "project":b.get('project',''),"tags":json.dumps(b.get('tags',[])),"notes":b.get('notes',''),
           "estimated_hours":b.get('estimated_hours',0),"progress":b.get('progress',0),
           "is_pinned":1 if b.get('is_pinned') else 0,"created_at":ts,"updated_at":ts,
           "completed_at":None,"reminder_sent":0,"snooze_until":None}
        d["tasks"].insert(0,t)
        logact(d,'created',t['id'],t['title'])
        autonotif(d); sv(d)
        return jsonify(t),201
    tasks=d["tasks"]
    st=request.args.get('status',''); pr=request.args.get('priority','')
    ca=request.args.get('category',''); pj=request.args.get('project','')
    se=request.args.get('search','').lower()
    if st: tasks=[t for t in tasks if t.get('status')==st]
    if pr: tasks=[t for t in tasks if t.get('priority')==pr]
    if ca: tasks=[t for t in tasks if t.get('category')==ca]
    if pj: tasks=[t for t in tasks if t.get('project')==pj]
    if se: tasks=[t for t in tasks if se in (t.get('title','')or'').lower() or se in (t.get('description','')or'').lower()]
    so=request.args.get('sort','created_at'); od=request.args.get('order','desc')
    rv=od.lower()=='desc'
    if so=='priority':
        po={'high':0,'medium':1,'low':2}
        tasks.sort(key=lambda t:po.get(t.get('priority','medium'),1))
    else:
        tasks.sort(key=lambda t:t.get(so)or'',reverse=rv)
    tasks.sort(key=lambda t:t.get('is_pinned',0),reverse=True)
    return jsonify(tasks)

@app.route('/api/tasks/<int:tid>',methods=['GET','PUT','DELETE','OPTIONS'])
def handle_task(tid):
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld(); t=None
    for x in d["tasks"]:
        if x["id"]==tid: t=x; break
    if not t: return jsonify({"error":"Not found"}),404
    if request.method=='GET': return jsonify(t)
    if request.method=='DELETE':
        title=t['title']
        d["tasks"]=[x for x in d["tasks"] if x["id"]!=tid]
        d["notifications"]=[n for n in d["notifications"] if n.get("task_id")!=tid]
        logact(d,'deleted',tid,title); sv(d)
        return jsonify({"message":"Deleted"})
    b=request.json or {}
    os2=t['status']; ns=b.get('status',t['status'])
    for k in ['title','description','category','priority','status','due_date','due_time',
              'reminder_mins','assigned_to','project','notes','estimated_hours','progress',
              'is_pinned','snooze_until']:
        if k in b: t[k]=b[k]
    if 'tags' in b: t['tags']=json.dumps(b['tags']) if isinstance(b['tags'],list) else b['tags']
    t['updated_at']=ni()
    if ns=='completed' and os2!='completed': t['completed_at']=ni()
    elif ns!='completed': t['completed_at']=None
    if 'due_date' in b or 'due_time' in b: t['reminder_sent']=0
    logact(d,'updated',tid,t['title']); autonotif(d); sv(d)
    return jsonify(t)

@app.route('/api/tasks/<int:tid>/snooze',methods=['PUT','OPTIONS'])
def snooze(tid):
    if request.method=='OPTIONS': return jsonify({}),200
    b=request.json or {}; mins=b.get('minutes',10); d=ld()
    for t in d["tasks"]:
        if t["id"]==tid:
            t['snooze_until']=(datetime.now()+timedelta(minutes=mins)).isoformat()
            t['reminder_sent']=0
            d["notifications"]=[n for n in d["notifications"] if not(n.get("task_id")==tid and n.get("type")=="reminder")]
            sv(d); return jsonify({"ok":True})
    return jsonify({"error":"Not found"}),404

@app.route('/api/tasks/<int:tid>/pin',methods=['PUT','OPTIONS'])
def pin(tid):
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    for t in d["tasks"]:
        if t["id"]==tid:
            t['is_pinned']=0 if t.get('is_pinned') else 1
            sv(d); return jsonify({"is_pinned":t['is_pinned']})
    return jsonify({"error":"Not found"}),404

@app.route('/api/categories',methods=['GET','POST','OPTIONS'])
def handle_cats():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    if request.method=='POST':
        b=request.json or {}; name=b.get('name','')
        if any(c['name']==name for c in d["categories"]): return jsonify({"error":"Exists"}),400
        c={"id":nid(d,"categories"),"name":name,"color":b.get('color','#6366f1')}
        d["categories"].append(c); sv(d); return jsonify(c),201
    return jsonify(d["categories"])

@app.route('/api/projects',methods=['GET','POST','OPTIONS'])
def handle_projs():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    if request.method=='POST':
        b=request.json or {}; name=b.get('name','')
        if any(p['name']==name for p in d["projects"]): return jsonify({"error":"Exists"}),400
        p={"id":nid(d,"projects"),"name":name,"color":b.get('color','#0ea5e9'),
           "description":b.get('description',''),"created_at":ni()}
        d["projects"].append(p); sv(d); return jsonify(p),201
    return jsonify(d["projects"])

@app.route('/api/notifications',methods=['GET'])
def get_notifs():
    d=ld(); autonotif(d); sv(d)
    ns=[n for n in d["notifications"] if not n.get("is_dismissed")]
    po={'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n:po.get(n.get('priority','medium'),1))
    return jsonify(ns[:80])

@app.route('/api/notifications/new',methods=['GET'])
def get_new():
    d=ld(); autonotif(d); sv(d)
    ns=[n for n in d["notifications"] if not n.get("is_read") and not n.get("is_dismissed")]
    po={'high':0,'medium':1,'low':2}
    ns.sort(key=lambda n:po.get(n.get('priority','medium'),1))
    return jsonify(ns)

@app.route('/api/notifications/<int:nid2>/read',methods=['PUT','OPTIONS'])
def read_n(nid2):
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    for n in d["notifications"]:
        if n["id"]==nid2: n["is_read"]=1; break
    sv(d); return jsonify({"ok":True})

@app.route('/api/notifications/read-all',methods=['PUT','OPTIONS'])
def read_all():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld()
    for n in d["notifications"]: n["is_read"]=1
    sv(d); return jsonify({"ok":True})

@app.route('/api/notifications/clear-read',methods=['DELETE','OPTIONS'])
def clear_r():
    if request.method=='OPTIONS': return jsonify({}),200
    d=ld(); d["notifications"]=[n for n in d["notifications"] if not n.get("is_read")]
    sv(d); return jsonify({"ok":True})

@app.route('/api/statistics',methods=['GET'])
def get_stats():
    d=ld(); ts=d["tasks"]; td=datetime.now().strftime('%Y-%m-%d')
    total=len(ts); comp=sum(1 for t in ts if t['status']=='completed')
    pend=sum(1 for t in ts if t['status']=='pending')
    prog=sum(1 for t in ts if t['status']=='in_progress')
    ov=sum(1 for t in ts if t['status']!='completed' and t.get('due_date') and t['due_date']<td)
    dt=sum(1 for t in ts if t['status']!='completed' and t.get('due_date')==td)
    hp=sum(1 for t in ts if t['priority']=='high' and t['status']!='completed')
    return jsonify({"total":total,"completed":comp,"pending":pend,"in_progress":prog,
                    "overdue":ov,"due_today":dt,"high_priority":hp,
                    "completion_rate":round(comp/total*100,1) if total>0 else 0})

@app.route('/api/activity',methods=['GET'])
def get_act():
    d=ld(); lim=request.args.get('limit',30,type=int)
    return jsonify(d["activity"][:lim])

@app.route('/api/export',methods=['GET'])
def export_d():
    d=ld()
    return jsonify({"exported_at":ni(),"tasks":d["tasks"],"categories":d["categories"],
                    "projects":d["projects"],"settings":d["settings"]})

@app.route('/api/import',methods=['POST','OPTIONS'])
def import_d():
    if request.method=='OPTIONS': return jsonify({}),200
    b=request.json or {}; inc=b.get('tasks',[]); d=ld(); c=0; ts=ni()
    for t in inc:
        task={"id":nid(d,"tasks"),"title":t.get('title','Imported'),"description":t.get('description',''),
              "category":t.get('category','General'),"priority":t.get('priority','medium'),
              "status":t.get('status','pending'),"due_date":t.get('due_date'),"due_time":t.get('due_time'),
              "reminder_mins":t.get('reminder_mins',30),"assigned_to":t.get('assigned_to',''),
              "project":t.get('project',''),"tags":json.dumps(t.get('tags',[])),"notes":t.get('notes',''),
              "estimated_hours":0,"progress":0,"is_pinned":0,"created_at":ts,"updated_at":ts,
              "completed_at":None,"reminder_sent":0,"snooze_until":None}
        d["tasks"].insert(0,task); c+=1
    sv(d); return jsonify({"imported":c})


# ══════════════════════════════════════════════
# FULL HTML PAGE — embedded as string
# ══════════════════════════════════════════════
HTML_PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TaskPro Dashboard</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{--P:#4f46e5;--PH:#4338ca;--PL:#818cf8;--S:#0ea5e9;--OK:#22c55e;--WA:#f59e0b;--ER:#ef4444;--IN:#06b6d4;--bg:#f0f2f8;--card:#fff;--inp:#f8fafc;--tx:#1e293b;--txm:#64748b;--bdr:#e2e8f0;--sh2:0 8px 32px rgba(0,0,0,.13);--r:12px;--tr:all .22s ease;--sw:240px;--hh:56px}
body.dark{--bg:#0b1120;--card:#161f33;--inp:#0b1120;--tx:#e8edf5;--txm:#8899bb;--bdr:#1e2d47;--sh2:0 8px 32px rgba(0,0,0,.5)}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);font-size:14px;overflow:hidden;height:100vh}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
.app{display:flex;width:100vw;height:100vh}
.sb{width:var(--sw);flex-shrink:0;background:var(--card);border-right:1px solid var(--bdr);display:flex;flex-direction:column;height:100vh;transition:width .25s;overflow:hidden}
.sb.slim{width:58px}
.sb-b{height:var(--hh);display:flex;align-items:center;gap:10px;padding:0 14px;border-bottom:1px solid var(--bdr);flex-shrink:0}
.sb-l{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.sb-n{font-size:15px;font-weight:800;white-space:nowrap;background:linear-gradient(135deg,var(--P),var(--S));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sb.slim .sb-n{display:none}
.sb-nav{flex:1;overflow-y:auto;padding:8px 5px}
.ns2{margin-bottom:14px}
.nsl2{font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--txm);padding:0 8px;margin-bottom:4px;white-space:nowrap}
.sb.slim .nsl2{opacity:0}
.nb2{width:100%;display:flex;align-items:center;gap:8px;padding:8px 10px;border:none;background:none;border-radius:7px;cursor:pointer;color:var(--txm);transition:var(--tr);text-align:left;white-space:nowrap;overflow:hidden;font-size:12px}
.nb2 i{width:15px;text-align:center;font-size:12px;flex-shrink:0}
.nb2 .nt3{flex:1;font-weight:500}
.nb2 .nc3{background:var(--bg);color:var(--txm);font-size:9px;padding:1px 6px;border-radius:8px;flex-shrink:0}
.nb2:hover{background:var(--bg);color:var(--tx)}
.nb2.act{background:linear-gradient(135deg,var(--P),var(--PH));color:#fff}
.nb2.act .nc3{background:rgba(255,255,255,.25);color:#fff}
.sb.slim .nb2 .nt3,.sb.slim .nb2 .nc3{display:none}
.sb.slim .nb2{justify-content:center;padding:9px}
.rt{flex:1;display:flex;flex-direction:column;min-width:0;height:100vh;overflow:hidden}
.hd{height:var(--hh);background:var(--card);border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px;padding:0 16px;flex-shrink:0}
.hb2{width:32px;height:32px;border:none;background:var(--bg);border-radius:7px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--txm);position:relative;transition:var(--tr);flex-shrink:0;font-size:13px}
.hb2:hover{background:var(--P);color:#fff}
.bdg2{position:absolute;top:-3px;right:-3px;background:var(--ER);color:#fff;font-size:8px;min-width:15px;height:15px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700}
.swb{flex:1;max-width:460px;display:flex;align-items:center;gap:6px;background:var(--inp);border:1.5px solid var(--bdr);border-radius:7px;padding:0 11px}
.swb:focus-within{border-color:var(--P)}
.swb i{color:var(--txm);font-size:11px}
.swb input{flex:1;border:none;background:none;outline:none;padding:8px 0;color:var(--tx);font-size:12px}
.hr2{margin-left:auto;display:flex;align-items:center;gap:6px}
.av2{width:30px;height:30px;border-radius:7px;background:linear-gradient(135deg,var(--P),var(--S));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11px;cursor:pointer}
.ct{flex:1;overflow-y:auto;padding:18px 20px}
.pg{display:none;height:100%;flex-direction:column;gap:14px}
.pg.act{display:flex}
.phd{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px}
.phd h1{font-size:19px;font-weight:800;margin-bottom:2px}
.phd p{color:var(--txm);font-size:11px}
.phdr{display:flex;gap:6px}
.btn2{display:inline-flex;align-items:center;gap:5px;padding:8px 15px;border:none;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;transition:var(--tr);white-space:nowrap}
.bp{background:linear-gradient(135deg,var(--P),var(--PH));color:#fff}
.bp:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(79,70,229,.3)}
.bg2{background:var(--bg);color:var(--tx)}.bg2:hover{background:var(--bdr)}
.bok{background:var(--OK);color:#fff}
.bsm{padding:5px 10px;font-size:11px}
.sg2{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.sc2{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);padding:14px;display:flex;align-items:center;gap:10px;transition:var(--tr)}
.sc2:hover{transform:translateY(-2px);box-shadow:var(--sh2)}
.si2{width:36px;height:36px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:15px}
.sib2{background:rgba(79,70,229,.1);color:var(--P)}
.sig2{background:rgba(34,197,94,.1);color:var(--OK)}
.sio2{background:rgba(245,158,11,.1);color:var(--WA)}
.sir2{background:rgba(239,68,68,.1);color:var(--ER)}
.sic2{background:rgba(6,182,212,.1);color:var(--IN)}
.sip2{background:rgba(139,92,246,.1);color:#8b5cf6}
.sv2{font-size:22px;font-weight:800;line-height:1}
.sl2{color:var(--txm);font-size:10px;margin-top:2px}
.dg2{display:grid;grid-template-columns:1fr 260px;gap:12px;flex:1;min-height:0}
@media(max-width:1000px){.dg2{grid-template-columns:1fr}.dp2{display:none!important}}
.cd{background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);overflow:hidden;display:flex;flex-direction:column}
.cdh{padding:10px 14px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;gap:6px;flex-shrink:0}
.cdh h2{font-size:13px;font-weight:700}
.cdb{padding:12px;flex:1;overflow-y:auto}
.fb2{display:flex;gap:5px;flex-wrap:wrap}
.fb2 select{padding:5px 8px;border:1px solid var(--bdr);border-radius:5px;background:var(--inp);color:var(--tx);font-size:10px;cursor:pointer;outline:none}
.tl2{overflow-y:auto;flex:1}
.trw{display:flex;align-items:flex-start;gap:10px;padding:11px 14px;border-bottom:1px solid var(--bdr);transition:var(--tr);cursor:pointer}
.trw:last-child{border-bottom:none}
.trw:hover{background:var(--bg)}
.trw.dn{opacity:.5}
.trw.ovr{border-left:3px solid var(--ER)}
.ck{width:18px;height:18px;border:2px solid var(--bdr);border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer;margin-top:2px;transition:var(--tr)}
.ck:hover{border-color:var(--P)}
.ck.dn{background:var(--OK);border-color:var(--OK);color:#fff}
.tinfo{flex:1;min-width:0}
.tname{font-weight:600;font-size:12px;margin-bottom:3px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.trw.dn .tname{text-decoration:line-through;color:var(--txm)}
.tdesc{font-size:10px;color:var(--txm);margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tmeta{display:flex;gap:8px;flex-wrap:wrap;font-size:9px;color:var(--txm)}
.tmeta i{margin-right:2px}
.ovtx{color:var(--ER)!important;font-weight:700}
.tg{display:inline-flex;padding:1px 6px;background:var(--bg);border-radius:20px;font-size:8px;color:var(--txm);margin-top:3px;margin-right:2px}
.pri2{padding:1px 5px;border-radius:3px;font-size:8px;font-weight:700;text-transform:uppercase}
.prh{background:rgba(239,68,68,.1);color:var(--ER)}
.prm{background:rgba(245,158,11,.1);color:var(--WA)}
.prl{background:rgba(34,197,94,.1);color:var(--OK)}
.stb{padding:1px 7px;border-radius:20px;font-size:8px;font-weight:600}
.stp{background:rgba(245,158,11,.1);color:var(--WA)}
.sti{background:rgba(79,70,229,.1);color:var(--P)}
.stc{background:rgba(34,197,94,.1);color:var(--OK)}
.tact{display:flex;gap:3px;flex-shrink:0;opacity:0;transition:opacity .2s}
.trw:hover .tact{opacity:1}
.ab2{width:24px;height:24px;border:none;border-radius:4px;background:var(--bg);cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;font-size:10px;transition:var(--tr)}
.ab2:hover{background:var(--P);color:#fff}
.ab2.dl:hover{background:var(--ER)}
.emy{padding:35px 18px;text-align:center;color:var(--txm)}
.emy i{font-size:40px;margin-bottom:10px;opacity:.3;display:block}
.emy h3{font-size:14px;margin-bottom:5px;color:var(--tx)}
.emy p{font-size:11px;margin-bottom:12px}
.rw2{display:flex;align-items:center;justify-content:center;gap:14px;padding:8px 0}
.rc2{position:relative;width:70px;height:70px}
.rc2 svg{transform:rotate(-90deg)}
.rm2{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}
.rp2{font-size:14px;font-weight:800}
.rl2{font-size:8px;color:var(--txm)}
.rs2{display:flex;flex-direction:column;gap:4px}
.rsi2{display:flex;align-items:center;gap:5px;font-size:10px}
.dot2{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.pr3{display:flex;align-items:center;gap:6px;padding:5px 7px;border-radius:5px;cursor:pointer;transition:var(--tr)}
.pr3:hover{background:var(--bg)}
.pd2{width:7px;height:7px;border-radius:50%}
.pn3{flex:1;font-size:10px}
.pc3{font-size:9px;color:var(--txm);background:var(--bg);padding:0 5px;border-radius:7px}
.ndrop2{position:fixed;top:calc(var(--hh)+3px);right:10px;width:320px;background:var(--card);border-radius:var(--r);border:1px solid var(--bdr);box-shadow:var(--sh2);z-index:999;opacity:0;pointer-events:none;transform:translateY(8px);transition:var(--tr)}
.ndrop2.open{opacity:1;pointer-events:all;transform:translateY(0)}
.ndh2{padding:10px 12px;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.ndh2 h3{font-size:12px;font-weight:700}
.nda2{display:flex;gap:5px}
.ndl2{font-size:9px;color:var(--P);cursor:pointer;background:none;border:none}
.ndl2:hover{text-decoration:underline}
.ndl2.er2{color:var(--ER)}
.nds2{max-height:340px;overflow-y:auto}
.ndi2{display:flex;gap:9px;padding:10px 12px;border-bottom:1px solid var(--bdr);cursor:pointer;transition:var(--tr)}
.ndi2:last-child{border-bottom:none}
.ndi2:hover{background:var(--bg)}
.ndi2.ur{background:rgba(79,70,229,.04)}
.ndi2.hp2{border-left:3px solid var(--ER)}
.ndi2.mp2{border-left:3px solid var(--WA)}
.ni2{width:30px;height:30px;border-radius:6px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px}
.ni2.overdue,.ni2.upcoming_high{background:rgba(239,68,68,.1);color:var(--ER)}
.ni2.due_today{background:rgba(245,158,11,.1);color:var(--WA)}
.ni2.reminder{background:rgba(79,70,229,.1);color:var(--P)}
.nt4{flex:1;min-width:0}
.nm2{font-size:11px;margin-bottom:2px;line-height:1.3}
.ntm2{font-size:8px;color:var(--txm)}
.nde2{padding:25px;text-align:center;color:var(--txm);font-size:11px}
.ov3{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:600;opacity:0;pointer-events:none;transition:var(--tr)}
.ov3.open{opacity:1;pointer-events:all}
.md{background:var(--card);border-radius:14px;width:92%;max-width:520px;max-height:90vh;display:flex;flex-direction:column;transform:scale(.94);transition:var(--tr)}
.ov3.open .md{transform:scale(1)}
.mdh{padding:14px 18px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.mdh h2{font-size:15px;font-weight:700}
.mdc{width:28px;height:28px;border:none;background:var(--bg);border-radius:5px;cursor:pointer;color:var(--txm);display:flex;align-items:center;justify-content:center;transition:var(--tr)}
.mdc:hover{background:var(--ER);color:#fff}
.mdb{padding:18px;overflow-y:auto;flex:1}
.mdf{padding:10px 18px;border-top:1px solid var(--bdr);display:flex;justify-content:flex-end;gap:7px;flex-shrink:0}
.fg2{margin-bottom:12px}
.fl2{display:block;font-size:10px;font-weight:700;margin-bottom:4px}
.fl2 span{color:var(--ER)}
.fi2,.fs2,.fta2{width:100%;padding:8px 11px;border:1.5px solid var(--bdr);border-radius:6px;background:var(--inp);color:var(--tx);font-size:12px;outline:none;transition:var(--tr)}
.fi2:focus,.fs2:focus,.fta2:focus{border-color:var(--P)}
.fta2{min-height:60px;resize:vertical}
.fr3{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:480px){.fr3{grid-template-columns:1fr}}
.tw2{position:fixed;top:12px;right:12px;display:flex;flex-direction:column;gap:5px;z-index:2000}
.tst{display:flex;align-items:center;gap:9px;background:var(--card);border-radius:8px;padding:11px 14px;box-shadow:var(--sh2);min-width:240px;border-left:4px solid var(--P);animation:tin .25s ease}
.tst.ok{border-left-color:var(--OK)}.tst.er{border-left-color:var(--ER)}.tst.wa{border-left-color:var(--WA)}
.tsti{font-size:15px}.tst.ok .tsti{color:var(--OK)}.tst.er .tsti{color:var(--ER)}.tst.wa .tsti{color:var(--WA)}
.tstm{flex:1;font-size:12px}
.tstc{background:none;border:none;cursor:pointer;color:var(--txm);font-size:13px}
@keyframes tin{from{opacity:0;transform:translateX(50px)}to{opacity:1;transform:translateX(0)}}
.ap2{position:fixed;bottom:20px;right:20px;width:310px;background:var(--card);border-radius:11px;box-shadow:0 10px 36px rgba(0,0,0,.2);border:1px solid var(--bdr);z-index:3000;overflow:hidden;transform:translateY(120%);transition:transform .4s cubic-bezier(.34,1.56,.64,1)}
.ap2.show{transform:translateY(0)}
.aps{height:4px;width:100%}
.aps.high{background:linear-gradient(90deg,var(--ER),#ff8a80)}
.aps.medium{background:linear-gradient(90deg,var(--WA),#ffe57f)}
.aps.low{background:linear-gradient(90deg,var(--OK),#69f0ae)}
.aps.created{background:linear-gradient(90deg,var(--P),var(--PL))}
.apb{padding:12px 14px;display:flex;gap:10px;align-items:flex-start}
.api2{width:36px;height:36px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:16px}
.api2.high{background:rgba(239,68,68,.12);color:var(--ER)}
.api2.medium{background:rgba(245,158,11,.12);color:var(--WA)}
.api2.low{background:rgba(34,197,94,.12);color:var(--OK)}
.api2.created{background:rgba(79,70,229,.12);color:var(--P)}
.apt{flex:1;min-width:0}
.aptt{font-size:11px;font-weight:700;margin-bottom:2px}
.apmg{font-size:10px;color:var(--txm);line-height:1.4}
.appr{display:inline-flex;padding:1px 7px;border-radius:20px;font-size:8px;font-weight:700;text-transform:uppercase;margin-top:4px}
.appr.high{background:rgba(239,68,68,.1);color:var(--ER)}
.appr.medium{background:rgba(245,158,11,.1);color:var(--WA)}
.appr.low{background:rgba(34,197,94,.1);color:var(--OK)}
.apcl{width:22px;height:22px;border:none;background:var(--bg);border-radius:4px;cursor:pointer;color:var(--txm);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:10px;transition:var(--tr)}
.apcl:hover{background:var(--ER);color:#fff}
.appg{height:2px;background:var(--bdr)}
.apbar{height:100%;background:var(--P);width:100%}
.apft{padding:7px 14px;border-top:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.aptm{font-size:8px;color:var(--txm)}
.apac{display:flex;gap:5px}
.apbtn{font-size:9px;cursor:pointer;font-weight:600;background:none;border:none;padding:3px 8px;border-radius:4px;transition:var(--tr)}
.apbtn.snz{background:var(--bg);color:var(--tx)}.apbtn.snz:hover{background:var(--bdr)}
.apbtn.vw{color:var(--P)}.apbtn.vw:hover{text-decoration:underline}
.sets{margin-bottom:18px}
.sets h3{font-size:13px;font-weight:700;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--bdr)}
.setr{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--bdr)}
.setr:last-child{border-bottom:none}
.seti h4{font-size:12px;margin-bottom:1px}
.seti p{font-size:9px;color:var(--txm)}
.tgl{position:relative;width:40px;height:22px;flex-shrink:0}
.tgl input{opacity:0;width:0;height:0}
.tgls{position:absolute;cursor:pointer;inset:0;background:var(--bdr);border-radius:22px;transition:var(--tr)}
.tgls::before{position:absolute;content:"";width:16px;height:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:var(--tr)}
.tgl input:checked+.tgls{background:var(--P)}
.tgl input:checked+.tgls::before{transform:translateX(18px)}
@keyframes shrink{from{width:100%}to{width:0%}}
@media(max-width:768px){.sb{position:fixed;left:-100%;transition:left .3s;z-index:200}.sb.mob{left:0}.ct{padding:10px}}
</style>
</head>
<body>
<div class="app">
<aside class="sb" id="sidebar">
<div class="sb-b"><div class="sb-l"><i class="fas fa-layer-group"></i></div><span class="sb-n">TaskPro</span></div>
<nav class="sb-nav">
<div class="ns2"><div class="nsl2">MAIN</div>
<button class="nb2 act" data-p="dashboard" onclick="go('dashboard',this)"><i class="fas fa-th-large"></i><span class="nt3">Dashboard</span></button>
<button class="nb2" data-p="all" onclick="go('all',this)"><i class="fas fa-list-check"></i><span class="nt3">All Tasks</span><span class="nc3" id="nc-all">0</span></button>
<button class="nb2" data-p="today" onclick="go('today',this)"><i class="fas fa-calendar-day"></i><span class="nt3">Due Today</span><span class="nc3" id="nc-today">0</span></button>
<button class="nb2" data-p="overdue" onclick="go('overdue',this)"><i class="fas fa-exclamation-circle"></i><span class="nt3">Overdue</span><span class="nc3" id="nc-ov" style="background:var(--ER);color:#fff">0</span></button>
<button class="nb2" data-p="completed" onclick="go('completed',this)"><i class="fas fa-check-double"></i><span class="nt3">Completed</span></button>
</div>
<div class="ns2"><div class="nsl2">CATEGORIES</div><div id="sbC"></div></div>
</nav>
</aside>
<div class="rt">
<header class="hd">
<button class="hb2" onclick="toggleSB()"><i class="fas fa-bars"></i></button>
<div class="swb"><i class="fas fa-search"></i><input id="srch" placeholder="Search..." oninput="onSrch()"></div>
<div class="hr2">
<button class="hb2" onclick="toggleTheme()"><i class="fas fa-moon" id="thI"></i></button>
<button class="hb2" id="bellBtn" onclick="toggleND()"><i class="fas fa-bell"></i><span class="bdg2" id="nBdg" style="display:none">0</span></button>
<button class="hb2" onclick="openSM()"><i class="fas fa-cog"></i></button>
<div class="av2">JD</div>
</div>
</header>
<div class="ndrop2" id="nDrop">
<div class="ndh2"><h3>Notifications</h3><div class="nda2"><button class="ndl2" onclick="markAll()">Read all</button><button class="ndl2 er2" onclick="clearR()">Clear</button></div></div>
<div class="nds2" id="nList"></div>
</div>
<div class="ct">
<div class="pg act" id="pg-dashboard">
<div class="phd"><div><h1 id="greet">Hello!</h1><p>Your task overview</p></div>
<div class="phdr"><button class="btn2 bg2" onclick="loadAll()"><i class="fas fa-sync"></i></button>
<button class="btn2 bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div></div>
<div class="sg2">
<div class="sc2"><div class="si2 sib2"><i class="fas fa-tasks"></i></div><div><div class="sv2" id="s-t">0</div><div class="sl2">Total</div></div></div>
<div class="sc2"><div class="si2 sig2"><i class="fas fa-check-circle"></i></div><div><div class="sv2" id="s-d">0</div><div class="sl2">Done</div></div></div>
<div class="sc2"><div class="si2 sio2"><i class="fas fa-spinner"></i></div><div><div class="sv2" id="s-p">0</div><div class="sl2">Progress</div></div></div>
<div class="sc2"><div class="si2 sir2"><i class="fas fa-exclamation-triangle"></i></div><div><div class="sv2" id="s-o">0</div><div class="sl2">Overdue</div></div></div>
</div>
<div class="dg2" style="flex:1;min-height:0">
<div class="cd" style="min-height:0">
<div class="cdh"><h2>Tasks</h2><div class="fb2">
<select id="d-st" onchange="rDash()"><option value="">All</option><option value="pending">Pending</option><option value="in_progress">Progress</option><option value="completed">Done</option></select>
<select id="d-pr" onchange="rDash()"><option value="">Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
</div></div><div class="tl2" id="dList"></div></div>
<div class="dp2" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto">
<div class="cd"><div class="cdh"><h2>Progress</h2></div><div class="cdb">
<div class="rw2"><div class="rc2"><svg width="70" height="70" viewBox="0 0 70 70"><circle cx="35" cy="35" r="29" fill="none" stroke="var(--bdr)" stroke-width="7"/><circle id="rC" cx="35" cy="35" r="29" fill="none" stroke="var(--P)" stroke-width="7" stroke-linecap="round" stroke-dasharray="182" stroke-dashoffset="182" style="transition:stroke-dashoffset .6s"/></svg>
<div class="rm2"><div class="rp2" id="rPct">0%</div><div class="rl2">done</div></div></div>
<div class="rs2"><div class="rsi2"><span class="dot2" style="background:var(--OK)"></span>Done: <b id="rD">0</b></div>
<div class="rsi2"><span class="dot2" style="background:var(--WA)"></span>Pending: <b id="rPn">0</b></div>
<div class="rsi2"><span class="dot2" style="background:var(--ER)"></span>Overdue: <b id="rO">0</b></div></div></div></div></div>
<div class="cd"><div class="cdh"><h2>Categories</h2></div><div class="cdb" style="padding:6px 8px"><div id="cP"></div></div></div>
</div></div></div>
<div class="pg" id="pg-all"><div class="phd"><div><h1>All Tasks</h1></div><div class="phdr"><button class="btn2 bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div></div>
<div class="cd" style="flex:1"><div class="cdh"><div class="fb2">
<select id="a-st" onchange="rAll()"><option value="">All</option><option value="pending">Pending</option><option value="in_progress">Progress</option><option value="completed">Done</option></select>
<select id="a-pr" onchange="rAll()"><option value="">Priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
<select id="a-ca" onchange="rAll()"><option value="">Category</option></select>
</div></div><div class="tl2" id="aL" style="flex:1"></div></div></div>
<div class="pg" id="pg-today"><div class="phd"><div><h1>Due Today</h1></div><div class="phdr"><button class="btn2 bp" onclick="openTM()"><i class="fas fa-plus"></i></button></div></div><div class="cd" style="flex:1"><div class="tl2" id="tL" style="flex:1"></div></div></div>
<div class="pg" id="pg-overdue"><div class="phd"><div><h1>Overdue</h1></div></div><div class="cd" style="flex:1"><div class="tl2" id="oL" style="flex:1"></div></div></div>
<div class="pg" id="pg-completed"><div class="phd"><div><h1>Completed</h1></div></div><div class="cd" style="flex:1"><div class="tl2" id="cL" style="flex:1"></div></div></div>
</div></div></div>

<div class="ap2" id="aP"><div class="aps" id="apS"></div><div class="apb"><div class="api2" id="apI"><i class="fas fa-bell" id="apIi"></i></div><div class="apt"><div class="aptt" id="apTt">Alert</div><div class="apmg" id="apMg">Update</div><div class="appr" id="apPri">MEDIUM</div></div><button class="apcl" onclick="closeAP()"><i class="fas fa-times"></i></button></div><div class="appg"><div class="apbar" id="apBar"></div></div><div class="apft"><span class="aptm" id="apTm">Now</span><div class="apac"><button class="apbtn snz" onclick="closeAP()">Snooze</button><button class="apbtn vw" onclick="closeAP()">Dismiss</button></div></div></div>

<div class="ov3" id="tOv"><div class="md"><div class="mdh"><h2 id="mTi">New Task</h2><button class="mdc" onclick="closeTM()"><i class="fas fa-times"></i></button></div><div class="mdb"><input type="hidden" id="f-id">
<div class="fg2"><label class="fl2">Title <span>*</span></label><input class="fi2" id="f-title"></div>
<div class="fg2"><label class="fl2">Description</label><textarea class="fta2" id="f-desc"></textarea></div>
<div class="fr3"><div class="fg2"><label class="fl2">Category</label><select class="fs2" id="f-cat"></select></div><div class="fg2"><label class="fl2">Priority</label><select class="fs2" id="f-pri"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></div></div>
<div class="fr3"><div class="fg2"><label class="fl2">Due Date</label><input type="date" class="fi2" id="f-date"></div><div class="fg2"><label class="fl2">Due Time</label><input type="time" class="fi2" id="f-time"></div></div>
<div class="fr3"><div class="fg2"><label class="fl2">Status</label><select class="fs2" id="f-status"><option value="pending">Pending</option><option value="in_progress">In Progress</option><option value="completed">Done</option></select></div><div class="fg2"><label class="fl2">Reminder</label><select class="fs2" id="f-rem"><option value="5">5m</option><option value="10">10m</option><option value="15">15m</option><option value="30" selected>30m</option><option value="60">1h</option><option value="1440">1d</option></select></div></div>
<div class="fg2"><label class="fl2">Assigned To</label><input class="fi2" id="f-asn"></div>
<div class="fg2"><label class="fl2">Tags (comma separated)</label><input class="fi2" id="f-tags"></div>
<div class="fg2"><label class="fl2">Notes</label><textarea class="fta2" id="f-notes"></textarea></div>
</div><div class="mdf"><button class="btn2 bg2" onclick="closeTM()">Cancel</button><button class="btn2 bp" onclick="saveT()"><i class="fas fa-save"></i> Save</button></div></div></div>

<div class="ov3" id="cOv"><div class="md" style="max-width:320px"><div class="mdh"><h2>New Category</h2><button class="mdc" onclick="closeCM()"><i class="fas fa-times"></i></button></div><div class="mdb"><div class="fg2"><label class="fl2">Name</label><input class="fi2" id="cn"></div><div class="fg2"><label class="fl2">Color</label><input type="color" class="fi2" id="cc" value="#4f46e5" style="height:36px;padding:3px"></div></div><div class="mdf"><button class="btn2 bg2" onclick="closeCM()">Cancel</button><button class="btn2 bp" onclick="saveCat()">Save</button></div></div></div>

<div class="ov3" id="sOv"><div class="md" style="max-width:460px"><div class="mdh"><h2>Settings</h2><button class="mdc" onclick="closeSM()"><i class="fas fa-times"></i></button></div><div class="mdb">
<div class="sets"><h3>Notifications</h3>
<div class="setr"><div class="seti"><h4>Sound</h4></div><label class="tgl"><input type="checkbox" id="s-sound" checked onchange="saveSet()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Popup</h4></div><label class="tgl"><input type="checkbox" id="s-popup" checked onchange="saveSet()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Browser Notif</h4></div><label class="tgl"><input type="checkbox" id="s-browser" checked onchange="saveSet()"><span class="tgls"></span></label></div>
<div class="setr"><div class="seti"><h4>Poll Interval</h4></div><select class="fs2" id="s-interval" style="width:80px" onchange="saveSet()"><option value="15">15s</option><option value="30">30s</option><option value="60">60s</option></select></div>
</div>
<div class="sets"><h3>Default Reminders</h3>
<div class="setr"><div class="seti"><h4>High Priority</h4></div><select class="fs2" id="s-rh" style="width:90px" onchange="saveSet()"><option value="5">5m</option><option value="10">10m</option><option value="15">15m</option><option value="30">30m</option></select></div>
<div class="setr"><div class="seti"><h4>Medium Priority</h4></div><select class="fs2" id="s-rm" style="width:90px" onchange="saveSet()"><option value="15">15m</option><option value="30">30m</option><option value="60">1h</option></select></div>
<div class="setr"><div class="seti"><h4>Low Priority</h4></div><select class="fs2" id="s-rl" style="width:90px" onchange="saveSet()"><option value="30">30m</option><option value="60">1h</option><option value="120">2h</option></select></div>
</div>
<div class="sets"><h3>Popup Duration</h3>
<div class="setr"><div class="seti"><h4>High</h4></div><select class="fs2" id="s-dh" style="width:80px" onchange="saveSet()"><option value="10">10s</option><option value="12">12s</option><option value="15">15s</option></select></div>
<div class="setr"><div class="seti"><h4>Medium</h4></div><select class="fs2" id="s-dm" style="width:80px" onchange="saveSet()"><option value="5">5s</option><option value="8">8s</option><option value="10">10s</option></select></div>
<div class="setr"><div class="seti"><h4>Low</h4></div><select class="fs2" id="s-dl" style="width:80px" onchange="saveSet()"><option value="3">3s</option><option value="5">5s</option><option value="8">8s</option></select></div>
</div>
</div><div class="mdf"><button class="btn2 bp" onclick="closeSM()">Done</button></div></div></div>

<div class="tw2" id="tw"></div>

<script>
var A='/api';
var allT=[],cats=[],stats={},notifs=[],settings={};
var cur='dashboard',knownN={},aQ=[],aSh=false,aTmr=null,pTmr=null,curATid=null;

document.addEventListener('DOMContentLoaded',function(){setGreet();loadTheme();loadAll();
if('Notification' in window && Notification.permission==='default')Notification.requestPermission();});

function loadAll(){Promise.all([fT(),fC(),fS(),fN(),fSet()]).then(function(){render();renderSB();});}

function apiC(p,m,b){m=m||'GET';var o={method:m,headers:{'Content-Type':'application/json'}};
if(b)o.body=JSON.stringify(b);return fetch(A+p,o).then(function(r){return r.json();}).catch(function(e){console.error(e);toast('Error','er');return null;});}

function fT(){return apiC('/tasks?sort=created_at&order=desc').then(function(r){allT=r||[];});}
function fC(){return apiC('/categories').then(function(r){cats=r||[];});}
function fS(){return apiC('/statistics').then(function(r){stats=r||{};});}
function fN(){return apiC('/notifications').then(function(r){notifs=r||[];updateBdg();renderNL();});}
function fSet(){return apiC('/settings').then(function(r){settings=r||{};
G('s-sound').checked=settings.sound_enabled!==0;G('s-popup').checked=settings.popup_enabled!==0;
G('s-browser').checked=settings.browser_notif_enabled!==0;
SV('s-interval',settings.check_interval_secs||30);SV('s-rh',settings.default_reminder_high||15);
SV('s-rm',settings.default_reminder_medium||30);SV('s-rl',settings.default_reminder_low||60);
SV('s-dh',settings.popup_duration_high||12);SV('s-dm',settings.popup_duration_medium||8);
SV('s-dl',settings.popup_duration_low||5);startPoll();});}

function SV(id,v){var e=G(id);if(e)e.value=v;}

function saveSet(){var d={sound_enabled:G('s-sound').checked?1:0,popup_enabled:G('s-popup').checked?1:0,
browser_notif_enabled:G('s-browser').checked?1:0,check_interval_secs:parseInt(G('s-interval').value),
default_reminder_high:parseInt(G('s-rh').value),default_reminder_medium:parseInt(G('s-rm').value),
default_reminder_low:parseInt(G('s-rl').value),popup_duration_high:parseInt(G('s-dh').value),
popup_duration_medium:parseInt(G('s-dm').value),popup_duration_low:parseInt(G('s-dl').value)};
apiC('/settings','PUT',d).then(function(r){settings=r||settings;startPoll();toast('Saved','ok');});}

function startPoll(){if(pTmr)clearInterval(pTmr);pTmr=setInterval(pollN,(settings.check_interval_secs||30)*1000);}

function pollN(){apiC('/notifications/new').then(function(nw){if(!nw)return;
var fresh=nw.filter(function(n){return!knownN[n.id];});
fresh.forEach(function(n){knownN[n.id]=true;aQ.push(n);});
if(fresh.length>0){fN().then(processQ);}});}

function processQ(){if(aSh||aQ.length===0)return;var n=aQ.shift();
var pri=n.priority||'medium';if(settings.popup_enabled!==0)showAP(n,pri);}

function showAP(n,pri){aSh=true;clearTimeout(aTmr);curATid=n.task_id||null;
var cfgs={overdue:{t:'OVERDUE',i:'fa-exclamation-circle'},due_today:{t:'Due Today',i:'fa-calendar-check'},
reminder:{t:'Reminder',i:'fa-bell'},upcoming_high:{t:'Tomorrow',i:'fa-fire'},created:{t:'Created',i:'fa-check-circle'}};
var cfg=cfgs[n.type]||{t:'Alert',i:'fa-bell'};var ic=n.type==='created'?'created':pri;
G('apS').className='aps '+ic;G('apI').className='api2 '+ic;G('apIi').className='fas '+cfg.i;
G('apTt').textContent=cfg.t;G('apMg').textContent=n.message||'Update';
G('apPri').className='appr '+pri;G('apPri').textContent=pri.toUpperCase();G('apTm').textContent=tAgo(n.created_at);
var durs={high:settings.popup_duration_high||12,medium:settings.popup_duration_medium||8,low:settings.popup_duration_low||5};
var dur=durs[pri]||8;var bar=G('apBar');bar.style.animation='none';bar.offsetHeight;
bar.style.animation=dur>0?'shrink '+dur+'s linear forwards':'none';
G('aP').classList.add('show');
if(settings.sound_enabled!==0)playS(pri);
if(settings.browser_notif_enabled!==0&&'Notification' in window&&Notification.permission==='granted')
new Notification('TaskPro: '+cfg.t,{body:n.message||''});
if(dur>0)aTmr=setTimeout(function(){closeAP();setTimeout(processQ,400);},dur*1000);}

function closeAP(){G('aP').classList.remove('show');clearTimeout(aTmr);curATid=null;setTimeout(function(){aSh=false;processQ();},350);}

var actx;
function playS(pri){try{if(!actx)actx=new(window.AudioContext||window.webkitAudioContext)();
var ns={high:[[523,0],[659,.12],[784,.24],[1047,.36]],medium:[[523,0],[659,.15],[784,.3]],low:[[523,0],[659,.2]]};
(ns[pri]||ns.medium).forEach(function(p){var o=actx.createOscillator(),g=actx.createGain();o.connect(g);g.connect(actx.destination);
o.type=pri==='high'?'triangle':'sine';o.frequency.value=p[0];var t=actx.currentTime+p[1];
g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.15,t+.04);g.gain.exponentialRampToValueAtTime(.001,t+.4);
o.start(t);o.stop(t+.5);});}catch(e){}}

function G(id){return document.getElementById(id);}
function td2(){return new Date().toISOString().split('T')[0];}
function isOv(t){return t.due_date&&t.due_date<td2()&&t.status!=='completed';}
function fD(s){if(!s)return'';return new Date(s+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'});}
function tAgo(s){if(!s)return'';var d=Math.floor((Date.now()-new Date(s))/1000);
if(d<60)return'Now';if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'h';return Math.floor(d/86400)+'d';}
function pT(t){try{return JSON.parse(t||'[]');}catch(e){return[];}}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function cap(s){return s?s.charAt(0).toUpperCase()+s.slice(1):'';}
function stV(id,v){var e=G(id);if(e)e.textContent=v;}
function fillS(id,items,ph){var el=G(id);if(!el)return;var c=el.value;var h=ph?'<option value="">'+ph+'</option>':'';
items.forEach(function(i){h+='<option value="'+esc(i.v)+'">'+esc(i.l)+'</option>';});el.innerHTML=h;if(c)el.value=c;}

function tRow(t){var ov=isOv(t);var tags=pT(t.tags).map(function(g){return '<span class="tg">#'+esc(g)+'</span>';}).join('');
var pc={high:'prh',medium:'prm',low:'prl'}[t.priority]||'prm';
var sc={pending:'stp',in_progress:'sti',completed:'stc'}[t.status]||'stp';
var rc=(t.status==='completed'?' dn':'')+(ov?' ovr':'');
var ck=t.status==='completed'?'dn':'';
var ci=t.status==='completed'?'<i class="fas fa-check" style="font-size:8px"></i>':'';
var h='<div class="trw'+rc+'">';
h+='<div class="ck '+ck+'" onclick="togSt('+t.id+',event)">'+ci+'</div>';
h+='<div class="tinfo" onclick="editT('+t.id+')">';
h+='<div class="tname">'+esc(t.title)+' <span class="pri2 '+pc+'">'+t.priority+'</span> <span class="stb '+sc+'">'+t.status.replace('_',' ')+'</span></div>';
if(t.description)h+='<div class="tdesc">'+esc(t.description)+'</div>';
h+='<div class="tmeta">';
if(t.due_date){h+='<span class="'+(ov?'ovtx':'')+'"><i class="fas fa-calendar"></i>'+fD(t.due_date);
if(t.due_time)h+=' '+t.due_time;if(ov)h+=' !!';h+='</span>';}
h+='<span><i class="fas fa-folder"></i>'+esc(t.category)+'</span>';
if(t.assigned_to)h+='<span><i class="fas fa-user"></i>'+esc(t.assigned_to)+'</span>';
h+='<span><i class="fas fa-bell"></i>'+(t.reminder_mins||30)+'m</span>';
h+='</div>';
if(tags)h+='<div style="margin-top:3px">'+tags+'</div>';
h+='</div>';
h+='<div class="tact"><button class="ab2" onclick="editT('+t.id+')"><i class="fas fa-pen"></i></button>';
h+='<button class="ab2 dl" onclick="delT('+t.id+',event)"><i class="fas fa-trash"></i></button></div>';
h+='</div>';return h;}

function emS(m){m=m||'No tasks found';return '<div class="emy"><i class="fas fa-clipboard-list"></i><h3>'+m+'</h3><button class="btn2 bp" onclick="openTM()"><i class="fas fa-plus"></i> New Task</button></div>';}
function setL(id,l){var e=G(id);if(!e)return;if(!l||l.length===0){e.innerHTML=emS();return;}e.innerHTML=l.map(tRow).join('');}

function render(){updateSt();updateRing();updateBdg();renderCounts();
switch(cur){case'dashboard':rDash();break;case'all':rAll();break;case'today':rToday();break;case'overdue':rOver();break;case'completed':rComp();break;}}

function rDash(){var s=G('d-st')?G('d-st').value:'';var p=G('d-pr')?G('d-pr').value:'';var l=allT.slice();
if(s)l=l.filter(function(t){return t.status===s;});if(p)l=l.filter(function(t){return t.priority===p;});setL('dList',l.slice(0,30));}

function rAll(){var s=G('a-st')?G('a-st').value:'';var p=G('a-pr')?G('a-pr').value:'';
var c=G('a-ca')?G('a-ca').value:'';var q=G('srch')?G('srch').value.toLowerCase():'';var l=allT.slice();
if(s)l=l.filter(function(t){return t.status===s;});if(p)l=l.filter(function(t){return t.priority===p;});
if(c)l=l.filter(function(t){return t.category===c;});
if(q)l=l.filter(function(t){return(t.title+' '+(t.description||'')).toLowerCase().indexOf(q)!==-1;});setL('aL',l);}

function rToday(){var d=td2();var l=allT.filter(function(t){return t.due_date===d&&t.status!=='completed';});
var e=G('tL');if(!e)return;e.innerHTML=l.length?l.map(tRow).join(''):emS('Nothing today!');}

function rOver(){var l=allT.filter(function(t){return isOv(t);});
var e=G('oL');if(!e)return;e.innerHTML=l.length?l.map(tRow).join(''):emS('All caught up!');}

function rComp(){var l=allT.filter(function(t){return t.status==='completed';});
l.sort(function(a,b){return(b.completed_at||'').localeCompare(a.completed_at||'');});setL('cL',l);}

function updateSt(){stV('s-t',stats.total||0);stV('s-d',stats.completed||0);stV('s-p',stats.in_progress||0);stV('s-o',stats.overdue||0);}

function updateRing(){var t=stats.total||0;var c=stats.completed||0;var p=t>0?Math.round(c/t*100):0;
stV('rPct',p+'%');stV('rD',c);stV('rPn',stats.pending||0);stV('rO',stats.overdue||0);
var ring=G('rC');if(ring)ring.style.strokeDashoffset=182-(p/100)*182;}

function renderCounts(){var d=td2();stV('nc-all',allT.filter(function(t){return t.status!=='completed';}).length);
stV('nc-today',allT.filter(function(t){return t.due_date===d&&t.status!=='completed';}).length);
stV('nc-ov',allT.filter(function(t){return isOv(t);}).length);}

function updateBdg(){var u=notifs.filter(function(n){return!n.is_read;}).length;G('nBdg').textContent=u;G('nBdg').style.display=u>0?'flex':'none';}

function renderNL(){var e=G('nList');if(!notifs||notifs.length===0){e.innerHTML='<div class="nde2">No notifications</div>';return;}
var h='';notifs.slice(0,30).forEach(function(n){var pc=n.priority==='high'?'hp2':n.priority==='medium'?'mp2':'';
var ic=n.type==='overdue'||n.type==='upcoming_high'?'fa-exclamation-circle':n.type==='due_today'?'fa-calendar-check':'fa-bell';
h+='<div class="ndi2 '+(n.is_read?'':'ur')+' '+pc+'" onclick="readN('+n.id+')">';
h+='<div class="ni2 '+n.type+'"><i class="fas '+ic+'"></i></div>';
h+='<div class="nt4"><div class="nm2">'+esc(n.message)+'</div><div class="ntm2">'+tAgo(n.created_at)+'</div></div></div>';});
e.innerHTML=h;}

function renderSB(){var ce=G('sbC');if(ce){var h='';cats.forEach(function(c){var cnt=allT.filter(function(t){return t.category===c.name&&t.status!=='completed';}).length;
h+='<button class="nb2" onclick="fCat(\''+esc(c.name)+'\')"><span style="width:8px;height:8px;border-radius:50%;background:'+c.color+';display:inline-block;flex-shrink:0"></span><span class="nt3">'+esc(c.name)+'</span><span class="nc3">'+cnt+'</span></button>';});
ce.innerHTML=h;}
var cp=G('cP');if(cp){var h2='';cats.forEach(function(c){var cnt=allT.filter(function(t){return t.category===c.name&&t.status!=='completed';}).length;
h2+='<div class="pr3" onclick="fCat(\''+esc(c.name)+'\')"><span class="pd2" style="background:'+c.color+'"></span><span class="pn3">'+esc(c.name)+'</span><span class="pc3">'+cnt+'</span></div>';});
cp.innerHTML=h2;}
fillS('a-ca',cats.map(function(c){return{v:c.name,l:c.name};}),'All Categories');
fillS('f-cat',cats.map(function(c){return{v:c.name,l:c.name};}));}

function toggleND(){G('nDrop').classList.toggle('open');}
function readN(id){apiC('/notifications/'+id+'/read','PUT').then(fN);}
function markAll(){apiC('/notifications/read-all','PUT').then(function(){fN();toast('Done','ok');});}
function clearR(){apiC('/notifications/clear-read','DELETE').then(function(){fN();toast('Cleared','ok');});}

function openTM(t){['f-id','f-title','f-desc','f-date','f-time','f-asn','f-tags','f-notes'].forEach(function(id){var e=G(id);if(e)e.value='';});
G('f-pri').value='medium';G('f-status').value='pending';G('f-rem').value=settings.default_reminder_medium||30;
G('mTi').textContent='New Task';fillS('f-cat',cats.map(function(c){return{v:c.name,l:c.name};}));
if(t){G('mTi').textContent='Edit';G('f-id').value=t.id;G('f-title').value=t.title||'';G('f-desc').value=t.description||'';
G('f-cat').value=t.category||'General';G('f-pri').value=t.priority||'medium';G('f-date').value=t.due_date||'';
G('f-time').value=t.due_time||'';G('f-status').value=t.status||'pending';G('f-rem').value=t.reminder_mins||30;
G('f-asn').value=t.assigned_to||'';G('f-tags').value=pT(t.tags).join(', ');G('f-notes').value=t.notes||'';}
G('tOv').classList.add('open');setTimeout(function(){G('f-title').focus();},120);}

function closeTM(){G('tOv').classList.remove('open');}
function editT(id){var t=allT.filter(function(x){return x.id===id;})[0];if(t)openTM(t);}

G('f-pri').addEventListener('change',function(){var rm={high:settings.default_reminder_high||15,medium:settings.default_reminder_medium||30,low:settings.default_reminder_low||60};G('f-rem').value=rm[this.value]||30;});

function saveT(){var id=G('f-id').value;var title=G('f-title').value.trim();if(!title){toast('Title needed','er');return;}
var tagsR=G('f-tags').value;var tags=tagsR?tagsR.split(',').map(function(s){return s.trim();}).filter(Boolean):[];
var payload={title:title,description:G('f-desc').value,category:G('f-cat').value,priority:G('f-pri').value,
status:G('f-status').value,due_date:G('f-date').value||null,due_time:G('f-time').value||null,
reminder_mins:parseInt(G('f-rem').value),assigned_to:G('f-asn').value,tags:tags,notes:G('f-notes').value};
var method=id?'PUT':'POST';var url=id?'/tasks/'+id:'/tasks';
apiC(url,method,payload).then(function(r){if(r&&!r.error){toast(id?'Updated':'Created!','ok');
showAP({type:'created',priority:payload.priority,message:'"'+title+'" '+(id?'updated':'created'),created_at:new Date().toISOString()},payload.priority);
closeTM();loadAll();}});}

function togSt(id,e){e.stopPropagation();var t=allT.filter(function(x){return x.id===id;})[0];if(!t)return;
var ns=t.status==='completed'?'pending':'completed';apiC('/tasks/'+id,'PUT',{status:ns}).then(function(r){
if(r){toast(ns==='completed'?'Done!':'Reopened','ok');if(ns==='completed')playS('high');loadAll();}});}

function delT(id,e){e.stopPropagation();var t=allT.filter(function(x){return x.id===id;})[0];
if(!t||!confirm('Delete "'+t.title+'"?'))return;apiC('/tasks/'+id,'DELETE').then(function(){toast('Deleted','ok');loadAll();});}

function openCatM(){G('cOv').classList.add('open');}
function closeCM(){G('cOv').classList.remove('open');}
function saveCat(){var n=G('cn').value.trim();if(!n){toast('Name needed','er');return;}
apiC('/categories','POST',{name:n,color:G('cc').value}).then(function(r){
if(r&&!r.error){toast('Created','ok');closeCM();G('cn').value='';loadAll();}else{toast('Error','er');}});}

function openSM(){G('sOv').classList.add('open');}
function closeSM(){G('sOv').classList.remove('open');}

function go(p,btn){cur=p;document.querySelectorAll('.pg').forEach(function(x){x.classList.remove('act');});
document.querySelectorAll('.nb2').forEach(function(x){x.classList.remove('act');});
var pg=G('pg-'+p);if(pg)pg.classList.add('act');if(btn)btn.classList.add('act');render();
if(window.innerWidth<=768)G('sidebar').classList.remove('mob');}

function fCat(n){go('all',document.querySelector('[data-p="all"]'));setTimeout(function(){var s=G('a-ca');if(s){s.value=n;rAll();}},50);}

var srT;function onSrch(){clearTimeout(srT);srT=setTimeout(function(){if(cur!=='all')go('all',document.querySelector('[data-p="all"]'));else rAll();},300);}
function toggleSB(){var s=G('sidebar');if(window.innerWidth<=768)s.classList.toggle('mob');else s.classList.toggle('slim');}
function toggleTheme(){document.body.classList.toggle('dark');G('thI').className=document.body.classList.contains('dark')?'fas fa-sun':'fas fa-moon';
localStorage.setItem('tp-t',document.body.classList.contains('dark')?'dark':'light');}
function loadTheme(){if(localStorage.getItem('tp-t')==='dark'){document.body.classList.add('dark');G('thI').className='fas fa-sun';}}
function setGreet(){var h=new Date().getHours();stV('greet',h<12?'Good Morning!':h<17?'Good Afternoon!':'Good Evening!');}

function toast(m,tp){tp=tp||'ok';var w=G('tw');var e=document.createElement('div');e.className='tst '+tp;
var ic={ok:'fa-check-circle',er:'fa-times-circle',wa:'fa-exclamation-triangle'}[tp]||'fa-info-circle';
e.innerHTML='<i class="fas '+ic+' tsti"></i><span class="tstm">'+m+'</span><button class="tstc" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>';
w.appendChild(e);setTimeout(function(){e.style.opacity='0';setTimeout(function(){e.remove();},300);},4000);}

document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();G('srch').focus();}
if((e.ctrlKey||e.metaKey)&&e.key==='n'){e.preventDefault();openTM();}
if(e.key==='Escape')document.querySelectorAll('.ov3.open,.ndrop2.open').forEach(function(el){el.classList.remove('open');});});
document.addEventListener('click',function(e){if(!e.target.closest('#bellBtn')&&!e.target.closest('#nDrop'))G('nDrop').classList.remove('open');});
</script>
</body>
</html>'''