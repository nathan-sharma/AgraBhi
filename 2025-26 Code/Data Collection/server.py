import serial, pynmea2, time, os, math
from flask import Flask, render_template, jsonify
logged_data_list = []
import requests
import RPi.GPIO as GPIO
import threading
from flask import Flask, render_template, jsonify, request, send_file
app = Flask(__name__)
import json


current_latitude = "N/A"
current_longitude = "N/A"
current_moisture = "N/A"
sample_ID = 0
last_lat = None
last_lon = None 
landing_event_flag = False
SPRINKLER_FILE = "sprinklers.json"
points = []  

try:
    serMoisture = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    serGps = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
except Exception as e:
    print(f"Serial Error: {e}")
    serMoisture = serGps = None


def load_sprinklers():
    if os.path.exists(SPRINKLER_FILE):
        with open(SPRINKLER_FILE, 'r') as f:
            return json.load(f)
    return []


def save_sprinklers(data):
    with open(SPRINKLER_FILE, 'w') as f:
        json.dump(data, f)


@app.route("/covariates")
def covariates_page():
    return render_template("sprinklers.html")


@app.route("/get_sprinklers")
def get_sprinklers():
    return jsonify(load_sprinklers())


@app.route("/add_sprinkler", methods=['POST'])
def add_sprinkler():
    try:
        data = request.get_json()

        if not data:
            return "No data received", 400

        sprinklers = load_sprinklers()
        sprinklers.append(data)
        save_sprinklers(sprinklers)
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500


@app.route("/delete_sprinkler/<int:index>", methods=['DELETE'])
def delete_sprinkler(index):
    sprinklers = load_sprinklers()
    if 0 <= index < len(sprinklers):
        sprinklers.pop(index)
        save_sprinklers(sprinklers)
    return "OK"
def dist_points(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    l1, l2 = math.radians(lon1), math.radians(lon2)
    x = (l2 - l1) * math.cos((p1 + p2) / 2)
    y = (p2 - p1)
    return math.sqrt(x * x + y * y) * R


def read_gps_with_accuracy():
    if serGps:
        serGps.reset_input_buffer()
        time.sleep(0.1)

    lat, lon, hdop, vdop = None, None, None, None
    CEP, TWOD_MULTIPLIER = 1.0, 2.45
    timeout = time.time() + 1.0

    while time.time() < timeout:
        if serGps and serGps.in_waiting > 0:
            line = serGps.readline().decode('utf-8', errors='ignore').strip()

            if 'GSA' in line:
                msg = pynmea2.parse(line)
                hdop = float(msg.hdop)

            if 'GGA' in line:
                msg = pynmea2.parse(line)
                if msg.gps_qual > 0:
                    lat, lon = msg.latitude, msg.longitude

            if lat and hdop:
                h_err = (CEP * TWOD_MULTIPLIER) * hdop
                return lat, lon, h_err

    return None, None, None
@app.route("/")
def index():
    return render_template("index.html", initial_data=logged_data_list)


@app.route("/log")
def log_action():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude, logged_data_list
    force_log = request.args.get('override') == 'true'

    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except:
                current_moisture = "Error"

    serGps.reset_input_buffer()
    new_lat, new_lon, h_err = read_gps_with_accuracy()

    if new_lat is None:
        return jsonify({"status": "error", "message": "No GPS Fix - Log Aborted"})

    distance_from_last = 0.0

    if last_lat is not None:
        distance_from_last = dist_points(last_lat, last_lon, new_lat, new_lon)
    elif last_lat is None:
        distance_from_last = h_err * 3

    if not force_log:
        if h_err and distance_from_last < (h_err * 3):
            return jsonify({
               "status": "warning",
                "message": f"Log Skipped: Points too close ({distance_from_last:.2f}m < {h_err*3:.1f}m threshold)"
            })

    current_latitude, current_longitude = new_lat, new_lon
    last_lat, last_lon = new_lat, new_lon

    sprinklers = load_sprinklers()
    closest_dist = "N/A"
    closest_name = "None"

    if sprinklers and new_lat:
        distances = []
        for s in sprinklers:
            d = dist_points(new_lat, new_lon, s['lat'], s['lon'])
            distances.append((d, s['name']))

        min_entry = min(distances, key=lambda x: x[0])
        closest_dist = round(min_entry[0], 2)
        closest_name = min_entry[1]

    filename = "data.csv"

    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write('Sample ID, Latitude, Longitude, Moisture,Elevation(m),  Distance from last point(m), Closest Sprinkler, Dist to Sprinkler(m)\n')

    url = f"https://epqs.nationalmap.gov/v1/json?x={current_longitude}&y={current_latitude}&units=Meters&wkid=4326"
    response = requests.get(url)
    elevation = response.json()['value']
    elevation = float(elevation)

    with open(filename, 'a') as f:
        f.write(f"{sample_ID},{current_latitude},{current_longitude},{current_moisture},{elevation}, {distance_from_last:.2f},{closest_name}, {closest_dist}\n")

    sample_ID += 1
    new_point = [
        sample_ID,
        current_latitude,
        current_longitude,
        current_moisture,
    ]

    logged_data_list.append(new_point)

    return jsonify({
        "full_list": logged_data_list,
        "new_point": new_point
    })


@app.route("/reset")
def reset_tracking():
    global sample_ID, last_lat, last_lon
    sample_ID = 0
    last_lat = last_lon = None
    return "Tracking and ID Reset."

@app.route("/check_landing")
def check_landing():
    pin_state = GPIO.input(LANDING_PIN) == GPIO.HIGH
    return jsonify({"landed": pin_state})


@app.route("/extend")
def extend():
    if serMoisture:
        serMoisture.write(b"e\n")
    return "SUCCESS: Actuator Extended"


@app.route("/retract")
def retract():
    if serMoisture:
        serMoisture.write(b"r\n")
    return "SUCCESS: Actuator Retracted"


@app.route("/collect")
def collect():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude

    lat, lon, h_err = read_gps_with_accuracy()

    url = f"https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}&units=Meters&wkid=4326"
    response = requests.get(url)
    elevation = response.json()['value']
    elevation = float(elevation)

    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except:
                current_moisture = "Error"

    closest_name = "None"
    closest_dist = "N/A"
    sprinklers = load_sprinklers()

    if sprinklers and lat:
        distances = []
        for s in sprinklers:
            d = dist_points(lat, lon, s['lat'], s['lon'])
            distances.append((d, s['name']))

        min_entry = min(distances, key=lambda x: x[0])
        closest_dist = round(min_entry[0], 2)
        closest_name = min_entry[1]
   return jsonify({
        "moisture": current_moisture,
        "lat": lat if lat else "No Fix",
        "lon": lon if lon else "No Fix",
        "elevation": elevation if elevation else "Couldn't get elevation data, check wifi",
        "h_err": round(h_err, 2) if h_err else "N/A",
        "closest_sprinkler": closest_name,
        "sprinkler_dist": closest_dist
    })


@app.route("/view_logs")
def view_logs():
    csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")

    if not os.path.exists(csv_path):
        return "No logs available yet."

    return send_file(csv_path, mimetype='text/csv', as_attachment=False)


@app.route("/clear_logs")
def clear_logs():
    csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")

    if not os.path.exists(csv_path):
        return "No logs to clear."

    with open(csv_path, 'w') as f:
        f.write("Sample ID, Latitude, Longitude, Moisture, Elevation(m), Distance from last point(m),Closest Sprinkler, Distance to Sprinkler(m)\n")

    return "All logs cleared successfully, data.csv contents are now empty."

@app.route("/get_latest_point")
def get_latest_point():
    if logged_data_list:
        return jsonify(logged_data_list[-1])
    return jsonify([])
LANDING_PIN = 37
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LANDING_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


def monitor_landing():
    """Background thread that waits for the Pixhawk Relay signal."""
    print("Auto-Log Thread: Active and listening on Pin 37...")

    while True:
        if GPIO.input(LANDING_PIN) == GPIO.HIGH: 
            global landing_event_flag
            landing_event_flag = True
            print("LANDING DETECTED via GPIO! Auto-logging point...")
            if serMoisture:
                serMoisture.write(b"e\n") 
                time.sleep(30)
            with app.test_client() as client:
                response = client.get('/log?override=true')
                print(f"Auto-Log Status: {response.status}")

            while GPIO.input(LANDING_PIN) == GPIO.HIGH:
                time.sleep(1)

            print("Signal reset. Waiting for next landing...")

        else: 
            landing_event_flag = False
            if serMoisture: 
                serMoisture.write(b"r\n")


threading.Thread(target=monitor_landing, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)