import os
import json
import time
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# --- VERCEL BLOB STORAGE WRAPPER ---
# Uses a local file fallback if the VERCEL_BLOB_TOKEN is not set, 
# allowing you to test locally before deploying to Vercel.
VERCEL_BLOB_TOKEN = os.environ.get('VERCEL_BLOB_TOKEN')

class Storage:
    FILE_NAME = "barrel_state.json"

    @classmethod
    def get_data(cls):
        if VERCEL_BLOB_TOKEN:
            # In a real Vercel environment, you would fetch from the blob URL.
            # You must save your blob URL in an env var during initial setup.
            blob_url = os.environ.get('VERCEL_BLOB_URL')
            if blob_url:
                try:
                    return requests.get(blob_url).json()
                except:
                    pass
        else:
            if os.path.exists(cls.FILE_NAME):
                with open(cls.FILE_NAME, 'r') as f:
                    return json.load(f)
        
        # Default empty state
        return {
            "water_level": 0.0,
            "battery": 0,
            "last_updated": 0,
            "today_version": 1,
            "tomorrow_version": 1,
            "today_schedule": "-" * 48, # 48 half-hour slots
            "tomorrow_schedule": "-" * 48,
            "cancel_rainy": False
        }

    @classmethod
    def save_data(cls, data):
        if VERCEL_BLOB_TOKEN:
            # Documentation: https://vercel.com/docs/storage/vercel-blob/rest-api
            headers = {"Authorization": f"Bearer {VERCEL_BLOB_TOKEN}"}
            requests.put(
                f"https://blob.vercel-storage.com/{cls.FILE_NAME}",
                headers=headers,
                data=json.dumps(data)
            )
        else:
            with open(cls.FILE_NAME, 'w') as f:
                json.dump(data, f)

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        barrel_name = request.form.get('barrel_name')
        if barrel_name:
            return redirect(url_for('dashboard', barrel_name=barrel_name))
    return render_template('index.html')

@app.route('/setup')
def setup():
    return render_template('setup.html')

@app.route('/dashboard/<barrel_name>')
def dashboard(barrel_name):
    data = Storage.get_data()
    last_updated_mins = int((time.time() - data.get('last_updated', time.time())) / 60)
    return render_template('dashboard.html', barrel_name=barrel_name, data=data, last_updated_mins=last_updated_mins)

@app.route('/api/update', methods=['POST'])
def api_update():
    """
    IoT Endpoint. Expects JSON:
    {
      "timestamp": 1690000000,
      "water": 85.5,
      "battery": 4,
      "today_version": 1,
      "tomorrow_version": 0
    }
    """
    req_data = request.json or {}
    state = Storage.get_data()
    
    # Update state with incoming barrel data
    state['last_updated'] = req_data.get('timestamp', int(time.time()))
    state['water_level'] = req_data.get('water', state['water_level'])
    state['battery'] = req_data.get('battery', state['battery'])
    
    Storage.save_data(state)

    # Determine which schedules to send
    barrel_today_v = req_data.get('today_version', 0)
    barrel_tomorrow_v = req_data.get('tomorrow_version', 0)
    
    server_today_v = state.get('today_version', 1)
    server_tomorrow_v = state.get('tomorrow_version', 1)
    
    send_today = server_today_v > barrel_today_v
    send_tomorrow = server_tomorrow_v > barrel_tomorrow_v

    header = ""
    if send_today and send_tomorrow:
        header = "yy"
    elif send_today and not send_tomorrow:
        header = "yn"
    elif not send_today and send_tomorrow:
        header = "ny"
    else:
        header = "nn"

    # Enforce strict 98 character fixed-length format (2 header + 48 today + 48 tomorrow)
    # Using spaces as padding if a schedule isn't sent to maintain the exact length.
    today_str = state['today_schedule'] if send_today else " " * 48
    tomorrow_str = state['tomorrow_schedule'] if send_tomorrow else " " * 48

    response_string = f"{header}{today_str}{tomorrow_str}"
    
    return response_string, 200, {'Content-Type': 'text/plain'}