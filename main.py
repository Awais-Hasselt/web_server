import os
import json
import time
import hashlib
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATIE ---
VERCEL_BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

class Storage:
    @classmethod
    def get_filename(cls, barrel_name):
        """Genereert een veilige MD5 hash voor de bestandsnaam."""
        safe_id = hashlib.md5(barrel_name.strip().encode()).hexdigest()
        return f"barrel_{safe_id}.json"

    @classmethod
    def get_data(cls, barrel_name, create_if_missing=False):
        filename = cls.get_filename(barrel_name)
        
        if VERCEL_BLOB_TOKEN:
            headers = {"Authorization": f"Bearer {VERCEL_BLOB_TOKEN}"}
            try:
                list_url = f"https://blob.vercel-storage.com/?prefix={filename}"
                list_resp = requests.get(list_url, headers=headers).json()
                
                if list_resp.get("blobs"):
                    blob_url = list_resp["blobs"][0]["url"]
                    data = requests.get(blob_url).json()
                    data['barrel_name'] = barrel_name
                    return data
            except Exception as e:
                print(f"Blob Read Error: {e}")

        if not create_if_missing:
            return None

        # Fallback / Nieuwe Ton configuratie
        return {
            "barrel_name": barrel_name,
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
    def save_data(cls, barrel_name, data):
        filename = cls.get_filename(barrel_name)
        data['barrel_name'] = barrel_name
        
        if VERCEL_BLOB_TOKEN:
            headers = {
                "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
                "x-add-random-suffix": "false",
                "Content-Type": "application/json"
            }
            requests.put(
                f"https://blob.vercel-storage.com/{filename}",
                headers=headers,
                data=json.dumps(data)
            )

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        barrel_name = request.form.get('barrel_name', '').strip()
        if barrel_name:
            data = Storage.get_data(barrel_name)
            if data:
                return redirect(url_for('dashboard', barrel_name=barrel_name))
            else:
                error = f"Geen ton gevonden met de naam '{barrel_name}'. Controleer de spelling of verbind je ton eerst."
        else:
            error = "Vul a.u.b. een naam in."
            
    return render_template('index.html', error=error)

@app.route('/dashboard/<barrel_name>')
def dashboard(barrel_name):
    data = Storage.get_data(barrel_name)
    if not data:
        return redirect(url_for('index'))
        
    last_updated_mins = int((time.time() - data['last_updated']) / 60) if data['last_updated'] > 0 else "?"
    timeslots = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(24) for m in (0, 30)]
    
    return render_template('dashboard.html', 
                         data=data, 
                         barrel_name=barrel_name, 
                         last_updated_mins=last_updated_mins,
                         timeslots=timeslots)

@app.route('/api/status', methods=['POST'])
def update_status():
    try:
        raw_body = request.data.decode('utf-8').split('\n', 1)
        if len(raw_body) < 2:
            return "error: invalid format", 400
            
        barrel_name = raw_body[0].strip()
        status_line = raw_body[1].strip()
        
        # Bij API status maken we de ton WEL aan als hij niet bestaat
        server_data = Storage.get_data(barrel_name, create_if_missing=True)
        
        parts = {p.strip()[0]: p.strip()[1:] for p in status_line.split(',')}
        v_parts = parts['v'].split('|')
        ton_v_today = int(v_parts[0])
        ton_v_tomorrow = int(v_parts[1])

        server_data['last_updated'] = int(time.time())
        server_data['battery'] = int(parts['b'])
        server_data['water_level'] = float(parts['w'])
        Storage.save_data(barrel_name, server_data)

        up_today = "y" if server_data['today_version'] > ton_v_today else "n"
        up_tomorrow = "y" if server_data['tomorrow_version'] > ton_v_tomorrow else "n"
        
        response = f"{up_today}{up_tomorrow}"

        if up_today == "y":
            response += f"{str(server_data['today_version']).zfill(3)}{server_data['today_schedule']}"
        if up_tomorrow == "y":
            response += f"{str(server_data['tomorrow_version']).zfill(3)}{server_data['tomorrow_schedule']}"

        return response

    except Exception as e:
        return f"error: {str(e)}", 400

@app.route('/api/schedule', methods=['POST'])
def save_schedule():
    web_data = request.json
    barrel_name = web_data.get('barrel_name')
    server_data = Storage.get_data(barrel_name)

    if not server_data:
        return jsonify({"status": "error", "message": "Ton niet gevonden"}), 404

    if server_data['today_schedule'] != web_data['today_schedule']:
        server_data['today_schedule'] = web_data['today_schedule']
        server_data['today_version'] += 1

    if server_data['tomorrow_schedule'] != web_data['tomorrow_schedule']:
        server_data['tomorrow_schedule'] = web_data['tomorrow_schedule']
        server_data['tomorrow_version'] += 1

    server_data['cancel_rainy'] = web_data.get('cancel_rainy', False)
    
    Storage.save_data(barrel_name, server_data)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)