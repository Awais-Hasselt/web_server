import time
from flask import Flask, render_template, request, jsonify, redirect, url_for
from Storage import Storage

app = Flask(__name__)

LAT = 50.9094
LON = 5.4179
GMT_OFFSET = 7200


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

    diff = int(time.time() - data.get('last_updated', time.time()))

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
    app.run(debug=True, port=5000)