import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# মাল্টি-টাস্কিং এবং লগ স্টোর করার সিস্টেম
active_tasks = {}
logs = ["> System online. Waiting for start command..."]

# API URLs
API_URL = "https://zefame-free.com/api_free.php?action=config"
ORDER_URL = "https://zefame-free.com/api_free.php?action=order"
CHECK_VIDEO_URL = "https://zefame-free.com/api_free.php?action=checkVideoId"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://zefame-free.com",
    "Referer": "https://zefame-free.com/"
}

# ৩ মিনিট পর পর নিজেকে রিকোয়েস্ট পাঠানোর ফাংশন (ডাইনামিক)
def keep_alive_ping():
    while True:
        # যদি অন্তত একটি টাস্ক সচল থাকে, তবেই পিং করবে
        is_any_running = any(task['running'] for task in active_tasks.values())
        
        if is_any_running:
            try:
                # লোকালহোস্টে কল পাঠাবে যাতে ডোমেইন বদলালেও সমস্যা না হয়
                requests.get("http://127.0.0.1:10315/", timeout=10)
                logs.append("📡 Keep-alive: 3-min heartbeat sent.")
            except:
                pass
            time.sleep(180) # ৩ মিনিট বিরতি
        else:
            time.sleep(10) # কোনো কাজ না থাকলে চেক করার বিরতি

def run_automation(service_id, service_name, video_link, target):
    task_id = service_id
    active_tasks[task_id]['running'] = True
    logs.append(f"🚀 [STARTED] {service_name}")
    
    try:
        v_res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=15).json()
        video_id = v_res.get("data", {}).get("videoId")
        if not video_id:
            logs.append(f"❌ {service_name}: Video ID not found!")
            active_tasks[task_id]['running'] = False
            return
    except:
        logs.append(f"❌ {service_name}: Connection failed.")
        active_tasks[task_id]['running'] = False
        return

    order_count = 0
    target_num = int(target) if target else 999999

    while active_tasks.get(task_id) and active_tasks[task_id]['running'] and order_count < target_num:
        order_count += 1
        try:
            payload = {
                "service": service_id, 
                "link": video_link, 
                "uuid": str(uuid.uuid4()), 
                "videoId": video_id
            }
            order = requests.post(ORDER_URL, data=payload, headers=headers, timeout=25).json()
            
            if order.get("success"):
                logs.append(f"✅ {service_name} Order #{order_count}: Success!")
            else:
                logs.append(f"⚠️ {service_name}: {order.get('message', 'Limit waiting')}")

            if order_count >= target_num: break
            
            next_av = order.get("data", {}).get("nextAvailable")
            current_time = int(time.time())
            wait_time = (int(next_av) - current_time) if next_av else 300
            
            if wait_time > 0:
                logs.append(f"⏳ {service_name}: Sleeping {wait_time}s...")
                for _ in range(wait_time):
                    if not active_tasks[task_id]['running']: break
                    time.sleep(1)
            else:
                time.sleep(10) # ডিফল্ট গ্যাপ
                
        except Exception as e:
            time.sleep(20)
    
    active_tasks[task_id]['running'] = False
    logs.append(f"🎯 [FINISHED] {service_name}")

@app.route('/')
def index():
    target_services = {
        229: "TikTok Views", 
        228: "TikTok Followers", 
        232: "TikTok Likes", 
        235: "TikTok Shares", 
        236: "TikTok Favorites"
    }
    processed = []
    try:
        api_data = requests.get(API_URL, headers=headers, timeout=10).json()
        status_map = {s.get('id'): s.get('available') for s in api_data.get('data', {}).get('tiktok', {}).get('services', [])}
        for sid, name in target_services.items():
            ok = status_map.get(sid, False)
            processed.append({"id": sid, "name": name, "status": "WORKING" if ok else "DOWN", "is_ok": ok})
    except:
        processed = [{"id": k, "name": v, "status": "UNKNOWN", "is_ok": True} for k, v in target_services.items()]
    return render_template('index.html', services=processed)

@app.route('/start', methods=['POST'])
def start_bot():
    sid = request.form.get('service_id')
    sname = request.form.get('service_name')
    if sid in active_tasks and active_tasks[sid]['running']:
        return jsonify({"status": "already_running"})
    
    active_tasks[sid] = {'running': True}
    threading.Thread(target=run_automation, args=(sid, sname, request.form.get('video_link'), request.form.get('target')), daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/stop_all', methods=['POST'])
def stop_all():
    for sid in active_tasks:
        active_tasks[sid]['running'] = False
    return jsonify({"status": "all_stopped"})

@app.route('/get_logs')
def get_logs():
    running_count = sum(1 for task in active_tasks.values() if task['running'])
    global logs
    if len(logs) > 50: logs = logs[-40:] # লগ ক্লিন রাখা
    return jsonify({"logs": logs, "running_count": running_count})

if __name__ == '__main__':
    # ব্যাকগ্রাউন্ড পিং স্টার্ট
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    # প্যানেল পোর্ট
    app.run(host='0.0.0.0', port=10715)
