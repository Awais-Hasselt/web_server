import os
import json
import time
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Configuratie
BARREL_NAME = "Slimme Regenton"
VERCEL_BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

class Storage:
    FILE_NAME = "barrel_state.json"
    DEFAULT_STATE = {
        "water_level": 0.0,
        "max_liters": 200.0, 
        "battery": 0,
        "last_updated": 0,
        "today_version": 1,
        "tomorrow_version": 1,
        "today_schedule": "-" * 48, 
        "tomorrow_schedule": "-" * 48,
        "cancel_rainy": False
    }

    @classmethod
    def get_data(cls):
        if VERCEL_BLOB_TOKEN:
            headers = {"Authorization": f"Bearer {VERCEL_BLOB_TOKEN}"}
            try:
                # Zoek het bestand in Vercel Blob
                list_resp = requests.get(f"https://blob.vercel-storage.com/?prefix={cls.FILE_NAME}", headers=headers).json()
                if list_resp.get("blobs"):
                    url = list_resp["blobs"][0]["url"]
                    return requests.get(url).json()
            except Exception as e:
                print(f"Blob Error: {e}")
        return cls.DEFAULT_STATE

    @classmethod
    def save_data(cls, data):
        if VERCEL_BLOB_TOKEN:
            headers = {
                "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
                "x-add-random-suffix": "false"
            }
            requests.put(
                f"https://blob.vercel-storage.com/{cls.FILE_NAME}",
                headers=headers,
                data=json.dumps(data)
            )

@app.route('/')
def dashboard():
    data = Storage.get_data()
    last_updated_mins = int((time.time() - data['last_updated']) / 60) if data['last_updated'] > 0 else "?"
    
    # Genereer tijdslots voor de editor (00:00, 00:30, etc.)
    timeslots = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(24) for m in (0, 30)]
    
    return render_template('dashboard.html', 
                         data=data, 
                         barrel_name=BARREL_NAME, 
                         last_updated_mins=last_updated_mins,
                         timeslots=timeslots)

@app.route('/api/status', methods=['POST'])
def update_status():
    """
    Input van ton: "t1715673600, v1|1, b4, w145.2"
    Output naar ton: "yn[versie3][schedule48]..."
    """
    try:
        raw_input = request.data.decode('utf-8')
        server_data = Storage.get_data()
        
        # Parsen van de ton string
        parts = {p.strip()[0]: p.strip()[1:] for p in raw_input.split(',')}
        v_parts = parts['v'].split('|')
        ton_v_today = int(v_parts[0])
        ton_v_tomorrow = int(v_parts[1])

        # Sla nieuwe status op
        server_data['last_updated'] = int(time.time())
        server_data['battery'] = int(parts['b'])
        server_data['water_level'] = float(parts['w'])
        Storage.save_data(server_data)

        # Bepaal 'y' of 'n'
        up_today = "y" if server_data['today_version'] > ton_v_today else "n"
        up_tomorrow = "y" if server_data['tomorrow_version'] > ton_v_tomorrow else "n"
        
        response_str = f"{up_today}{up_tomorrow}"

        # Voeg schema data toe indien nodig
        if up_today == "y":
            v_str = str(server_data['today_version']).zfill(3)
            response_str += f"{v_str}{server_data['today_schedule']}"
            
        if up_tomorrow == "y":
            v_str = str(server_data['tomorrow_version']).zfill(3)
            response_str += f"{v_str}{server_data['tomorrow_schedule']}"

        return response_str # Plain text response voor de ton

    except Exception as e:
        return f"error: {str(e)}", 400

@app.route('/api/schedule', methods=['POST'])
def save_schedule():
    """Update vanuit het dashboard"""
    web_data = request.json
    server_data = Storage.get_data()

    # Update today schedule + versie
    if server_data['today_schedule'] != web_data['today_schedule']:
        server_data['today_schedule'] = web_data['today_schedule']
        server_data['today_version'] += 1

    # Update tomorrow schedule + versie
    if server_data['tomorrow_schedule'] != web_data['tomorrow_schedule']:
        server_data['tomorrow_schedule'] = web_data['tomorrow_schedule']
        server_data['tomorrow_version'] += 1

    server_data['cancel_rainy'] = web_data.get('cancel_rainy', False)
    
    Storage.save_data(server_data)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)