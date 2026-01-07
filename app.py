import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

active_tasks = {}  # {task_id: {'running': True}}
logs = ["> System ready."]
site_public_url = ""
keep_alive_running = False
keep_alive_thread = None

API_URL = "https://zefame-free.com/api_free.php?action=config"
ORDER_URL = "https://zefame-free.com/api_free.php?action=order"
CHECK_VIDEO_URL = "https://zefame-free.com/api_free.php?action=checkVideoId"

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

# Keep Alive - শুধু অ্যাকটিভ টাস্ক থাকলে চলবে
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
        time.sleep(420)  # প্রতি ৭ মিনিটে (Render-এ সেফ)

    keep_alive_running = False
    logs.append("> [SYSTEM] Keep-alive stopped (no active tasks)")

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
    
    # Keep alive চালু করো
    start_keep_alive()

    # Video ID চেক
    video_id = ""
    try:
        res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=20)
        data = res.json()
        video_id = data.get("data", {}).get("videoId", "")
    except:
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
    max_errors = 15  # বেশি এরর হলে অটো স্টপ

    while active_tasks.get(task_id, {}).get('running') and order_count < target_num:
        try:
            payload = {"service": service_id, "link": video_link, "uuid": str(uuid.uuid4()), "videoId": video_id}
            res = requests.post(ORDER_URL, data=payload, headers=headers, timeout=30)
            order = res.json()

            if order.get("success"):
                order_count += 1
                error_count = 0  # রিসেট
                logs.append(f"> SUCCESS ({order_count}/{target_num}) {service_name}")
            else:
                msg = order.get("message", "Unknown")
                logs.append(f"> WAIT: {msg}")

            # nextAvailable ডিটেক্ট করে ডাইনামিক ওয়েট
            next_av = order.get("data", {}).get("nextAvailable")
            if next_av and str(next_av).isdigit():
                wait_time = max(int(next_av) - int(time.time()), 5)
                logs.append(f"> DYNAMIC WAIT: {wait_time}s")
            else:
                wait_time = 30
                logs.append(f"> DEFAULT WAIT: {wait_time}s")

            # ওয়েট লুপ
            for _ in range(wait_time):
                if not active_tasks.get(task_id, {}).get('running'):
                    logs.append(f"> [STOPPED] {service_name}")
                    break
                time.sleep(1)

        except Exception as e:
            error_count += 1
            logs.append(f"> [ORDER ERROR] Retry {error_count}/{max_errors}")
            if error_count >= max_errors:
                logs.append("> [STOPPED] Too many errors - Task stopped")
                active_tasks[task_id]['running'] = False
                break
            time.sleep(30)

    # টাস্ক শেষ
    if task_id in active_tasks:
        del active_tasks[task_id]
    logs.append(f"> [FINISHED] {service_name} - Sent: {order_count}")

    # শেষ টাস্ক হলে keep-alive বন্ধ
    if not any(t.get('running') for t in active_tasks.values()):
        stop_keep_alive()
        logs.append("> [SYSTEM] Keep-alive deactivated")

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
        for platform in ['tiktok', 'instagram', 'facebook', 'youtube', 'twitter', 'telegram']:
            if platform in platforms_data:
                processed.append({"id": "", "name": f"--- {platform.upper()} ---", "clickable": False})
                for s in platforms_data[platform].get('services', []):
                    name = clean_and_translate(s.get('name', ''))
                    if platform == 'tiktok' and "Views" not in name and all(x not in name for x in ["Likes", "Followers", "Shares", "Favorites"]):
                        name += " Views"
                    processed.append({
                        "id": s.get('id'),
                        "name": f"   {platform.capitalize()} {name} [Qty: {s.get('quantity', '?')}] ({s.get('timer', 'N/A')})",
                        "clickable": True
                    })
    except:
        logs.append("> [API FAILED] Loading fallback services")
        processed = [
            {"id": "", "name": "--- TIKTOK ---", "clickable": False},
            {"id": "229", "name": "   Tiktok Views [Qty: 1000] (5 min)", "clickable": True},
            {"id": "230", "name": "   Tiktok Likes [Qty: 100] (Instant)", "clickable": True},
            {"id": "231", "name": "   Tiktok Followers [Qty: 10] (24h)", "clickable": True},
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
    port = int(os.environ.get('PORT', 10357))
    app.run(host='0.0.0.0', port=port)