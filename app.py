import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

active_tasks = {}  # {task_id: {'running': True}}
logs = ["> System ready."]
site_public_url = ""
keep_alive_running = False  # গ্লোবাল ফ্ল্যাগ
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

# সুপার অপ্টিমাইজড Keep Alive — শুধু অ্যাকটিভ টাস্ক থাকলে চলবে
def smart_keep_alive():
    global keep_alive_running, site_public_url
    ping_url = site_public_url.rstrip('/') + "/get_logs"
    
    while keep_alive_running:
        # ডাবল চেক: যদি এখনো অ্যাকটিভ টাস্ক থাকে তবেই পিং
        if any(task.get('running', False) for task in active_tasks.values()):
            try:
                requests.get(ping_url, timeout=15)
            except:
                pass
        # যদি কোনো টাস্ক না থাকে → লুপ থেকে বের হয়ে যাবে (থ্রেড শেষ)
        else:
            break
        
        time.sleep(420)  # প্রতি ৭ মিনিটে (Render-এ সেফ এবং অপ্টিমাল)

    # লুপ শেষ হলে ফ্ল্যাগ অফ
    keep_alive_running = False
    logs.append("> [SYSTEM] Keep-alive stopped (no active tasks)")

def start_keep_alive_if_needed():
    global keep_alive_running, keep_alive_thread
    if not keep_alive_running and any(task.get('running', False) for task in active_tasks.values()):
        keep_alive_running = True
        keep_alive_thread = threading.Thread(target=smart_keep_alive, daemon=True)
        keep_alive_thread.start()
        logs.append("> [SYSTEM] Keep-alive started")

def stop_keep_alive():
    global keep_alive_running
    keep_alive_running = False
    logs.append("> [SYSTEM] Keep-alive stopped by user/action")

def run_automation(service_id, service_name, video_link, target):
    task_id = str(service_id)
    
    if task_id in active_tasks and active_tasks[task_id].get('running'):
        logs.append(f"> [INFO] {service_name} already running")
        return
    
    active_tasks[task_id] = {'running': True}
    logs.append(f"> [STARTING] {service_name}")
    
    # প্রথম টাস্ক শুরু হলে keep-alive চালু করো
    start_keep_alive_if_needed()

    # বাকি অটোমেশন লজিক (একই)
    video_id = ""
    try:
        res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=20)
        data = res.json()
        video_id = data.get("data", {}).get("videoId", "")
    except:
        logs.append("> [ERROR] Failed to check video ID")

    if not video_id:
        logs.append("> [ERROR] Video ID not found!")
        del active_tasks[task_id]
        start_keep_alive_if_needed()  # চেক করে বন্ধ করবে যদি দরকার হয়
        return

    logs.append(f"> [VIDEO ID] {video_id}")

    target_num = int(target) if target and target.isdigit() else 999999
    order_count = 0

    while active_tasks.get(task_id, {}).get('running') and order_count < target_num:
        try:
            payload = {"service": service_id, "link": video_link, "uuid": str(uuid.uuid4()), "videoId": video_id}
            res = requests.post(ORDER_URL, data=payload, headers=headers, timeout=30)
            order = res.json()

            if order.get("success"):
                order_count += 1
                logs.append(f"> SUCCESS ({order_count}/{target_num}) {service_name}")
            else:
                msg = order.get("message", "Wait")
                logs.append(f"> WAIT: {msg}")

            next_av = order.get("data", {}).get("nextAvailable")
            wait_time = max(int(next_av) - int(time.time()), 5) if next_av and next_av.isdigit() else 30

            if order_count < target_num:
                logs.append(f"> SLEEP: {wait_time}s")
                for _ in range(wait_time):
                    if not active_tasks.get(task_id, {}).get('running'):
                        logs.append(f"> [STOPPED] {service_name}")
                        break
                    time.sleep(1)
        except:
            logs.append("> [ORDER ERROR] Retrying...")
            time.sleep(30)

    # টাস্ক শেষ
    if task_id in active_tasks:
        del active_tasks[task_id]
    logs.append(f"> [FINISHED] {service_name} - Total: {order_count}")

    # শেষ টাস্ক হলে keep-alive বন্ধের চেক
    if not any(task.get('running', False) for task in active_tasks.values()):
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
        logs.append("> [API FAILED] Using fallback")
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
    global keep_alive_running
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
    port = int(os.environ.get('PORT', 10356))
    app.run(host='0.0.0.0', port=port)