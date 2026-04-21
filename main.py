import time
from flask import Flask, render_template, request, jsonify, redirect, url_for
from Storage import Storage

app = Flask(__name__)

# --- CONFIGURATION ---
LAT = 50.9094
LON = 5.4179
GMT_OFFSET = 7200  # GMT+2 in seconds

def get_now_gmt2():
    return int(time.time() + GMT_OFFSET)

@app.route('/dashboard/<barrel_name>')
def dashboard(barrel_name):
    data = Storage.get_data(barrel_name)
    if not data:
        return redirect(url_for('index'))
    
    # Ensure physical constants are available to the template
    # These match your firmware: Height 90cm, Radius 25cm
    data['max_height'] = 90.0 
    
    # Format the last updated string
    diff = int(time.time() - data['last_updated'])
    last_updated_str = f"{diff} sec." if diff < 60 else f"{diff // 60} min."
    
    timeslots = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(24) for m in (0, 30)]
    
    return render_template('dashboard.html', 
                         data=data, 
                         barrel_name=barrel_name, 
                         last_updated_mins=last_updated_str,
                         timeslots=timeslots)

@app.route('/api/status', methods=['POST'])
def update_status():
    try:
        raw_body = request.data.decode('utf-8').split('\n', 1)
        if len(raw_body) < 2:
            return "error: invalid format", 400
            
        barrel_name = raw_body[0].strip()
        status_line = raw_body[1].strip()
        
        server_data = Storage.get_data(barrel_name, create_if_missing=True)

        # Parse Status (format: t12345678,v1|1,b5,w20.5)
        parts = {p.strip()[0]: p.strip()[1:] for p in status_line.split(',')}
        
        # TIME OFFSET LOGIC
        # server_now is GMT+2, barrel_time is whatever it sent (usually UTC)
        server_now = get_now_gmt2()
        barrel_time = int(parts['t'])
        time_diff_seconds = server_now - barrel_time 
        
        # Calculate index shift (each index is 30 mins / 1800 seconds)
        # If barrel is 2 hours behind, shift is +4
        shift = round(time_diff_seconds / 1800)

        def shift_schedule(sched_str, s):
            if s == 0: return sched_str
            # Move elements. If s is positive, the barrel is BEHIND.
            # A 11:00 task (idx 22) must be moved to 09:00 (idx 18) for the barrel to hit it correctly.
            shifted = ['-'] * 48
            for i in range(48):
                new_idx = i - s
                if 0 <= new_idx < 48:
                    shifted[new_idx] = sched_str[i]
            return "".join(shifted)

        v_parts = parts['v'].split('|')
        ton_v_today = int(v_parts[0])
        ton_v_tomorrow = int(v_parts[1])

        server_data['last_updated'] = int(time.time()) # Real world arrival time
        server_data['battery'] = int(parts['b'])
        server_data['water_level'] = float(parts['w'])
        
        Storage.save_data(barrel_name, server_data)

        # Compare versions
        up_today = "y" if server_data['today_version'] != ton_v_today else "n"
        up_tomorrow = "y" if server_data['tomorrow_version'] != ton_v_tomorrow else "n"
        
        response = f"{up_today}{up_tomorrow}"

        if up_today == "y":
            v_str = str(server_data['today_version']).zfill(3)
            final_sched = shift_schedule(server_data['today_schedule'], shift)
            response += f"{v_str}{final_sched}"
            
        if up_tomorrow == "y":
            v_str = str(server_data['tomorrow_version']).zfill(3)
            final_sched = shift_schedule(server_data['tomorrow_schedule'], shift)
            response += f"{v_str}{final_sched}"

        return response

    except Exception as e:
        return f"error: {str(e)}", 400