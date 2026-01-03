import os, uuid, time, requests, threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

logs = []
is_running = False

API_URL = "https://zefame-free.com/api_free.php?action=config"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://zefame-free.com",
    "Referer": "https://zefame-free.com/",
    "X-Requested-With": "XMLHttpRequest"
}

def run_automation(service_id, video_link, target):
    global logs, is_running
    is_running = True
    logs = ["> Initializing Bot..."]
    
    try:
        res = requests.post("https://zefame-free.com/api_free.php?action=checkVideoId", 
                          data={"link": video_link}, headers=headers, timeout=15)
        video_id = res.json().get("data", {}).get("videoId")
        if not video_id:
            logs.append("❌ Error: Invalid Link! Video ID not found.")
            is_running = False
            return
        logs.append(f"✅ Video ID Found: {video_id}")
    except:
        logs.append("❌ API Connection Error. Try again later.")
        is_running = False
        return

    order_count = 0
    while is_running: # is_running False হলে লুপ বন্ধ হয়ে যাবে
        order_count += 1
        try:
            logs.append(f"🚀 Sending Order #{order_count}...")
            order = requests.post("https://zefame-free.com/api_free.php?action=order", 
                                data={"service": service_id, "link": video_link, 
                                      "uuid": str(uuid.uuid4()), "videoId": video_id},
                                headers=headers, timeout=20)

            if order.status_code != 200 or not order.text.strip():
                logs.append("⚠️ Empty response. Waiting 30s...")
                time.sleep(30); continue

            try:
                result = order.json()
            except:
                logs.append("❌ JSON Error. Retrying in 30s...")
                time.sleep(30); continue
            
            if result.get("success"):
                logs.append(f"✅ Order #{order_count}: Success!")
            else:
                logs.append(f"⚠️ Server: {result.get('message', 'Failed')}")

            if target and order_count >= int(target):
                logs.append("🎯 Target reached. Task completed.")
                break
            
            next_av = result.get("data", {}).get("nextAvailable")
            if next_av:
                wait_time = int(next_av) - int(time.time())
                if wait_time > 0:
                    logs.append(f"⏳ Sleep: Waiting {wait_time} seconds...")
                    # স্টপ বাটন দ্রুত কাজ করার জন্য ছোট ছোট স্লিপ দেওয়া হয়েছে
                    for _ in range(wait_time + 3):
                        if not is_running: break
                        time.sleep(1)
            else:
                time.sleep(10)
                
        except Exception as e:
            logs.append(f"❌ Error: {str(e)}")
            time.sleep(10)
    
    is_running = False
    logs.append("> Process Stopped.")

@app.route('/')
def index():
    target_services = {229: "TikTok Views", 228: "TikTok Followers", 232: "TikTok Likes", 235: "TikTok Shares", 236: "TikTok Favorites"}
    processed = []
    try:
        resp = requests.get(API_URL, headers=headers, timeout=10).json()
        api_serv = resp.get('data', {}).get('tiktok', {}).get('services', [])
        status_map = {s.get('id'): s.get('available') for s in api_serv}
        for sid, name in target_services.items():
            ok = status_map.get(sid, False)
            processed.append({"id": sid, "name": name, "status": "WORKING" if ok else "DOWN", "is_ok": ok})
    except:
        processed = [{"id": k, "name": v, "status": "OFFLINE", "is_ok": False} for k, v in target_services.items()]
    return render_template('index.html', services=processed)

@app.route('/start', methods=['POST'])
def start_bot():
    global is_running
    if is_running: return jsonify({"status": "running"})
    t = threading.Thread(target=run_automation, args=(request.form.get('service_id'), request.form.get('video_link'), request.form.get('target')))
    t.daemon = True
    t.start()
    return jsonify({"status": "started"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    global is_running
    is_running = False
    return jsonify({"status": "stopping"})

@app.route('/get_logs')
def get_logs():
    return jsonify({"logs": logs, "is_running": is_running})

#if __name__ == '__main__':
   # app.run(host='0.0.0.0', port=5044)
