import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

active_tasks = {}
logs = ["> System online. Waiting for command..."]
site_public_url = ""

API_URL = "https://zefame-free.com/api_free.php?action=config"
ORDER_URL = "https://zefame-free.com/api_free.php?action=order"
CHECK_VIDEO_URL = "https://zefame-free.com/api_free.php?action=checkVideoId"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://zefame-free.com",
    "Referer": "https://zefame-free.com/",
    "X-Requested-With": "XMLHttpRequest"
}

TRANS_MAP = {
    "Vues": "Views", "Abonnés": "Followers", "Partages": "Shares",
    "Favoris": "Favorites", "J'aime": "Likes", "Membres": "Members",
    "Vidéos": "Videos", "Gratuits": "", "Free": "", "Chaîne": "Channel",
    "Story": "Story", "Tweet": "Tweet", "Retweets": "Retweets", "Post": "Post"
}

def clean_and_translate(text):
    for fr, en in TRANS_MAP.items():
        text = text.replace(fr, en)
    return " ".join(text.split())

def keep_alive_ping():
    global site_public_url
    while True:
        if site_public_url:
            try: requests.get(site_public_url, headers=headers, timeout=10)
            except: pass
            time.sleep(120)
        else:
            time.sleep(10)

def run_automation(service_id, service_name, video_link, target):
    task_id = service_id
    active_tasks[task_id] = {'running': True}
    
    logs.append(f"> [STARTING] {service_name}")
    
    # ভিডিও আইডি চেক করার লজিক
    video_id = ""
    try:
        v_res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=15).json()
        video_id = v_res.get("data", {}).get("videoId", "")
    except: pass
    
    # আইডি না পেলে কাজ বন্ধ করে দিবে
    if not video_id:
        logs.append(f"> [ERROR] Video ID not found! Please change the link.")
        active_tasks[task_id]['running'] = False
        return

    logs.append(f"> [VIDEO ID]: {video_id}")
    
    target_num = int(target) if target and target.isdigit() else 999999
    order_count = 0
    
    while active_tasks.get(task_id) and active_tasks[task_id]['running'] and order_count < target_num:
        try:
            payload = {"service": service_id, "link": video_link, "uuid": str(uuid.uuid4()), "videoId": video_id}
            order = requests.post(ORDER_URL, data=payload, headers=headers, timeout=25).json()
            
            if order.get("success"):
                order_count += 1
                logs.append(f"> OK: {service_name} Success ({order_count}/{target_num})")
                if order_count >= target_num: break
            else:
                msg = order.get('message', 'Wait')
                logs.append(f"> WAIT: {service_name} - {msg}")

            # ডাইনামিক স্লিপ টাইম
            next_av = order.get("data", {}).get("nextAvailable")
            if next_av:
                wait_time = int(next_av) - int(time.time())
                wait_time = max(wait_time, 3)
            else:
                wait_time = 30

            if order_count < target_num:
                logs.append(f"> SLEEP: {wait_time}s")
                for _ in range(wait_time):
                    if task_id not in active_tasks or not active_tasks[task_id]['running']:
                        logs.append(f"> [STOPPED] {service_name}")
                        return 
                    time.sleep(1)
        except:
            time.sleep(30)
    
    if task_id in active_tasks: active_tasks[task_id]['running'] = False
    logs.append(f"> FINISHED: {service_name}")

@app.route('/')
def index():
    global site_public_url
    if not site_public_url or site_public_url != request.host_url:
        site_public_url = request.host_url
        logs.append(f"> Domain Sync: {site_public_url}")
    
    processed = []
    try:
        api_data = requests.get(API_URL, headers=headers, timeout=10).json()
        platforms_data = api_data.get('data', {})
        for p_key in ['tiktok', 'instagram', 'facebook', 'youtube', 'twitter', 'telegram']:
            if p_key in platforms_data:
                processed.append({"id": "", "name": f"--- {p_key.upper()} ---", "clickable": False})
                for s in platforms_data[p_key].get('services', []):
                    raw_name = s.get('name', '')
                    translated = clean_and_translate(raw_name)
                    if p_key == 'tiktok' and all(k not in translated for k in ["Followers", "Likes", "Shares", "Favorites"]):
                        if "Views" not in translated: translated += " Views"
                    
                    processed.append({
                        "id": s.get('id'),
                        "name": f"   {p_key.capitalize()} {translated} [Qty: {s.get('quantity', '0')}] ({s.get('timer', 'N/A')})",
                        "clickable": True
                    })
    except:
        processed = [{"id": 229, "name": "   Tiktok Views [Qty: 1000] (5 min)", "clickable": True}]
    
    return render_template('index.html', services=processed)

@app.route('/start', methods=['POST'])
def start_bot():
    sid = request.form.get('service_id')
    if sid in active_tasks and active_tasks[sid]['running']: return jsonify({"status": "running"})
    active_tasks[sid] = {'running': True}
    threading.Thread(target=run_automation, args=(sid, request.form.get('service_name'), request.form.get('video_link'), request.form.get('target')), daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/stop_all', methods=['POST'])
def stop_all():
    for sid in list(active_tasks.keys()): active_tasks[sid]['running'] = False
    return jsonify({"status": "stopped"})

@app.route('/get_logs')
def get_logs():
    running_count = sum(1 for task in active_tasks.values() if task.get('running'))
    return jsonify({"logs": logs[-25:], "running_count": running_count})

if __name__ == '__main__':
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    app.run(host='0.0.0.0', port=16424)
