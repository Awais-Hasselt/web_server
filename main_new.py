import time
from flask import Flask, render_template, request, jsonify, redirect, url_for
from Storage import Storage

app = Flask(__name__)

LAT = 50.9094
LON = 5.4179
GMT_OFFSET = 3600 * 2


def get_now_gmt2():
    return int(time.time() + GMT_OFFSET)


@app.route('/setup', methods=['GET'])
def setup_page():
    return render_template('setup.html')


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
                error = f"Geen ton gevonden met de naam '{barrel_name}'."
        else:
            error = 'Vul een naam in.'

    return render_template('index.html', error=error)


@app.route('/dashboard/<barrel_name>')
def dashboard(barrel_name):

    data = Storage.get_data(barrel_name)

    if not data:
        return redirect(url_for('index'))

    data.setdefault('history', [])
    data.setdefault('today_schedule', '-' * 48)
    data.setdefault('tomorrow_schedule', '-' * 48)
    data.setdefault('cancel_rainy', False)
    data.setdefault('battery', 0)
    data.setdefault('water_level', 0)

    diff = max(0, int(time.time()) - int(data.get('last_updated', int(time.time()))))

    if diff < 60:
        last_updated_str = f'{diff} sec.'
    else:
        last_updated_str = f'{diff // 60} min.'

    return render_template(
        'dashboard_new.html',
        barrel_name=barrel_name,
        data=data,
        last_updated_mins=last_updated_str
    )


@app.route('/api/live/<barrel_name>')
def api_live(barrel_name):

    data = Storage.get_data(barrel_name)

    if not data:
        return jsonify({'status': 'error'}), 404

    return jsonify(data)


@app.route('/api/history/<barrel_name>')
def api_history(barrel_name):

    data = Storage.get_data(barrel_name)

    if not data:
        return jsonify({'status': 'error'}), 404

    return jsonify({
        'history': data.get('history', [])
    })


@app.route('/api/status', methods=['POST'])
def update_status():

    try:
        raw_body = request.data.decode('utf-8').split('\n', 1)

        if len(raw_body) < 2:
            return 'error: invalid format', 400

        barrel_name = raw_body[0].strip()
        status_line = raw_body[1].strip()

        server_data = Storage.get_data(barrel_name, create_if_missing=True)

        parts = {p.strip()[0]: p.strip()[1:] for p in status_line.split(',')}

        server_now = get_now_gmt2()
        barrel_time = int(parts['t'])

        time_diff_seconds = server_now - barrel_time

        shift = round(time_diff_seconds / 1800)

        def shift_schedule(sched_str, s):
            if s == 0:
                return sched_str

            shifted = ['-'] * 48

            for i in range(48):
                new_idx = i - s

                if 0 <= new_idx < 48:
                    shifted[new_idx] = sched_str[i]

            return ''.join(shifted)

        v_parts = parts['v'].split('|')

        ton_v_today = int(v_parts[0])
        ton_v_tomorrow = int(v_parts[1])

        server_data['last_updated'] = int(time.time())
        server_data['battery'] = int(parts['b'])
        server_data['water_level'] = float(parts['w'])

        server_data.setdefault('history', [])

        server_data['history'].append([
            int(time.time()),
            float(parts['w'])
        ])

        server_data['history'] = server_data['history'][-2000:]

        Storage.save_data(barrel_name, server_data)

        up_today = 'y' if server_data['today_version'] != ton_v_today else 'n'
        up_tomorrow = 'y' if server_data['tomorrow_version'] != ton_v_tomorrow else 'n'

        response = f'{up_today}{up_tomorrow}'

        if up_today == 'y':
            v_str = str(server_data['today_version']).zfill(3)
            final_sched = shift_schedule(server_data['today_schedule'], shift)
            response += f'{v_str}{final_sched}'

        if up_tomorrow == 'y':
            v_str = str(server_data['tomorrow_version']).zfill(3)
            final_sched = shift_schedule(server_data['tomorrow_schedule'], shift)
            response += f'{v_str}{final_sched}'

        return response

    except Exception as e:
        return f'error: {str(e)}', 400


@app.route('/api/schedule', methods=['POST'])
def save_schedule():

    web_data = request.json

    barrel_name = web_data.get('barrel_name')

    server_data = Storage.get_data(barrel_name)

    if not server_data:
        return jsonify({
            'status': 'error',
            'message': 'Ton niet gevonden'
        }), 404

    if server_data['today_schedule'] != web_data['today_schedule']:
        server_data['today_schedule'] = web_data['today_schedule']
        server_data['today_version'] += 1

    if server_data['tomorrow_schedule'] != web_data['tomorrow_schedule']:
        server_data['tomorrow_schedule'] = web_data['tomorrow_schedule']
        server_data['tomorrow_version'] += 1

    server_data['cancel_rainy'] = web_data.get('cancel_rainy', False)

    Storage.save_data(barrel_name, server_data)

    return jsonify({'status': 'success'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)