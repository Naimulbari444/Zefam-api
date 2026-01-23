import os
import uuid
import time
import requests
import threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

active_tasks = {}  # {task_id: {'running': True}}
logs = ["> System ready."]
site_public_url = ""
keep_alive_running = False
keep_alive_thread = None

# নতুন API URL গুলা
API_URL = "https://app.zefame.com/api_free.php?action=config"
ORDER_URL = "https://app.zefame.com/api_free.php?action=order"
CHECK_VIDEO_URL = "https://app.zefame.com/api_free.php?action=checkVideoId"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    return " ".join(text.split()).strip()

def get_timer_display(timer_sec):
    if timer_sec >= 86400:  # 24h+
        return "24h"
    elif timer_sec >= 3600:   # hours
        hours = timer_sec // 3600
        mins = (timer_sec % 3600) // 60
        return f"{hours}h" if mins == 0 else f"{hours}h {mins}m"
    else:
        minutes = timer_sec // 60
        return f"{minutes}m"

# Smart Keep Alive
def smart_keep_alive():
    global keep_alive_running, site_public_url
    ping_url = site_public_url.rstrip('/') + "/get_logs"
    while keep_alive_running:
        if any(task.get('running', False) for task in active_tasks.values()):
            try:
                requests.get(ping_url, timeout=15)
            except:
                pass
        else:
            break
        time.sleep(420)

    keep_alive_running = False
    logs.append("> [SYSTEM] Keep-alive stopped")

def start_keep_alive():
    global keep_alive_running, keep_alive_thread
    if not keep_alive_running:
        keep_alive_running = True
        keep_alive_thread = threading.Thread(target=smart_keep_alive, daemon=True)
        keep_alive_thread.start()
        logs.append("> [SYSTEM] Keep-alive activated")

def stop_keep_alive():
    global keep_alive_running
    keep_alive_running = False

def run_automation(service_id, service_name, video_link, target):
    task_id = str(service_id)
    
    if task_id in active_tasks and active_tasks[task_id].get('running'):
        logs.append(f"> [INFO] {service_name} already running")
        return
    
    active_tasks[task_id] = {'running': True}
    logs.append(f"> [STARTING] {service_name}")
    start_keep_alive()

    video_id = ""
    try:
        res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=20)
        data = res.json()
        video_id = data.get("data", {}).get("videoId", "")
    except Exception as e:
        logs.append("> [ERROR] Failed to get Video ID")

    if not video_id:
        logs.append("> [ERROR] Invalid Video ID! Check link.")
        del active_tasks[task_id]
        if not any(t.get('running') for t in active_tasks.values()):
            stop_keep_alive()
        return

    logs.append(f"> [VIDEO ID] {video_id}")

    target_num = int(target) if target and target.isdigit() else 999999
    order_count = 0
    error_count = 0
    max_errors = 15

    while active_tasks.get(task_id, {}).get('running') and order_count < target_num:
        try:
            payload = {"service": service_id, "link": video_link, "uuid": str(uuid.uuid4()), "videoId": video_id}
            res = requests.post(ORDER_URL, data=payload, headers=headers, timeout=30)
            order = res.json()

            if order.get("success"):
                order_count += 1
                error_count = 0
                logs.append(f"> SUCCESS ({order_count}/{target_num}) {service_name}")
            else:
                msg = order.get("message", "Unknown")
                logs.append(f"> WAIT: {msg}")

            next_av = order.get("data", {}).get("nextAvailable")
            if next_av and str(next_av).isdigit():
                wait_time = max(int(next_av) - int(time.time()), 5)
                logs.append(f"> DYNAMIC WAIT: {wait_time}s")
            else:
                wait_time = 30
                logs.append(f"> DEFAULT WAIT: {wait_time}s")

            for _ in range(wait_time):
                if not active_tasks.get(task_id, {}).get('running'):
                    logs.append(f"> [STOPPED] {service_name}")
                    break
                time.sleep(1)

        except Exception as e:
            error_count += 1
            logs.append(f"> [ORDER ERROR] Retry {error_count}/{max_errors}")
            if error_count >= max_errors:
                logs.append("> [STOPPED] Too many errors")
                active_tasks[task_id]['running'] = False
                break
            time.sleep(30)

    if task_id in active_tasks:
        del active_tasks[task_id]
    logs.append(f"> [FINISHED] {service_name} - Sent: {order_count}")

    if not any(t.get('running') for t in active_tasks.values()):
        stop_keep_alive()

@app.route('/')
def index():
    global site_public_url
    current_url = request.host_url.rstrip('/')
    if not site_public_url:
        site_public_url = current_url
        logs.append(f"> Domain Sync: {site_public_url}")

    processed = []
    try:
        api_res = requests.get(API_URL, headers=headers, timeout=20)
        api_data = api_res.json()
        platforms_data = api_data.get('data', {})

        for platform in ['tiktok', 'instagram', 'twitter', 'facebook', 'youtube', 'telegram']:
            if platform in platforms_data:
                processed.append({"id": "", "name": f"--- {platform.upper()} ---", "clickable": False})
                for s in platforms_data[platform].get('services', []):
                    raw_name = s.get('name', '').strip()
                    name = clean_and_translate(raw_name)
                    qty = s.get('quantity', '?')
                    timer_sec = s.get('timerSeconds', 0)
                    timer_display = get_timer_display(timer_sec)

                    # Views সার্ভিসের নাম খালি থাকলে "Views" যোগ করো
                    if not name:
                        name = "Views"

                    processed.append({
                        "id": s.get('id'),
                        "name": f"   {platform.capitalize()} {name} [Qty: {qty}] ({timer_display})",
                        "clickable": True
                    })
    except Exception as e:
        logs.append("> [API FAILED] Loading fallback")
        processed = [
            {"id": "", "name": "--- TIKTOK ---", "clickable": False},
            {"id": "229", "name": "   Tiktok Views [Qty: 100] (5m)", "clickable": True},
            {"id": "228", "name": "   Tiktok Followers [Qty: 10] (24h)", "clickable": True},
            {"id": "232", "name": "   Tiktok Likes [Qty: 10] (5m)", "clickable": True},
            {"id": "235", "name": "   Tiktok Shares [Qty: 20] (1h)", "clickable": True},
            {"id": "236", "name": "   Tiktok Favorites [Qty: 30] (20m)", "clickable": True},
        ]

    return render_template('index.html', services=processed)

@app.route('/start', methods=['POST'])
def start_bot():
    sid = request.form.get('service_id')
    if sid and sid in active_tasks and active_tasks[sid].get('running'):
        return jsonify({"status": "already_running"})
    
    threading.Thread(target=run_automation, args=(
        sid,
        request.form.get('service_name'),
        request.form.get('video_link'),
        request.form.get('target')
    ), daemon=True).start()
    
    return jsonify({"status": "started"})

@app.route('/stop_all', methods=['POST'])
def stop_all():
    for tid in list(active_tasks.keys()):
        active_tasks[tid]['running'] = False
    active_tasks.clear()
    stop_keep_alive()
    logs.append("> [INFO] All tasks stopped")
    return jsonify({"status": "stopped"})

@app.route('/get_logs')
def get_logs():
    running = len(active_tasks)
    return jsonify({"logs": logs[-30:], "running_count": running})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10347))
    app.run(host='0.0.0.0', port=port)