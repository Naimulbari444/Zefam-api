import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

logs = []
is_running = False

# API URLs
API_URL = "https://zefame-free.com/api_free.php?action=config"
ORDER_URL = "https://zefame-free.com/api_free.php?action=order"
CHECK_VIDEO_URL = "https://zefame-free.com/api_free.php?action=checkVideoId"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://zefame-free.com",
    "Referer": "https://zefame-free.com/"
}

# ৩ মিনিট পর পর নিজেকে পিং করার ফাংশন
def keep_alive_ping(site_url):
    global is_running
    while is_running:
        try:
            time.sleep(180) # ১৮০ সেকেন্ড = ৩ মিনিট
            if is_running:
                requests.get(site_url, timeout=10)
                logs.append("📡 Keep-alive: 3-minute self-ping sent.")
        except: pass

def run_automation(service_id, video_link, target, site_url):
    global logs, is_running
    is_running = True
    threading.Thread(target=keep_alive_ping, args=(site_url,), daemon=True).start()
    logs = ["> Bot started. Verifying Video..."]
    
    try:
        v_res = requests.post(CHECK_VIDEO_URL, data={"link": video_link}, headers=headers, timeout=15).json()
        video_id = v_res.get("data", {}).get("videoId")
        if not video_id:
            logs.append("❌ Error: Invalid TikTok link.")
            is_running = False
            return
    except:
        logs.append("❌ Connection Error.")
        is_running = False
        return

    order_count = 0
    target_num = int(target) if target else 999999

    while is_running and order_count < target_num:
        order_count += 1
        try:
            logs.append(f"🚀 Sending Order #{order_count}...")
            payload = {"service": service_id, "link": video_link, "uuid": str(uuid.uuid4()), "videoId": video_id}
            order = requests.post(ORDER_URL, data=payload, headers=headers, timeout=25).json()
            
            if order.get("success"):
                logs.append(f"✅ Order #{order_count}: Success!")
            else:
                logs.append(f"⚠️ Msg: {order.get('message', 'Waiting')}")

            if order_count >= target_num: break
            
            next_av = order.get("data", {}).get("nextAvailable")
            wait_time = (int(next_av) - int(time.time())) if next_av else 300
            if wait_time > 0:
                logs.append(f"⏳ Sleeping {wait_time}s...")
                for _ in range(wait_time):
                    if not is_running: break
                    time.sleep(1)
        except: time.sleep(15)
    
    is_running = False
    logs.append("> Task Finished.")

@app.route('/')
def index():
    # সবগুলো সার্ভিস আইডি এখানে দেওয়া হলো
    target_services = {
        229: "TikTok Video Views", 
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
    global is_running
    if is_running: return jsonify({"status": "running"})
    t = threading.Thread(target=run_automation, args=(request.form.get('service_id'), request.form.get('video_link'), request.form.get('target'), request.host_url))
    t.daemon = True
    t.start()
    return jsonify({"status": "started"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    global is_running
    is_running = False
    return jsonify({"status": "stopped"})

@app.route('/get_logs')
def get_logs():
    return jsonify({"logs": logs, "is_running": is_running})

#if __name__ == '__main__':
   # app.run(host='0.0.0.0', port=11515)
