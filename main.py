import os
import json
import time
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

VERCEL_BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

class Storage:
    FILE_NAME = "barrel_state.json"

    @classmethod
    def get_data(cls):
        if VERCEL_BLOB_TOKEN:
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
        
        # Standaard lege status (water_level in liters)
        return {
            "water_level": 0.0,
            "max_liters": 200.0, # Toegevoegd voor capaciteit berekening
            "battery": 0,
            "last_updated": 0,
            "today_version": 1,
            "tomorrow_version": 1,
            "today_schedule": "-" * 48, # 48 halve uren
            "tomorrow_schedule": "-" * 48,
            "cancel_rainy": False
        }

    @classmethod
    def save_data(cls, data):
        if VERCEL_BLOB_TOKEN:
            headers = {"Authorization": f"Bearer {VERCEL_BLOB_TOKEN}"}
            requests.put(
                f"https://blob.vercel-storage.com/{cls.FILE_NAME}",
                headers=headers,
                data=json.dumps(data)
            )
        else:
            with open(cls.FILE_NAME, 'w') as f:
                json.dump(data, f)

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
    
    # Genereer tijdsloten voor de UI editor (00:00, 00:30, etc.)
    timeslots = []
    for h in range(24):
        timeslots.append(f"{h:02d}:00")
        timeslots.append(f"{h:02d}:30")

    return render_template('dashboard.html', 
                           barrel_name=barrel_name, 
                           data=data, 
                           last_updated_mins=last_updated_mins,
                           timeslots=timeslots)

@app.route('/api/schedule', methods=['POST'])
def update_schedule():
    """Verwerkt schema updates vanuit het web dashboard"""
    req_data = request.json
    state = Storage.get_data()
    
    if 'today_schedule' in req_data and req_data['today_schedule'] != state['today_schedule']:
        state['today_schedule'] = req_data['today_schedule']
        state['today_version'] += 1
        
    if 'tomorrow_schedule' in req_data and req_data['tomorrow_schedule'] != state['tomorrow_schedule']:
        state['tomorrow_schedule'] = req_data['tomorrow_schedule']
        state['tomorrow_version'] += 1
        
    Storage.save_data(state)
    return jsonify({"status": "success"})

@app.route('/api/update', methods=['POST'])
def api_update():
    """IoT Endpoint voor de regenton"""
    req_data = request.json or {}
    state = Storage.get_data()
    
    state['last_updated'] = req_data.get('timestamp', int(time.time()))
    state['water_level'] = req_data.get('water', state['water_level'])
    state['battery'] = req_data.get('battery', state['battery'])
    
    Storage.save_data(state)

    barrel_today_v = req_data.get('today_version', 0)
    barrel_tomorrow_v = req_data.get('tomorrow_version', 0)
    
    server_today_v = state.get('today_version', 1)
    server_tomorrow_v = state.get('tomorrow_version', 1)
    
    send_today = server_today_v > barrel_today_v
    send_tomorrow = server_tomorrow_v > barrel_tomorrow_v

    if send_today and send_tomorrow: header = "yy"
    elif send_today and not send_tomorrow: header = "yn"
    elif not send_today and send_tomorrow: header = "ny"
    else: header = "nn"

    today_str = state['today_schedule'] if send_today else " " * 48
    tomorrow_str = state['tomorrow_schedule'] if send_tomorrow else " " * 48

    response_string = f"{header}{today_str}{tomorrow_str}"
    
    return response_string, 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    app.run(debug=True, port=5000)